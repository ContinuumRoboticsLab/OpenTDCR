"""Dry-run and explicit XL430-W250 position transports.

Register definitions: https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/
No serial device is opened during import or object construction.
"""
import importlib
import math
import time
import warnings
import numpy as np
from .config import RobotConfig


def checked_target(config, target):
    values = np.asarray(target, dtype=float)
    if values.shape != (config.n_tendons,) or not np.isfinite(values).all():
        raise ValueError(f"target requires {config.n_tendons} finite tendon displacements")
    if np.any(np.abs(values) > config.max_tendon_travel_mm + 1e-9):
        raise ValueError("target exceeds max_tendon_travel_mm")
    return values


class DryRunTransport:
    def __init__(self, config: RobotConfig):
        self.config = config
        self.position_mm = np.zeros(config.n_tendons)
        self.is_open = False

    def open(self):
        self.is_open = True
        return self

    def move(self, target, check=None):
        if not self.is_open:
            raise RuntimeError("transport is closed")
        values = checked_target(self.config, target)
        if check:
            check()
        self.position_mm = values.copy()

    def read_positions_mm(self):
        if not self.is_open:
            raise RuntimeError("transport is closed")
        return self.position_mm.copy()

    def capture_reference(self):
        offsets = self.read_positions_mm()
        self.position_mm = np.zeros(self.config.n_tendons)
        return {"offsets_mm": offsets.tolist(), "zero_ticks": None}

    def close(self):
        self.is_open = False


