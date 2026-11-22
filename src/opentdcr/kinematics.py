"""Linear Clark-coordinate tendon map for parallel routing through proximal segments.

Coordinates have millimetre units: segment tendon radius times bending angle.
Positive tendon displacement follows the configured positive servo direction.
This is a geometric command map, not a forward dynamics or contact model.
"""
import numpy as np
from .config import RobotConfig


class TendonKinematics:
    def __init__(self, config: RobotConfig):
        self.config = config
        self.limit_mm = np.array(config.tendon_radius_mm) * config.max_bend_rad
        self.maps = []
        self.slices = []
        start = 0
        for n, offset in zip(config.tendons_per_segment, config.tendon_angle_offset_rad):
            angles = offset + np.arange(n) * 2 * np.pi / n
            self.maps.append(np.column_stack((np.cos(angles), np.sin(angles))))
            self.slices.append(slice(start, start+n))
            start += n

    def coordinates(self, values):
        values = np.asarray(values, dtype=float)
        if values.shape != (self.config.n_segments, 2) or not np.isfinite(values).all():
            raise ValueError(f"coordinates must be finite with shape ({self.config.n_segments}, 2)")
        return values

    def clamp(self, values):
        values = self.coordinates(values).copy()
        lengths = np.linalg.norm(values, axis=1)
        scale = np.minimum(1.0, self.limit_mm / np.maximum(lengths, 1e-30))
        return values * scale[:, None]

    def to_tendons(self, values):
        values = self.coordinates(values)
        radii = np.array(self.config.tendon_radius_mm)
        # Distal tendon groups traverse every proximal segment. Their radius is
        # assumed constant along that route; scale proximal bending accordingly.
        integrated_bend = np.cumsum(values / radii[:, None], axis=0)
        return np.concatenate([mapping @ (bend * radius) for mapping, bend, radius in
                               zip(self.maps, integrated_bend, radii)])

    def from_tendons(self, values):
        values = np.asarray(values, dtype=float)
        if values.shape != (self.config.n_tendons,) or not np.isfinite(values).all():
            raise ValueError(f"tendons must be {self.config.n_tendons} finite values")
        radii = np.array(self.config.tendon_radius_mm)
        integrated_bend = np.array([(2 / len(mapping)) * mapping.T @ values[sl] / radius
                                   for mapping, sl, radius in zip(self.maps, self.slices, radii)])
        # Projects away common-mode tendon stretch; cannot recover axial extension.
        return np.diff(integrated_bend, axis=0, prepend=np.zeros((1, 2))) * radii[:, None]
