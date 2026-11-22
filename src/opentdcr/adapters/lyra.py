"""Optional NDI Lyra passive-marker adapter with an explicit fixed base transform.

The PyPI distribution is ``ndicapi``; its extension module is ``ndicapy``. No
vendor module is imported and no device is opened until ``open()`` or the
explicit ``create_lyra_sensor(path)`` factory is called. Native I/O runs in a
spawned process because ndicapi 3.7.6 does not expose its C socket-timeout setter
and native calls can retain the GIL. Read/open/close waits are bounded by the
parent; a timed-out worker is terminated and cannot supply cached data later.

Native API reference: https://github.com/SciKit-Surgery/ndicapi (ndicapimodule.cxx
and ndicapi.h). TX getters supply millimetres and a camera frame counter. A TX
request has no exposure timestamp: request start minus the configured maximum
camera frame period is used as a conservative host-monotonic acquisition bound.
This assumes a live, unbuffered TX stream at the reviewed frame period; the
adapter preserves the acquisition time on repeated frames and rejects stale,
reversed, or inconsistent frames and slow replies. It does not
claim hardware-clock synchronization or perform calibration/reference tracking.
"""
from dataclasses import dataclass
from importlib import import_module
import json
import math
import multiprocessing
from pathlib import Path
import time
from typing import Callable, Protocol

import numpy as np

from opentdcr.sensors import PositionMeasurement, validate_measurement


class LyraError(RuntimeError):
    """The tracker is unavailable, invalid, ambiguous, stale, or timed out."""


def _finite(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    return float(value)


def _point(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name} must contain three millimetre coordinates")
    return tuple(_finite(x, name) for x in value)


@dataclass(frozen=True)
class LyraConfig:
    host: str
    port: int
    configuration_reviewed: bool
    rotation: tuple[tuple[float, float, float], ...]
    translation_mm: tuple[float, float, float]
    tip_mode: str
    min_sensor_mm: tuple[float, float, float] | None = None
    max_sensor_mm: tuple[float, float, float] | None = None
    timeout_s: float = 0.2
    open_timeout_s: float = 5.0
    max_frame_age_s: float = 0.25
    frame_period_s: float = 0.02

    def __post_init__(self):
        if not isinstance(self.host, str) or not self.host.strip() or any(c.isspace() for c in self.host):
            raise ValueError("host must be a configured tracker hostname or IP")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("port must be an integer in [1, 65535]")
        if type(self.configuration_reviewed) is not bool:
            raise ValueError("configuration_reviewed must be true or false")
        try:
            rotation = tuple(_point(row, "sensor_to_base.rotation") for row in self.rotation)
        except TypeError as exc:
            raise ValueError("sensor_to_base.rotation must be a 3 by 3 matrix") from exc
        if len(rotation) != 3:
            raise ValueError("sensor_to_base.rotation must be a 3 by 3 matrix")
        matrix = np.asarray(rotation, dtype=float)
        if not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-6, rtol=0) or not math.isclose(float(np.linalg.det(matrix)), 1.0, abs_tol=1e-6):
            raise ValueError("sensor_to_base.rotation must be a proper rigid rotation")
        object.__setattr__(self, "rotation", rotation)
        object.__setattr__(self, "translation_mm", _point(self.translation_mm, "translation_mm"))
        if self.tip_mode not in ("exactly_one", "roi"):
            raise ValueError("tip.mode must be exactly_one or roi; marker-list indices are not identities")
        if self.tip_mode == "roi":
            low = _point(self.min_sensor_mm, "tip.min_sensor_mm")
            high = _point(self.max_sensor_mm, "tip.max_sensor_mm")
            if not all(a < b for a, b in zip(low, high)):
                raise ValueError("tip ROI requires min_sensor_mm < max_sensor_mm on each axis")
            object.__setattr__(self, "min_sensor_mm", low)
            object.__setattr__(self, "max_sensor_mm", high)
        elif self.min_sensor_mm is not None or self.max_sensor_mm is not None:
            raise ValueError("ROI bounds are only accepted with tip.mode=roi")
        for name in ("timeout_s", "open_timeout_s", "max_frame_age_s", "frame_period_s"):
            value = _finite(getattr(self, name), name, positive=True)
            if value > 60:
                raise ValueError(f"{name} must not exceed 60 seconds")
            object.__setattr__(self, name, value)
        if self.frame_period_s >= self.max_frame_age_s:
            raise ValueError("frame_period_s must be less than max_frame_age_s")

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Lyra configuration must be a JSON object")
        allowed = {"host", "port", "configuration_reviewed", "sensor_to_base", "tip", "timeout_s", "open_timeout_s", "max_frame_age_s", "frame_period_s"}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"unknown Lyra configuration fields: {', '.join(sorted(unknown))}")
        required = {"host", "port", "configuration_reviewed", "sensor_to_base", "tip"}
        if required - set(data):
            raise ValueError(f"missing Lyra configuration fields: {', '.join(sorted(required - set(data)))}")
        transform = data["sensor_to_base"]
        if not isinstance(transform, dict) or set(transform) != {"rotation", "translation_mm"}:
            raise ValueError("sensor_to_base requires explicit rotation and translation_mm")
        tip = data["tip"]
        if not isinstance(tip, dict) or "mode" not in tip:
            raise ValueError("tip requires an explicit selection mode")
        expected = {"mode", "min_sensor_mm", "max_sensor_mm"} if tip["mode"] == "roi" else {"mode"}
        if set(tip) != expected:
            raise ValueError("tip fields must match the selected exactly_one or roi mode")
        return cls(host=data["host"], port=data["port"], configuration_reviewed=data["configuration_reviewed"],
                   rotation=transform["rotation"], translation_mm=transform["translation_mm"],
                   tip_mode=tip["mode"], min_sensor_mm=tip.get("min_sensor_mm"), max_sensor_mm=tip.get("max_sensor_mm"),
                   **{key: data[key] for key in ("timeout_s", "open_timeout_s", "max_frame_age_s", "frame_period_s") if key in data})


