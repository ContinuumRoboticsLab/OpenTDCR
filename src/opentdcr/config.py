"""Strict, unit-labelled configuration. Example motor maps are not calibrations."""
from dataclasses import dataclass
import json
import math
from pathlib import Path


def _number(value, label, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    if positive and value <= 0:
        raise ValueError(f"{label} must be positive")
    return float(value)


def _integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer in [{low}, {high}]")
    return value


@dataclass(frozen=True)
class RobotConfig:
    name: str
    tendons_per_segment: tuple[int, ...]
    tendon_radius_mm: tuple[float, ...]
    tendon_angle_offset_rad: tuple[float, ...]
    max_bend_rad: tuple[float, ...]
    servo_ids: tuple[int, ...]
    spool_radius_mm: tuple[float, ...]
    servo_direction: tuple[int, ...]
    max_tendon_travel_mm: float = 10.0
    max_tendon_speed_mm_s: float = 2.0
    keyboard_step_mm: float = 0.1
    baudrate: int = 3000000
    hardware_reviewed: bool = False
    sensor_max_age_s: float = 0.25

    def __post_init__(self):
        for key in ("tendons_per_segment", "tendon_radius_mm", "tendon_angle_offset_rad",
                    "max_bend_rad", "servo_ids", "spool_radius_mm", "servo_direction"):
            try:
                object.__setattr__(self, key, tuple(getattr(self, key)))
            except TypeError as exc:
                raise ValueError(f"{key} must be a sequence") from exc
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be non-empty")
        if not self.tendons_per_segment:
            raise ValueError("at least one segment is required")
        for n in self.tendons_per_segment:
            _integer(n, "tendons_per_segment", 3, 32)
        ns, nt = len(self.tendons_per_segment), sum(self.tendons_per_segment)
        for key in ("tendon_radius_mm", "tendon_angle_offset_rad", "max_bend_rad"):
            if len(getattr(self, key)) != ns:
                raise ValueError(f"{key} requires one value per segment")
        for key in ("servo_ids", "spool_radius_mm", "servo_direction"):
            if len(getattr(self, key)) != nt:
                raise ValueError(f"{key} requires {nt} values, ordered base to tip")
        for value in self.servo_ids:
            _integer(value, "servo_ids", 0, 252)
        if len(set(self.servo_ids)) != nt:
            raise ValueError("servo_ids must be unique")
        for value in self.servo_direction:
            if type(value) is not int or value not in (-1, 1):
                raise ValueError("servo_direction entries must be -1 or 1")
        for key in ("tendon_radius_mm", "spool_radius_mm", "max_bend_rad"):
            for value in getattr(self, key):
                _number(value, key, positive=True)
        for value in self.tendon_angle_offset_rad:
            _number(value, "tendon_angle_offset_rad")
        for key in ("max_tendon_travel_mm", "max_tendon_speed_mm_s", "keyboard_step_mm", "sensor_max_age_s"):
            _number(getattr(self, key), key, positive=True)
        if self.keyboard_step_mm > self.max_tendon_travel_mm:
            raise ValueError("keyboard_step_mm must not exceed max_tendon_travel_mm")
        if self.baudrate not in (9600, 57600, 115200, 1000000, 2000000, 3000000, 4000000, 4500000):
            raise ValueError("baudrate is not supported by XL430-W250")
        if type(self.hardware_reviewed) is not bool:
            raise ValueError("hardware_reviewed must be true or false")

    @property
    def n_segments(self):
        return len(self.tendons_per_segment)

    @property
    def n_tendons(self):
        return sum(self.tendons_per_segment)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("configuration must be a JSON object")
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown configuration fields: {', '.join(sorted(unknown))}")
        array_fields = ("tendons_per_segment", "tendon_radius_mm", "tendon_angle_offset_rad",
                        "max_bend_rad", "servo_ids", "spool_radius_mm", "servo_direction")
        converted = dict(data)
        for key in array_fields:
            if key not in data or not isinstance(data[key], list):
                raise ValueError(f"{key} must be a JSON array")
            converted[key] = tuple(data[key])
        try:
            return cls(**converted)
        except TypeError as exc:
            raise ValueError(f"invalid configuration: {exc}") from exc


def load_config(path: str | Path) -> RobotConfig:
    with Path(path).open(encoding="utf-8") as handle:
        return RobotConfig.from_dict(json.load(handle))
