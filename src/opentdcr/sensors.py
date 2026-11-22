"""Small measurement boundary; sensor drivers stay in the integrating project."""
from dataclasses import dataclass
from importlib import import_module
import math
import time
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PositionMeasurement:
    """One measured point in robot_base, millimetres, host monotonic seconds.

    timestamp_s is the acquisition time mapped to time.monotonic(), not the time
    an old cached sample was returned. Transform sensor axes before constructing.
    """
    position_mm: tuple[float, float, float]
    timestamp_s: float
    frame: str = "robot_base"
    valid: bool = True


@runtime_checkable
class MeasurementSource(Protocol):
    def read(self) -> PositionMeasurement:
        """Return latest sample promptly; raise on device or tracking failure."""
        ...

    def close(self) -> None:
        """Release sensor resources; tolerate repeated calls."""
        ...


def validate_measurement(sample: PositionMeasurement, max_age_s: float = 0.25,
                         *, now_s: float | None = None) -> PositionMeasurement:
    if not isinstance(sample, PositionMeasurement):
        raise ValueError("sensor must return PositionMeasurement")
    if sample.valid is not True or sample.frame != "robot_base":
        raise ValueError("sensor tracking invalid or frame is not robot_base")
    try:
        if len(sample.position_mm) != 3 or not all(math.isfinite(float(v)) for v in sample.position_mm):
            raise ValueError("position_mm requires three finite coordinates")
        if not math.isfinite(sample.timestamp_s) or not math.isfinite(max_age_s) or max_age_s <= 0:
            raise ValueError("invalid measurement timestamp or age limit")
    except (TypeError, OverflowError) as exc:
        raise ValueError("invalid sensor data") from exc
    now = time.monotonic() if now_s is None else now_s
    age = now - sample.timestamp_s
    if age < 0 or age > max_age_s:
        raise ValueError(f"sensor timestamp outside freshness window (age={age:.3f}s)")
    return sample


class MockSensor:
    """A fresh stationary synthetic point; never a real tracking device."""
    def read(self):
        return PositionMeasurement((0.0, 0.0, 0.0), time.monotonic())

    def close(self):
        pass


def load_sensor(spec: str) -> MeasurementSource:
    """Import an explicitly requested, trusted module:factory; no auto-discovery."""
    module, separator, factory_name = spec.partition(":")
    if not separator or not module or not factory_name or ":" in factory_name:
        raise ValueError("sensor must be a trusted module:factory reference")
    sensor = getattr(import_module(module), factory_name)()
    if not isinstance(sensor, MeasurementSource):
        close = getattr(sensor, "close", None)
        if callable(close):
            close()
        raise ValueError("sensor must implement read() and close()")
    return sensor