def load_lyra_config(path: str | Path) -> LyraConfig:
    with Path(path).open(encoding="utf-8") as stream:
        return LyraConfig.from_dict(json.load(stream))


@dataclass(frozen=True)
class LyraFrame:
    """Backend frame: raw sensor-frame mm, 32-bit frame ID, monotonic acquisition."""
    markers_mm: tuple[tuple[float, float, float], ...]
    frame_number: int
    timestamp_s: float
    system_status: int = 0


class LyraBackend(Protocol):
    """Inject a synthetic backend for tests; no vendor SDK is then needed."""
    def open(self, config: LyraConfig) -> None: ...
    def read_frame(self) -> LyraFrame: ...
    def close(self) -> None: ...


class _NativeConnection:
    """SDK calls, used only inside the worker (or with an injected test SDK)."""
    def __init__(self, config, *, sdk=None, clock=time.monotonic):
        self.config, self.sdk, self.clock = config, sdk, clock
        self.device = None
        self.handle = None
        self.tracking = False

    def _command(self, command):
        response = self.sdk.ndiCommand(self.device, command)
        error = int(self.sdk.ndiGetError(self.device))
        if error:
            raise LyraError(f"NDI command {command.split(':')[0]} failed (code {error})")
        if not response:
            raise LyraError(f"NDI command {command.split(':')[0]} returned no response")
        return response

    def open(self):
        if self.sdk is None:
            try:
                self.sdk = import_module("ndicapy")
            except ImportError as exc:
                raise LyraError("Lyra requires the optional ndicapi package; install opentdcr[lyra]") from exc
        required = ("ndiOpenNetwork", "ndiCloseNetwork", "ndiCommand", "ndiGetError", "ndiGetPHRQHandle", "ndiGetTXFrame", "ndiGetTXNumberOfPassiveStrays", "ndiGetTXPassiveStray", "ndiGetTXSystemStatus")
        if any(not callable(getattr(self.sdk, name, None)) for name in required):
            raise LyraError("ndicapy build lacks required native TX/passive-marker APIs")
        try:
            self.device = self.sdk.ndiOpenNetwork(self.config.host, self.config.port)
            if self.device is None:
                raise LyraError("cannot open the configured Lyra network connection")
            timeout = getattr(self.sdk, "ndiTimeoutSocket", None)
            if callable(timeout):
                timeout(self.device, max(1, math.ceil(self.config.timeout_s * 1000)))
            self._command("INIT:")
            self._command("PHRQ:*********1**01")
            handle = self.sdk.ndiGetPHRQHandle(self.device)
            # The Python TX-frame wrapper accepts a single byte as signed C char.
            if type(handle) is not int or not 1 <= handle <= 127:
                raise LyraError("NDI did not allocate a supported passive tracking handle")
            self.handle = handle
            self._command(f"PENA:{handle:02X}D")
            self._command("TSTART:80")
            self.tracking = True
        except BaseException:
            try:
                self.close()
            except Exception:
                pass
            raise

    def read_frame(self):
        if self.device is None or not self.tracking:
            raise LyraError("Lyra connection is not open")
        requested = self.clock()
        # Request in-volume passive markers only; never parse ad-hoc TX strings.
        self._command("TX:1001")
        frame = self.sdk.ndiGetTXFrame(self.device, bytes([self.handle]))
        count = self.sdk.ndiGetTXNumberOfPassiveStrays(self.device)
        if type(count) is not int or not 0 <= count < 50:
            raise LyraError("invalid or saturated passive marker count")
        markers = tuple(self.sdk.ndiGetTXPassiveStray(self.device, index) for index in range(count))
        status = int(self.sdk.ndiGetTXSystemStatus(self.device))
        return LyraFrame(markers, frame, requested - self.config.frame_period_s, status)

    def close(self):
        device, self.device = self.device, None
        if device is None:
            return
        try:
            if self.tracking:
                self.sdk.ndiCommand(device, "TSTOP:")
        finally:
            self.tracking = False
            self.sdk.ndiCloseNetwork(device)


