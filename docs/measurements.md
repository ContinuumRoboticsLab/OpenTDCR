# Measurement sensors and calibration

The public package provides a small measurement interface so users can connect their own sensor without editing the teleoperation or kinematics code. It ships with a synthetic source, a runnable adapter example, and an optional Lyra adapter. The [calibration workflow](calibration.md) uses this same interface for its displacement thresholds; no tracker-specific logic belongs in the calibration core.

## The contract

An adapter implements `read()` and `close()` from `opentdcr.sensors.MeasurementSource`. Each read returns:

```python
from opentdcr.sensors import PositionMeasurement

sample = PositionMeasurement(
    position_mm=(x_mm, y_mm, z_mm),
    timestamp_s=acquisition_time_on_host_monotonic_clock,
    frame="robot_base",
    valid=True,
)
```

| Value | Required interpretation |
| --- | --- |
| `position_mm` | Three finite coordinates, in millimetres, for a consistently identified measured point |
| `timestamp_s` | Acquisition time mapped to the host's `time.monotonic()` clock |
| `frame` | Exactly `robot_base`, after applying your measured sensor-to-base transform |
| `valid` | `True` only when the sample is usable; false or an exception for lost tracking |

Define and record your base frame's origin, axes, handedness, and measured-point attachment. The label alone does not define that transform. If you start with metres, multiply by 1000 before returning the sample. If you measure a marker offset from the point of interest, account for that rigid transform and its orientation requirements in your adapter.

A cached sample must retain its original acquisition timestamp. Calibration health checks can accept it while fresh, but baseline/threshold decisions wait for acquisition after the operator step/completed motion, with a bounded timeout. Calling `time.monotonic()` when returning an old observation defeats stale-data detection. For devices with their own clocks, estimate and validate the clock mapping; record its uncertainty. Future timestamps are also rejected.

`read()` must return promptly. Configure a finite timeout in the vendor SDK or maintain a nonblocking sample buffer. The synchronous teleoperation loop cannot interrupt an adapter stuck in a blocking vendor call. `close()` should release device resources and tolerate repeated calls.

The generic loader accepts an explicit, trusted `module:factory` string; the CLI also provides an optional `lyra` adapter selected with its own reviewed configuration. The module is ordinary Python code and runs with the process's permissions. There is no automatic plugin discovery.

## Try the adapter boundary

From the repository root:

```sh
python -m opentdcr sensor --sensor examples.sensor_adapter:create_sensor --samples 5
```

Use `python -m opentdcr` for this repository-local example so the current directory is on Python’s module search path. The `tdcr` console command works with adapter modules installed in your environment.

The example deliberately inherits `MockSensor`, returns synthetic positions, and is rejected as a physical-hardware measurement gate. For a real adapter, implement `MeasurementSource` directly and return actual device data. Keep vendor dependencies in your integration environment.

Before connecting actuators, test valid data, units, frame orientation, stationary noise, dropped tracking, stale cached data, device disconnects, and cleanup. Then exercise the same adapter in dry-run teleoperation:

```sh
tdcr teleop --config configs/three_segment.example.json --sensor my_lab.sensor:create_sensor
```

## What measurements do during teleoperation

If a sensor is supplied, the session validates it before motor startup, before a motion command, and while a hardware move is being monitored. Invalid, nonfinite, wrong-frame, stale, or future-dated samples are rejected. Sensor exceptions propagate to resource cleanup.

During teleoperation, the position value is not used to compute a corrective command. This is an availability check on the configured measurement source, not closed-loop control, shape validation, tension estimation, collision detection, or a certified safety system. Keyboard mode does not poll measurements while the terminal is waiting for input. Gamepad mode checks the sensor on each input loop, including while idle; it still cannot interrupt a blocked vendor call.

## Four different calibration tasks

1. **Mechanical reference and pretension.** Verify tendon winding directions, prepare a usable starting posture, then run the [calibration sequence](calibration.md) with thresholds/countbacks appropriate to your build, or establish pretension manually. The calibration loop observes tip displacement; it does not measure force.
2. **Encoder zero.** Capture current servo positions relative to the established posture. Standalone teleoperation records its acknowledged starting posture. Successful calibration records a new zero after applying all tendon references and operator adjustments. A saved report is not an instruction to restore old ticks after a power cycle.
3. **Sensor frame and timing.** Calibrate the transform, units, marker offsets, and clock relationship that make measurements comparable between runs.
4. **Model identification.** Estimate geometry, stiffness, friction, or other simulation parameters for a specific study. Those parameters belong to the chosen model and experiment, not to a generic sensor adapter.

Record these separately, together with hardware revision, servo configuration, tendon routing, test date, and the measurement method. Do not reuse lab-specific transforms or motor offsets on another assembly without remeasurement.

The related simulator has its own [system-identification pipeline](https://github.com/ContinuumRoboticsLab/opencr-mujoco). Using that pipeline does not replace mechanical setup of this hardware. The public calibration implementation retains the lab's loosen, measure, pull-to-threshold, countback, and common-adjustment sequence. Its generic sensor contract and configuration support adaptation to other measurement devices; physical validation is still required for each build.
