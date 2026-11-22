"""Public command line. Inspect and dry-run never import motor SDKs."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from .config import load_config
from .sensors import MockSensor, PositionMeasurement, load_sensor, validate_measurement
from .teleop import TeleopSession
from .transport import DryRunTransport, DynamixelTransport


def parser():
    result = argparse.ArgumentParser(description="OpenTDCR: inspect, dry-run, and explicitly enable hardware")
    sub = result.add_subparsers(dest="action", required=True)
    inspect = sub.add_parser("inspect", help="validate and print a robot configuration as JSON")
    inspect.add_argument("--config", required=True)
    teleop = sub.add_parser("teleop", help="bounded keyboard command steps; dry-run unless --hardware")
    teleop.add_argument("--config", required=True)
    teleop.add_argument("--input", choices=("keyboard", "dualsense"), default="keyboard")
    teleop.add_argument("--hardware", action="store_true", help="enable physical XL430 servos")
    teleop.add_argument("--port", help="explicit serial device, used only with --hardware")
    teleop.add_argument("--confirm-home", action="store_true", help="confirm current manually tensioned pose is home")
    teleop.add_argument("--commands", help="space-separated dry-run commands for examples and CI")
    teleop.add_argument("--sensor", help="trusted Python module:factory; adds a measurement health gate")
    teleop.add_argument("--sensor-config", help="local Lyra JSON settings (requires --sensor lyra)")
    calibration = sub.add_parser("calibrate", help="sensor-independent tendon calibration; synthetic dry-run by default")
    calibration.add_argument("--config", required=True)
    calibration.add_argument("--calibration-config", required=True)
    calibration.add_argument("--hardware", action="store_true")
    calibration.add_argument("--port", help="explicit servo serial device, used only with --hardware")
    calibration.add_argument("--confirm-home", action="store_true", help="acknowledge prepared starting posture as temporary encoder reference")
    calibration.add_argument("--sensor", help="trusted module:factory, or lyra; required for physical calibration")
    calibration.add_argument("--sensor-config", help="local Lyra JSON settings")
    calibration.add_argument("--output", help="write a new local JSON report; use a .local.json filename")
    calibration.add_argument("--teleop", action="store_true", help="continue teleoperation in the same calibrated motor session")
    calibration.add_argument("--input", choices=("keyboard", "dualsense"), default="keyboard")
    calibration.add_argument("--commands", help="scripted keyboard commands after --teleop; dry-run only")
    sensor = sub.add_parser("sensor", help="read and validate measurements without any motor access")
    sensor.add_argument("--sensor", default="opentdcr.sensors:MockSensor", help="trusted module:factory")
    sensor.add_argument("--sensor-config", help="local Lyra JSON settings (requires --sensor lyra)")
    sensor.add_argument("--samples", type=int, default=5)
    return result


def _make_sensor(args):
    if args.sensor == "lyra":
        if not args.sensor_config:
            raise ValueError("--sensor lyra requires --sensor-config")
        from .adapters.lyra import create_lyra_sensor
        return create_lyra_sensor(args.sensor_config)
    if args.sensor_config:
        raise ValueError("--sensor-config requires --sensor lyra")
    return load_sensor(args.sensor) if args.sensor else None


def _make_transport(args, config):
    if args.hardware:
        if args.commands is not None or not sys.stdin.isatty():
            raise ValueError("hardware requires interactive terminal input; --commands is dry-run only")
        return DynamixelTransport(config, args.port, confirm_home=args.confirm_home)
    if args.port or args.confirm_home:
        raise ValueError("--port and --confirm-home require --hardware")
    return DryRunTransport(config)


def _run_inputs(args, session, gamepad=None):
    owns_gamepad = gamepad is None
    try:
        if args.input == "dualsense":
            from .gamepad import DualSenseUSB
            if gamepad is None:
                gamepad = DualSenseUSB().open()
            session.motion_guard = lambda: gamepad.read(require_deadman=True)
            return _gamepad_loop(session, gamepad)
        print(f"Select segment 1–{session.config.n_segments}; w/a/s/d = {session.config.keyboard_step_mm:g} mm Clarke step; home; q. Press Enter after each command.")
        scripted = iter(args.commands.split()) if args.commands is not None else None
        while True:
            command = next(scripted, "q") if scripted is not None else input(f"segment {session.segment+1}> ")
            if command.strip().lower() in ("q", "quit", "exit"):
                break
            if not command.strip():
                continue
            target = session.command(command)
            if target is not None:
                print(json.dumps({"segment": session.segment+1, "tendon_displacement_mm": target.round(6).tolist()}))
        return 0
    finally:
        if gamepad is not None and owns_gamepad:
            gamepad.close()


def _teleop(args):
    config = load_config(args.config)
    if args.commands is not None and args.input != "keyboard":
        raise ValueError("--commands requires keyboard input")
    transport = _make_transport(args, config)
    sensor = None
    gamepad = None
    try:
        sensor = _make_sensor(args)
        if args.hardware and isinstance(sensor, MockSensor):
            raise ValueError("MockSensor cannot serve as a physical measurement gate")
        session = TeleopSession(config, transport, sensor)
        # Validate sensor before motor torque can be enabled.
        session.check_sensor()
        if args.input == "dualsense":
            from .gamepad import DualSenseUSB
            gamepad = DualSenseUSB().open()
        transport.open()
        stop_hint = "Circle or Ctrl-C ends the session" if args.input == "dualsense" else "q disables torque"
        print(f"HARDWARE: motors enabled; {stop_hint}." if args.hardware else "DRY RUN: no motor connection.")
        return _run_inputs(args, session, gamepad)
    finally:
        try:
            transport.close()
        finally:
            try:
                if gamepad is not None:
                    gamepad.close()
            finally:
                if sensor:
                    sensor.close()


class _CalibrationDemoSensor(MockSensor):
    """Synthetic deflection from commands; no claim of measured robot physics."""
    def __init__(self, transport):
        self.transport = transport

    def read(self):
        displacement = max(0.0, float(max(self.transport.position_mm)))
        return PositionMeasurement((displacement, 0.0, 0.0), time.monotonic())


def _calibrate(args):
    from .calibration import calibrate, load_calibration_config
    config = load_config(args.config)
    tuning = load_calibration_config(args.calibration_config, config)
    if args.commands is not None and (not args.teleop or args.input != "keyboard"):
        raise ValueError("--commands requires --teleop and keyboard input")
    if args.input != "keyboard" and not args.teleop:
        raise ValueError("--input requires --teleop")
    if args.hardware and not args.sensor:
        raise ValueError("physical calibration requires a real --sensor")
    output = Path(args.output) if args.output else None
    if output is not None and output.exists():
        raise ValueError("report already exists; choose a new local report filename")
    transport = _make_transport(args, config)
    sensor = None
    try:
        sensor = _make_sensor(args)
        if sensor is None:
            sensor = _CalibrationDemoSensor(transport)
        if args.hardware and isinstance(sensor, MockSensor):
            raise ValueError("MockSensor cannot calibrate physical hardware")
        validate_measurement(sensor.read(), config.sensor_max_age_s)
        transport.open()
        if args.hardware:
            print("HARDWARE: calibration started; Ctrl-C aborts and requests torque-off.")
        elif isinstance(sensor, _CalibrationDemoSensor):
            print("DRY RUN: synthetic calibration; no motor connection or physical calibration.")
        else:
            print("DRY RUN: external sensor measurements; no motor connection or physical calibration.")

        def on_loosened():
            if args.hardware:
                input("Tendons loosened. Gently perturb the robot to reduce hysteresis, then press Enter: ")

        def adjustment(current_positions):
            if not args.hardware:
                return None
            print("Current tendon positions (mm):", current_positions)
            text = input("Common adjustment in mm (+ pulls, - loosens); Enter accepts: ").strip()
            return float(text) if text else None

        def progress(event):
            if event["stage"] == "threshold":
                print(f"Servo {event['servo_id']}: threshold at {event['actual_position_mm']:.3f} mm; "
                      f"after countback {event['countback_position_mm']:.3f} mm")

        options = {"on_loosened": on_loosened, "adjustment": adjustment, "on_progress": progress}
        result = calibrate(transport, sensor, tuning, **options)
        report = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "dry_run": not args.hardware,
            "measurement_source": args.sensor or "synthetic command-deflection demo",
            "sensor_configuration": asdict(sensor.config) if args.sensor == "lyra" else None,
            "robot_config": asdict(config),
            "calibration_config": asdict(tuning),
            "result": result.to_dict(),
        }
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            # Never overwrite an existing calibration or robot configuration.
            with output.open("x", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2, allow_nan=False)
                handle.write("\n")
            print(f"Local report: {output}")
        print(json.dumps(report, indent=2, allow_nan=False))
        if args.teleop:
            print("Continuing with the calibrated reference in this motor session.")
            return _run_inputs(args, TeleopSession(config, transport, sensor))
        return 0
    finally:
        try:
            transport.close()
        finally:
            if sensor:
                sensor.close()


def _gamepad_loop(session, gamepad):
    print("USB DualSense: hold L1 and move left stick; D-pad up/down selects segment; Circle exits.")
    print("Releasing L1 during motion ends the session and disables torque. Restart to continue.")
    previous_next = previous_previous = False
    while True:
        state = gamepad.read()
        session.check_sensor()
        if state.next_segment and not previous_next:
            session.segment = (session.segment+1) % session.config.n_segments
            print(f"segment {session.segment+1}")
        if state.previous_segment and not previous_previous:
            session.segment = (session.segment-1) % session.config.n_segments
            print(f"segment {session.segment+1}")
        previous_next, previous_previous = state.next_segment, state.previous_segment
        if state.deadman and (state.x or state.y):
            target = session.step((state.x, state.y))
            print(json.dumps({"segment": session.segment+1, "tendon_displacement_mm": target.round(6).tolist()}))
        time.sleep(0.05)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.action == "inspect":
            print(json.dumps(asdict(load_config(args.config)), indent=2))
        elif args.action == "sensor":
            if not 1 <= args.samples <= 10000:
                raise ValueError("--samples must be in [1, 10000]")
            sensor = _make_sensor(args)
            try:
                for _ in range(args.samples):
                    print(json.dumps(asdict(validate_measurement(sensor.read()))))
                    time.sleep(0.05)
            finally:
                sensor.close()
        elif args.action == "calibrate":
            return _calibrate(args)
        else:
            return _teleop(args)
        return 0
    except (KeyboardInterrupt, EOFError):
        print("Session ended; transport cleanup requested.", file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError, ImportError, AttributeError) as exc:
        print(f"tdcr: {exc}", file=sys.stderr)
        return 2
