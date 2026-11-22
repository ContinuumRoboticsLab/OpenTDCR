"""Bounded command-step teleoperation, independent of the input device."""
import numpy as np
from .config import RobotConfig
from .kinematics import TendonKinematics
from .sensors import validate_measurement


class TeleopSession:
    def __init__(self, config: RobotConfig, transport, sensor=None):
        self.config, self.transport, self.sensor = config, transport, sensor
        self.kinematics = TendonKinematics(config)
        self.coordinates_mm = np.zeros((config.n_segments, 2))
        self.segment = 0
        self.last_measurement = None
        self.motion_guard = None

    def check_sensor(self):
        if self.sensor is not None:
            self.last_measurement = validate_measurement(self.sensor.read(), self.config.sensor_max_age_s)

    def check_motion(self):
        self.check_sensor()
        if self.motion_guard is not None:
            self.motion_guard()

    def step(self, direction):
        """Take at most one configured step from a normalized 2-D input."""
        direction = np.asarray(direction, dtype=float)
        if direction.shape != (2,) or not np.isfinite(direction).all() or np.linalg.norm(direction) > 1+1e-9:
            raise ValueError("direction must be a finite 2-D vector of norm at most one")
        desired = self.coordinates_mm.copy()
        desired[self.segment] += direction * self.config.keyboard_step_mm
        return self._move(desired)

    def _move(self, desired):
        desired = self.kinematics.clamp(desired)
        target = self.kinematics.to_tendons(desired)
        self.transport.move(target, check=self.check_motion)
        self.coordinates_mm = desired
        return target.copy()

    def command(self, command: str):
        """Return target or None. Invalid input never writes to the transport."""
        command = command.strip().lower()
        if command.isdigit():
            selected = int(command) - 1
            if not 0 <= selected < self.config.n_segments:
                raise ValueError("segment number is out of range")
            self.segment = selected
            return None
        directions = {"w": (0, 1), "s": (0, -1), "a": (-1, 0), "d": (1, 0)}
        if command == "home":
            desired = np.zeros_like(self.coordinates_mm)
        elif command in directions:
            desired = self.coordinates_mm.copy()
            desired[self.segment] += np.array(directions[command]) * self.config.keyboard_step_mm
        else:
            raise ValueError("use w/a/s/d, a segment number, home, or q")
        return self._move(desired)