def _native_worker(channel, config):
    connection = _NativeConnection(config)
    try:
        connection.open()
        channel.send(("ok", None))
        while True:
            request = channel.recv()
            if request == "read":
                channel.send(("ok", connection.read_frame()))
            elif request == "close":
                connection.close()
                channel.send(("ok", None))
                return
            else:
                raise LyraError("invalid Lyra worker request")
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            channel.send(("error", f"{type(exc).__name__}: {exc}"))
        except (EOFError, BrokenPipeError, OSError):
            pass
    finally:
        try:
            connection.close()
        except Exception:
            pass
        channel.close()


class _ProcessBackend:
    def __init__(self, *, worker_target=_native_worker):
        self._worker_target = worker_target
        self._process = None
        self._channel = None
        self._timeout = 0.2

    def _reply(self, timeout):
        try:
            if not self._channel.poll(timeout):
                raise LyraError(f"Lyra I/O timed out after {timeout:g} seconds")
            result, payload = self._channel.recv()
            if result != "ok":
                raise LyraError(str(payload))
            return payload
        except (EOFError, BrokenPipeError, OSError) as exc:
            self._abort()
            raise LyraError("Lyra worker disconnected") from exc
        except BaseException:
            self._abort()
            raise

    def open(self, config):
        self._timeout = config.timeout_s
        context = multiprocessing.get_context("spawn")
        self._channel, child = context.Pipe()
        self._process = context.Process(target=self._worker_target, args=(child, config), daemon=True)
        try:
            self._process.start()
            child.close()
            self._reply(config.open_timeout_s)
        except BaseException:
            child.close()
            self._abort()
            raise

    def read_frame(self):
        if self._channel is None:
            raise LyraError("Lyra worker is closed")
        try:
            self._channel.send("read")
            return self._reply(self._timeout)
        except (EOFError, BrokenPipeError, OSError) as exc:
            self._abort()
            raise LyraError("Lyra worker disconnected") from exc

    def _abort(self):
        process, self._process = self._process, None
        channel, self._channel = self._channel, None
        if channel is not None:
            channel.close()
        if process is not None and process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(0.1)
            if process.is_alive():
                process.kill()
                process.join(0.1)
            if not process.is_alive():
                process.close()

    def close(self):
        try:
            if self._channel is not None:
                self._channel.send("close")
                self._reply(self._timeout)
        except (LyraError, EOFError, BrokenPipeError, OSError):
            pass
        finally:
            self._abort()