class DynamixelTransport:
    """Blocking bounded moves. Requires preconfigured XL430 mode 4, drive mode 0.

    open() records the current prepared pose as the initial session reference.
    Calibration can explicitly capture a new reference without reopening motors.
    This transport itself never performs homing or tendon tensioning. close() attempts
    torque-off on every verified motor even when another motor does not respond.
    An independent power cut remains necessary: software cannot guarantee stop
    after communication failure, process kill, or device failure.
    """
    MODEL = 1060
    TICK_RAD = 2 * math.pi / 4096

    def __init__(self, config: RobotConfig, port: str, *, confirm_home=False, sdk=None):
        if not config.hardware_reviewed or not confirm_home or not port:
            raise ValueError("hardware requires reviewed config, explicit port, and confirm_home=True")
        self.config, self.port_name = config, port
        self.sdk = sdk
        self.port = self.packet = None
        self.verified_ids = []
        self.is_open = False
        self.position_mm = np.zeros(config.n_tendons)
        self.zero_ticks = None

    def _check(self, comm, error, servo_id):
        if comm != self.sdk.COMM_SUCCESS or error:
            raise OSError(f"Dynamixel {servo_id}: communication={comm}, device_error={error}")

    def _read(self, servo_id, address, size):
        fn = getattr(self.packet, f"read{size}ByteTxRx")
        value, comm, error = fn(self.port, servo_id, address)
        self._check(comm, error, servo_id)
        return value

    def _write(self, servo_id, address, value, size):
        fn = getattr(self.packet, f"write{size}ByteTxRx")
        comm, error = fn(self.port, servo_id, address, int(value) & ((1 << (size*8))-1))
        self._check(comm, error, servo_id)

    def _positions(self):
        result = []
        for servo_id in self.config.servo_ids:
            if self._read(servo_id, 70, 1):
                raise OSError(f"Dynamixel {servo_id} reports a hardware fault")
            value = self._read(servo_id, 132, 4)
            result.append(value - (1 << 32) if value >= (1 << 31) else value)
        return np.array(result, dtype=np.int64)

    def open(self):
        if self.is_open:
            raise RuntimeError("transport already open")
        if self.sdk is None:
            try:
                self.sdk = importlib.import_module("dynamixel_sdk")
            except ImportError as exc:
                raise RuntimeError('Install hardware support: pip install -e ".[hardware]"') from exc
        self.port = self.sdk.PortHandler(self.port_name)
        self.packet = self.sdk.PacketHandler(2.0)
        try:
            if not self.port.openPort() or not self.port.setBaudRate(self.config.baudrate):
                raise OSError("could not open serial port or set baudrate")
            # Verify identity/settings before enabling any motor. Setup remains a
            # deliberate Wizard operation; no EEPROM registers are written here.
            for servo_id in self.config.servo_ids:
                model, comm, error = self.packet.ping(self.port, servo_id)
                self._check(comm, error, servo_id)
                if model != self.MODEL:
                    raise ValueError(f"Dynamixel {servo_id} is model {model}; only XL430-W250 is supported")
                self.verified_ids.append(servo_id)
                if self._read(servo_id, 64, 1) != 0:
                    raise ValueError(f"Dynamixel {servo_id}: start with torque disabled")
                if self._read(servo_id, 11, 1) != 4 or self._read(servo_id, 10, 1) != 0:
                    raise ValueError(f"Dynamixel {servo_id}: configure operating mode 4 and drive mode 0 in Wizard")
                if self._read(servo_id, 12, 1) < 253:
                    raise ValueError(f"Dynamixel {servo_id}: disable secondary (shadow) ID in Wizard")
                if self._read(servo_id, 68, 1) != 2:
                    raise ValueError(f"Dynamixel {servo_id}: status return level must be 2")
                if self._read(servo_id, 98, 1) != 0:
                    raise ValueError(f"Dynamixel {servo_id}: bus watchdog must be 0 for stepwise teleoperation")
            self.zero_ticks = self._positions()
            if np.any(np.abs(self.zero_ticks) > 1048575):
                raise ValueError("current positions exceed extended position range")
            for servo_id, radius, zero in zip(self.config.servo_ids, self.config.spool_radius_mm, self.zero_ticks):
                units = math.floor(self.config.max_tendon_speed_mm_s / radius * 60 / (2*math.pi) / 0.229)
                # Zero means unlimited speed. Never round up past the user's cap.
                if not 1 <= units <= 32767:
                    raise ValueError("speed limit is outside the representable nonzero XL430 profile range")
                self._write(servo_id, 112, units, 4)
                self._write(servo_id, 108, 1, 4)
                self._write(servo_id, 116, zero, 4)
            for servo_id in self.config.servo_ids:
                self._write(servo_id, 64, 1, 1)
            self.is_open = True
            return self
        except BaseException:
            self.close()
            raise

    def move(self, target, check=None):
        if not self.is_open:
            raise RuntimeError("transport is closed")
        try:
            values = checked_target(self.config, target)
            if check:
                check()
            ticks = np.rint(values / np.array(self.config.spool_radius_mm) / self.TICK_RAD
                            * np.array(self.config.servo_direction)).astype(np.int64) + self.zero_ticks
            if np.any(np.abs(ticks) > 1048575):
                raise ValueError("target exceeds extended position range")
            writer = self.sdk.GroupSyncWrite(self.port, self.packet, 116, 4)
            try:
                for servo_id, tick in zip(self.config.servo_ids, ticks):
                    if not writer.addParam(servo_id, list((int(tick) & 0xffffffff).to_bytes(4, "little"))):
                        raise OSError(f"could not queue target for Dynamixel {servo_id}")
                result = writer.txPacket()
                if result != self.sdk.COMM_SUCCESS:
                    raise OSError(f"Dynamixel sync write failed: {result}")
            finally:
                writer.clearParam()
            for servo_id, tick in zip(self.config.servo_ids, ticks):
                if self._read(servo_id, 116, 4) != (int(tick) & 0xffffffff):
                    raise OSError(f"Dynamixel {servo_id} did not accept the requested goal")
            distance = float(np.max(np.abs(values - self.position_mm)))
            deadline = time.monotonic() + 3 + 2 * distance / self.config.max_tendon_speed_mm_s
            while True:
                if check:
                    check()
                actual = self._positions()
                moving = [self._read(sid, 122, 1) for sid in self.config.servo_ids]
                profile_active = [self._read(sid, 123, 1) & 2 for sid in self.config.servo_ids]
                if not any(moving) and not any(profile_active) and np.all(np.abs(actual-ticks) <= 2):
                    self.position_mm = values.copy()
                    return
                if time.monotonic() > deadline:
                    raise TimeoutError("motor did not reach the commanded position")
                time.sleep(0.02)
        except BaseException:
            self.close()
            raise

    def read_positions_mm(self):
        """Actual encoder displacement from this session's current reference."""
        if not self.is_open:
            raise RuntimeError("transport is closed")
        try:
            return ((self._positions() - self.zero_ticks) * self.TICK_RAD
                    * np.asarray(self.config.spool_radius_mm)
                    * np.asarray(self.config.servo_direction))
        except BaseException:
            self.close()
            raise

    def capture_reference(self):
        """Rebase at the settled measured posture; never reload a saved zero."""
        if not self.is_open:
            raise RuntimeError("transport is closed")
        try:
            if any(self._read(sid, 122, 1) or self._read(sid, 123, 1) & 2
                   for sid in self.config.servo_ids):
                raise RuntimeError("cannot capture reference while motors are moving")
            ticks = self._positions()
            offsets = ((ticks - self.zero_ticks) * self.TICK_RAD
                       * np.asarray(self.config.spool_radius_mm)
                       * np.asarray(self.config.servo_direction))
            checked_target(self.config, offsets)
            self.zero_ticks = ticks.copy()
            self.position_mm = np.zeros(self.config.n_tendons)
            return {"offsets_mm": offsets.tolist(), "zero_ticks": ticks.tolist()}
        except BaseException:
            self.close()
            raise

    def close(self):
        self.is_open = False
        if self.port is not None:
            failures = []
            for servo_id in self.verified_ids:
                try:
                    self._write(servo_id, 64, 0, 1)
                except Exception as exc:
                    failures.append(f"could not disable torque on {servo_id}: {exc}")
            try:
                self.port.closePort()
            except Exception as exc:
                failures.append(f"could not close the serial port: {exc}")
            finally:
                self.port = None
                self.verified_ids = []
            # Reporting must happen after all shutdown attempts: a warnings-as-
            # errors policy must never skip another motor or the port closure.
            if failures:
                warnings.warn("; ".join(failures) + "; use the power cut", RuntimeWarning)
