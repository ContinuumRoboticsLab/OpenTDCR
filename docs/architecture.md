# Architecture

OpenTDCR separates robot geometry, user input, actuator communication, and measurement acquisition. All hardware access is explicit; importing the package does not open a serial port or enable a motor.

```text
JSON robot configuration
         │
Keyboard / USB DualSense → segment Clark coordinates → relative tendon targets
                                                   │
                                   DryRunTransport or DynamixelTransport

Optional MeasurementSource → validity/freshness checks around motion
```

## Modules

| Module | Responsibility |
| --- | --- |
| `opentdcr.calibration` | Sensor-independent threshold/countback calibration and session-reference report |
| `opentdcr.adapters.lyra` | Optional NDI Lyra acquisition and explicit marker/frame conversion |
| `opentdcr.config` | Parse and validate a unit-labelled robot configuration |
| `opentdcr.kinematics` | Map segment coordinates to coupled tendon displacement and back |
| `opentdcr.teleop` | Selected segment, command integration, bounds, and measurement checks |
| `opentdcr.transport` | Dry-run behavior and explicit XL430 servo lifecycle |
| `opentdcr.sensors` | Timestamped point measurements, validation, and explicit adapter loading |
| `opentdcr.gamepad` | Optional standard wired DualSense reports, freshness, and hold-to-move checks |
| `opentdcr.cli` | `inspect`, `teleop`, `sensor`, and `calibrate` entry points |

## Tendon coordinates

Each segment has two Clark coordinates measured in millimetres. Their magnitude represents tendon radius times bend angle under the geometric assumption used by the command map. For evenly spaced tendons with angular positions `theta_i`, a segment's inverse map projects those two coordinates using `cos(theta_i)` and `sin(theta_i)`.

A distal tendon passes through proximal segments as well as its own. The map accumulates proximal bend contributions and scales them by the distal tendon group's radius. It assumes parallel routing with a constant radius for each tendon group along that route. Mixed-radius groups are supported under this assumption; arbitrary radius profiles, helical routing, axial extension, slack, friction, and elastic coupling require a different model.

The reverse transform projects away common-mode tendon changes. It cannot recover axial extension or prove that a measured robot has the commanded shape. This module is a geometric command map, not forward mechanics, dynamics, or contact simulation.

## State and limits

A `TeleopSession` holds the selected segment and coordinate target. Commands update that target, apply segment bend bounds, and validate tendon travel before dispatch. The transport handles actuator state and cleanup. Configuration validation rejects malformed inputs before hardware is opened.

The default dry-run transport uses the same command mapping without a device. The hardware path requires a reviewed local config, an explicit port, a home acknowledgment, and an interactive terminal. Its current register contract targets XL430-W250 servos. It verifies their preconfigured mode, drive mode, status return level, secondary ID, and watchdog; then it reads current positions, sets initial targets/profile, and enables torque.

Standalone teleoperation uses the physical posture at startup as its reference. The calibration path first uses that starting reference to loosen and probe each tendon, then applies countback references, accepts common operator adjustments, and captures a new zero. Its optional report records parameters, observations, and offsets; those saved values are never automatically restored after a power cycle. The keyboard interface waits for discrete commands; it does not maintain a background servo watchdog or sensor loop. The optional USB DualSense interface uses a report-reader thread and checks fresh input and sensor data between bounded moves and while a move is monitored. L1 is required for motion; releasing it during a move ends the session.

## Calibration lifecycle

The calibration core depends on a transport and `MeasurementSource`, with callbacks for operator interaction and progress. It loosens all tendons, pauses for the operator to settle the robot, records a baseline, and probes one tendon at a time while the others remain loose. At a threshold crossing, it records actual actuator readback and subtracts a configured tendon-length countback. It loosens again before the next probe, applies the complete set of references, accepts common manual increments, and captures a new zero only after successful completion.

Robot settings and calibration settings are separate JSON files. Per-tendon threshold, loosen, and countback values can be scalar or vectors in servo order. Bounded steps, time limits, sensor validation, and transport travel limits are enforced during the search. A failed or incomplete search does not establish a valid reference. See [calibration](calibration.md) for parameter units and commands.

The Lyra adapter lives behind the same measurement contract as user-supplied sensors. Its connection settings, marker-selection policy, and sensor-to-base transform belong in a reviewed local config. Calibration does not depend on Lyra, ROS, a camera model, or a particular SDK.

## Extending the package

Add a measurement device by implementing the [measurement contract](measurements.md). Keep unit conversion, frame transforms, acquisition timestamps, and tracking validity at that boundary. Teleoperation uses sensor data as an optional health gate. Calibration uses the same validated position samples to determine when an individual tendon reaches a configured displacement threshold. A closed-loop shape controller needs its own design and validation.

For another actuator, define and test a backend with the same lifecycle and target semantics. Include failure injection for partial initialization, communication errors, and cleanup. Do not reuse the XL430 control table for another model without verifying it.

For a new robot geometry, first implement and test the tendon mapping without hardware. Add a measured configuration with explicit provenance, then validate it physically. Gripper, translation, and arm commands are not part of the generic bending interface in this release.

## Validation scope

The unit suite runs on synthetic data and fake hardware. It checks behavior without serial devices, trackers, or motors. Hardware correctness additionally depends on the actual assembly, wiring, servo firmware, sensor timing, and operating limits. Those physical checks remain in the [release checklist](release-checklist.md).
