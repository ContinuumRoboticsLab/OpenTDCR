"""OpenTDCR: hardware-independent kinematics and explicit hardware sessions."""
from .config import RobotConfig, load_config
from .kinematics import TendonKinematics
from .sensors import MeasurementSource, PositionMeasurement, validate_measurement
from .calibration import CalibrationConfig, CalibrationResult, calibrate, load_calibration_config

__version__ = "0.1.0"
__all__ = ["RobotConfig", "load_config", "TendonKinematics", "MeasurementSource",
           "PositionMeasurement", "validate_measurement", "CalibrationConfig",
           "CalibrationResult", "calibrate", "load_calibration_config"]
