"""Replace the acquisition boundary with your tracking device.

This runnable example returns synthetic data and deliberately inherits MockSensor
so the CLI refuses to use it as a real hardware gate. Your implementation should
implement MeasurementSource directly, not inherit MockSensor.

    python -m opentdcr sensor --sensor examples.sensor_adapter:create_sensor --samples 5
"""
import time
from opentdcr.sensors import MockSensor, PositionMeasurement


class ExampleSensor(MockSensor):
    def read(self):
        # Real adapter: acquire a NEW sample (or preserve cached acquisition time),
        # convert metres to mm as needed, and transform into robot_base axes.
        # Return valid=False or raise if tracking is lost. Bound SDK read timeout;
        # the teleoperation loop cannot interrupt a blocking Python sensor call.
        return PositionMeasurement(
            position_mm=(0.0, 0.0, 100.0),
            timestamp_s=time.monotonic(),
            frame="robot_base",
            valid=True,
        )

    def close(self):
        # Stop your stream and close your SDK connection here.
        pass


def create_sensor():
    return ExampleSensor()
