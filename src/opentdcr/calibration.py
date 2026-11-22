"""Sensor-independent tip-displacement threshold calibration.

This preserves the lab's Lyra loosen/pull/countback procedure behind a generic
measurement interface. Related work: Kyum Lee, Chengnan Shentu, Chloe Pogue, and
Jessica Burgner-Kahrs, "Automating Tension Calibration for Tendon-Driven Continuum
Robots: A Low-Cost Approach Towards Consistent Teleoperation," ICRA 2025,
https://doi.org/10.1109/ICRA55743.2025.11128689.

This displacement-threshold adaptation does not implement the paper's force
estimation or establish a known tendon tension. Parameters require validation
on the physical robot. Sensor/transport reads must themselves have bounded I/O.
"""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import time

import numpy as np

from .config import RobotConfig
from .sensors import validate_measurement


def _finite(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return float(value)


@dataclass(frozen=True)
class CalibrationConfig:
    """Distances are mm; durations are seconds; vectors follow servo_ids order."""
    loosen_amount_mm: tuple[float, ...]
    movement_threshold_mm: tuple[float, ...]
    movement_countback_mm: tuple[float, ...]
    pull_step_mm: float = 0.05
    max_pull_mm: float = 2.0
    search_start_mm: float = -1.0
    settle_s: float = 0.05
    tendon_timeout_s: float = 30.0

    def __post_init__(self):
        for name in ("loosen_amount_mm", "movement_threshold_mm", "movement_countback_mm"):
            try:
                values = tuple(getattr(self, name))
            except TypeError as exc:
                raise ValueError(f"{name} must be a sequence; use from_dict for scalar broadcast") from exc
            if not values:
                raise ValueError(f"{name} must not be empty")
            values = tuple(_finite(value, name, positive=name != "movement_countback_mm",
                                   nonnegative=name == "movement_countback_mm") for value in values)
            object.__setattr__(self, name, values)
        lengths = {len(getattr(self, name)) for name in
                   ("loosen_amount_mm", "movement_threshold_mm", "movement_countback_mm")}
        if len(lengths) != 1:
            raise ValueError("calibration vectors must have equal lengths")
        for name in ("pull_step_mm", "max_pull_mm", "tendon_timeout_s"):
            object.__setattr__(self, name, _finite(getattr(self, name), name, positive=True))
        object.__setattr__(self, "search_start_mm", _finite(self.search_start_mm, "search_start_mm"))
        object.__setattr__(self, "settle_s", _finite(self.settle_s, "settle_s", nonnegative=True))
        if self.max_pull_mm <= max(0.0, self.search_start_mm):
            raise ValueError("max_pull_mm must exceed zero and search_start_mm")
        if self.pull_step_mm > self.max_pull_mm - max(0.0, self.search_start_mm):
            raise ValueError("pull_step_mm exceeds the search interval")
        if any(self.search_start_mm < -loosen for loosen in self.loosen_amount_mm):
            raise ValueError("search_start_mm must not be looser than the initial loose positions")

    def validate_for(self, robot: RobotConfig):
        if len(self.loosen_amount_mm) != robot.n_tendons:
            raise ValueError(f"calibration requires {robot.n_tendons} values per vector")
        limit = robot.max_tendon_travel_mm
        if (any(value > limit for value in self.loosen_amount_mm)
                or abs(self.search_start_mm) > limit or self.max_pull_mm > limit):
            raise ValueError("calibration targets exceed robot max_tendon_travel_mm")
        if any(value > 2 * limit for value in self.movement_countback_mm):
            raise ValueError("movement_countback_mm exceeds the robot travel interval")
        return self

    def to_dict(self):
        return {name: list(value) if isinstance(value, tuple) else value
                for name, value in self.__dict__.items()}

    @classmethod
    def from_dict(cls, data, robot: RobotConfig):
        if not isinstance(data, dict):
            raise ValueError("calibration configuration must be a JSON object")
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown calibration fields: {', '.join(sorted(unknown))}")
        values = dict(data)
        for name in ("loosen_amount_mm", "movement_threshold_mm", "movement_countback_mm"):
            if name not in values:
                raise ValueError(f"missing calibration field: {name}")
            value = values[name]
            if isinstance(value, list):
                values[name] = tuple(value)
            else:
                values[name] = (_finite(value, name),) * robot.n_tendons
        return cls(**values).validate_for(robot)


def load_calibration_config(path: str | Path, robot: RobotConfig) -> CalibrationConfig:
    with Path(path).open(encoding="utf-8") as handle:
        return CalibrationConfig.from_dict(json.load(handle), robot)


@dataclass(frozen=True)
class CalibrationResult:
    servo_ids: tuple[int, ...]
    baseline_position_mm: tuple[float, float, float]
    threshold_positions_mm: tuple[float, ...]
    threshold_displacements_mm: tuple[float, ...]
    calibrated_positions_mm: tuple[float, ...]
    manual_adjustments_mm: tuple[float, ...]
    final_positions_mm: tuple[float, ...]
    reference: dict
    calibration_config: CalibrationConfig
    elapsed_s: float

    def to_dict(self):
        return {
            "schema_version": 1,
            "status": "complete",
            "method": "tip-displacement-threshold-countback",
            "servo_ids": list(self.servo_ids),
            "baseline_position_mm": list(self.baseline_position_mm),
            "threshold_positions_mm": list(self.threshold_positions_mm),
            "threshold_displacements_mm": list(self.threshold_displacements_mm),
            "calibrated_positions_mm": list(self.calibrated_positions_mm),
            "manual_adjustments_mm": list(self.manual_adjustments_mm),
            "final_positions_mm": list(self.final_positions_mm),
            "reference": {"offsets_mm": list(self.reference["offsets_mm"]),
                          "zero_ticks": (None if self.reference["zero_ticks"] is None
                                         else list(self.reference["zero_ticks"]))},
            "calibration_config": self.calibration_config.to_dict(),
            "elapsed_s": self.elapsed_s,
        }


def calibrate(transport, sensor, config: CalibrationConfig, *, on_loosened=None,
              adjustment=None, on_progress=None, clock=time.monotonic, sleep=time.sleep):
    """Calibrate an already-open transport, leaving it open only on success.

    ``on_loosened()`` may ask the operator to perturb the loose robot and wait.
    ``adjustment(current_positions_mm)`` returns a common increment in mm, or
    None to finish; it is called repeatedly. ``on_progress(event)`` receives
    JSON-compatible progress dictionaries, never a partial calibration result.

    Every motor target is relative to the initial transport reference. All other
    tendons stay loose during a search. As in the original procedure, each tendon
    first approaches search_start_mm, then positive pulls begin one step above
    max(0, search_start_mm). Detection uses one baseline taken after perturbation.
    The actual encoder displacement at detection, not the requested target, is
    used for countback. Only a fully successful run captures the final reference.

    The per-tendon deadline includes approach, settling and search. It is checked
    by the transport's move callback as well as between operations. Blocking
    sensor/device implementations must supply their own read timeouts. Repeated
    fresh samples may satisfy health checks, but a threshold decision requires a
    sample acquired at or after that move completed. The baseline similarly
    requires acquisition after the operator callback returns. Waiting for either
    decision sample is bounded by sensor_max_age_s and the tendon deadline.
    """
    try:
        robot = transport.config
        config.validate_for(robot)
        if sensor is None:
            raise ValueError("calibration requires a measurement source")
        started = clock()
        deadline = None
        loose = -np.array(config.loosen_amount_mm, dtype=float)

        def emit(stage, **values):
            if on_progress is not None:
                on_progress({"stage": stage, **values})

        def check():
            # Evaluate time after acquisition so a slow read cannot supply a
            # falsely fresh sample or hide an expired search deadline.
            sample = sensor.read()
            now = clock()
            if deadline is not None and now >= deadline:
                raise TimeoutError("calibration tendon search timed out")
            return validate_measurement(sample, robot.sensor_max_age_s, now_s=now)

        def decision_sample(acquired_since):
            until = clock() + robot.sensor_max_age_s
            while True:
                sample = check()
                now = clock()
                if now > until:
                    raise TimeoutError("sensor decision-sample wait timed out")
                if sample.timestamp_s >= acquired_since:
                    return sample
                remaining = until - now
                if remaining <= 0:
                    raise TimeoutError("sensor did not provide a measurement acquired after the completed motion or operator step")
                sleep(min(0.01, remaining))

        def positions():
            values = np.asarray(transport.read_positions_mm(), dtype=float)
            if values.shape != (robot.n_tendons,) or not np.isfinite(values).all():
                raise ValueError("motor readback must contain one finite displacement per tendon")
            if np.any(np.abs(values) > robot.max_tendon_travel_mm + 1e-9):
                raise ValueError("motor readback exceeds robot max_tendon_travel_mm")
            return values.copy()

        def move(target):
            target = np.asarray(target, dtype=float)
            if target.shape != (robot.n_tendons,) or not np.isfinite(target).all():
                raise ValueError("calibration target must contain one finite value per tendon")
            if np.any(np.abs(target) > robot.max_tendon_travel_mm + 1e-9):
                raise ValueError("calibration target exceeds robot max_tendon_travel_mm")
            check()
            transport.move(target, check=check)
            completed_at = clock()
            until = completed_at + config.settle_s
            while True:
                check()
                remaining = until - clock()
                if remaining <= 0:
                    break
                sleep(min(0.05, remaining))
            return completed_at

        move(loose)
        emit("loosened", tendon_positions_mm=positions().tolist())
        if on_loosened is not None:
            on_loosened()
        baseline = np.array(decision_sample(clock()).position_mm, dtype=float)
        emit("baseline", position_mm=baseline.tolist())

        threshold_positions = []
        threshold_displacements = []
        calibrated_positions = []
        for index, servo_id in enumerate(robot.servo_ids):
            deadline = clock() + config.tendon_timeout_s
            target = loose.copy()
            target[index] = config.search_start_mm
            move(target)
            pull = max(0.0, config.search_start_mm)
            found = False
            while pull < config.max_pull_mm:
                next_pull = min(config.max_pull_mm, pull + config.pull_step_mm)
                if next_pull <= pull:
                    raise ValueError("pull_step_mm is too small to advance the search")
                pull = next_pull
                target[index] = pull
                completed_at = move(target)
                sample = decision_sample(completed_at)
                displacement = float(np.linalg.norm(np.array(sample.position_mm) - baseline))
                emit("search", tendon_index=index, servo_id=servo_id,
                     target_mm=pull, displacement_mm=displacement,
                     threshold_mm=config.movement_threshold_mm[index])
                if displacement >= config.movement_threshold_mm[index]:
                    actual = positions()[index]
                    zero = float(actual - config.movement_countback_mm[index])
                    if abs(zero) > robot.max_tendon_travel_mm + 1e-9:
                        raise ValueError("countback result exceeds robot max_tendon_travel_mm")
                    threshold_positions.append(float(actual))
                    threshold_displacements.append(displacement)
                    calibrated_positions.append(zero)
                    emit("threshold", tendon_index=index, servo_id=servo_id,
                         actual_position_mm=float(actual), countback_position_mm=zero)
                    found = True
                    break
            if not found:
                raise RuntimeError(f"tendon {index + 1} (servo {servo_id}) did not reach its displacement threshold")
            # The completed search deadline must not interrupt returning all
            # tendons loose; transport movement still has its own deadline.
            deadline = None
            move(loose)

        move(calibrated_positions)
        emit("applied", tendon_positions_mm=positions().tolist())
        manual_adjustments = []
        if adjustment is not None:
            while True:
                current = positions()
                increment = adjustment(current.tolist())
                if increment is None:
                    break
                increment = _finite(increment, "manual adjustment")
                move(current + increment)
                manual_adjustments.append(increment)
                emit("adjustment", increment_mm=increment, tendon_positions_mm=positions().tolist())

        check()
        final_positions = positions()
        emit("capture_reference", tendon_positions_mm=final_positions.tolist())
        check()
        elapsed_s = float(clock() - started)
        # No motor operation, callback, or sensor read follows a successful
        # capture: the returned reference is the final state of this session.
        reference = transport.capture_reference()
        return CalibrationResult(
            servo_ids=tuple(robot.servo_ids), baseline_position_mm=tuple(baseline.tolist()),
            threshold_positions_mm=tuple(threshold_positions),
            threshold_displacements_mm=tuple(threshold_displacements),
            calibrated_positions_mm=tuple(calibrated_positions),
            manual_adjustments_mm=tuple(manual_adjustments),
            final_positions_mm=tuple(final_positions.tolist()), reference=reference,
            calibration_config=config, elapsed_s=elapsed_s,
        )
    except BaseException:
        # Preserve the original failure even if shutdown itself cannot complete.
        try:
            transport.close()
        except BaseException:
            pass
        raise