class LyraSensor:
    """One explicitly identified tip, transformed using a reviewed fixed frame.

    ``exactly_one`` requires one visible marker in the entire tracker volume.
    ``roi`` requires one visible marker within explicit sensor-frame bounds. An
    ROI is spatial isolation, not a persistent marker ID: the operator must keep
    other markers out of it. Missing/ambiguous markers never fall back to list
    order, previous points, or a cached reference. Any read failure closes the
    source; create a new instance only after resolving the cause. Repeated fresh
    camera frames return the same measurement and original acquisition timestamp.
    """
    def __init__(self, config: LyraConfig, *, backend: LyraBackend | None = None,
                 clock: Callable[[], float] = time.monotonic):
        if not isinstance(config, LyraConfig):
            raise TypeError("config must be LyraConfig")
        self.config, self._backend, self._clock = config, backend, clock
        self._opened = False
        self._closed = False
        self._last_frame = None
        self._last_timestamp = None
        self._last_markers = None
        self._last_sample = None

    def open(self):
        if self._closed:
            raise LyraError("Lyra source is closed; create a new source to reconnect")
        if self._opened:
            return self
        if not self.config.configuration_reviewed:
            raise ValueError("review the tracker host, tip isolation, frame period and sensor_to_base transform; then set configuration_reviewed=true in a local config")
        if self._backend is None:
            self._backend = _ProcessBackend()
        try:
            self._backend.open(self.config)
            self._opened = True
        except BaseException:
            self.close()
            raise
        return self

    def _measurement(self, frame, now):
        if not isinstance(frame, LyraFrame):
            raise LyraError("Lyra backend must return LyraFrame")
        if type(frame.frame_number) is not int or not 0 < frame.frame_number < 2**32:
            raise LyraError("Lyra frame counter is missing or invalid")
        if type(frame.system_status) is not int or frame.system_status != 0:
            raise LyraError("Lyra reported a nonzero or invalid system status")
        if not isinstance(frame.markers_mm, (tuple, list)) or len(frame.markers_mm) >= 50:
            raise LyraError("invalid or saturated Lyra marker list")
        all_markers = tuple(_point(marker, "Lyra marker") for marker in frame.markers_mm)
        if self._last_frame is not None:
            advance = (frame.frame_number - self._last_frame) % 2**32
            if advance == 0:
                if all_markers != self._last_markers:
                    raise LyraError("Lyra repeated frame contains changed marker data")
                # Repeated polls are normal between camera exposures. Preserve
                # acquisition time exactly; returning cached data cannot renew it.
                return validate_measurement(self._last_sample, self.config.max_frame_age_s, now_s=now)
            if advance >= 2**31:
                raise LyraError("Lyra frame counter moved backwards")
        timestamp = _finite(frame.timestamp_s, "Lyra timestamp_s")
        if self._last_timestamp is not None and timestamp <= self._last_timestamp:
            raise LyraError("Lyra acquisition timestamp did not advance")
        markers = all_markers
        if self.config.tip_mode == "roi":
            markers = tuple(point for point in markers if all(low <= value <= high for value, low, high in zip(point, self.config.min_sensor_mm, self.config.max_sensor_mm)))
        if len(markers) != 1:
            raise LyraError(f"tip selection requires exactly one visible marker; found {len(markers)}")
        position = np.asarray(self.config.rotation) @ np.asarray(markers[0]) + np.asarray(self.config.translation_mm)
        sample = PositionMeasurement(tuple(float(x) for x in position), timestamp, frame="robot_base")
        validate_measurement(sample, self.config.max_frame_age_s, now_s=now)
        self._last_frame, self._last_timestamp = frame.frame_number, timestamp
        self._last_markers, self._last_sample = all_markers, sample
        return sample

    def read(self) -> PositionMeasurement:
        if not self._opened or self._closed:
            raise LyraError("Lyra source is not open")
        requested = self._clock()
        try:
            frame = self._backend.read_frame()
            now = self._clock()
            if now < requested or now - requested > self.config.timeout_s:
                raise LyraError("Lyra acquisition exceeded the configured read timeout")
            return self._measurement(frame, now)
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed, self._opened = True, False
        if self._backend is not None:
            try:
                self._backend.close()
            except Exception:
                pass

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()


def create_lyra_sensor(config_path: str | Path, *, backend: LyraBackend | None = None,
                       clock: Callable[[], float] = time.monotonic) -> LyraSensor:
    """Explicitly load a local configuration and open its optional Lyra source."""
    return LyraSensor(load_lyra_config(config_path), backend=backend, clock=clock).open()
