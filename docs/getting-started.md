# Getting started

Use Python 3.10 or newer. Start in the OpenTDCR release directory and create an isolated environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Windows activation is `.venv\Scripts\activate`. Core dependencies are intentionally small; the motor SDK is an optional extra.

## Inspect and run without hardware

```sh
tdcr inspect --config configs/three_segment.example.json
tdcr teleop --config configs/three_segment.example.json --commands '1 w w 2 a q'
tdcr sensor --samples 3
```

The first command validates and prints the configuration. The second prints tendon displacements using the dry-run backend. The third reads a synthetic position source without opening any motor connection.

For interactive use, omit `--commands`:

```sh
tdcr teleop --config configs/three_segment.example.json
```

| Input, followed by Enter | Effect |
| --- | --- |
| `1`, `2`, `3` | Select the corresponding segment in the example |
| `w`, `a`, `s`, `d` | One bounded step in the selected segment's two Clark coordinates |
| `home` | Request zero displacement from the session's reference |
| `q` | End the session and close resources |

This is stepwise terminal teleoperation, not a continuous keyboard or gamepad polling loop. A held key does not act as a dead-man switch. `home` is a motion request; it is not an emergency stop.

## Use a wired DualSense controller

The optional gamepad extra uses `hidapi`. Connect exactly one standard Sony DualSense by USB, with Bluetooth disconnected, then run:

```sh
python -m pip install -e '.[gamepad]'
tdcr teleop --config configs/three_segment.example.json --input dualsense
```

This remains dry-run. The accepted device is the standard DualSense (`054c:0ce6`) with its 64-byte USB report. Bluetooth, DualSense Edge, vibration, and controller LEDs are unsupported. OS HID access may require platform-specific setup.

| Control | Effect |
| --- | --- |
| L1 released at startup | Required before the session opens the transport |
| Hold L1 and move the left stick | Repeated bounded steps for the selected segment |
| D-pad up/down | Cycle the selected segment, once per press |
| Circle | End the session and request resource cleanup |
| Ctrl-C in the terminal | Interrupt the session and request cleanup |

The right stick is unused. Stick input has a central dead zone and is normalized; `keyboard_step_mm` also sets the maximum increment per gamepad step. This is a sequence of bounded moves, not a specified continuous velocity controller.

Release L1 before starting. When no move is active, releasing L1 prevents new motion and the hardware continues holding its current target. Releasing L1 **during a move** stops the session, attempts torque-off, and requires a restart. Circle, stale reports, malformed reports, or controller read errors also end the session. These software checks do not replace a physical actuator-power cutoff.

The reader uses 100 ms HID timeouts and rejects reports that have not advanced their device sequence within 0.25 seconds. The control loop validates reports and optional sensor data while idle and during motion. The controller and motor path have been tested with synthetic reports/transports; physical-device validation is still required.

For hardware, install `'.[hardware,gamepad]'` and add `--input dualsense` to the reviewed hardware command below. The same port, reference, configuration, and interactive-terminal requirements apply.

## Understand the configuration

Copy the example to a local file before adapting it. The nine-tendon example does not describe the complete supplied actuation assembly or assign its auxiliary actuators.

| Field | Meaning |
| --- | --- |
| `name` | Human-readable identity and revision for the configuration |
| `tendons_per_segment` | Number of evenly spaced bending tendons in each segment, base to tip |
| `tendon_radius_mm` | Tendon group's distance from the backbone centerline |
| `tendon_angle_offset_rad` | First tendon's angular offset in the common cross-section frame |
| `max_bend_rad` | Software bend bound for each segment |
| `servo_ids` | One unique servo ID per tendon, grouped base to tip |
| `spool_radius_mm` | Effective winding radius for each tendon |
| `servo_direction` | `1` or `-1`: sign converting positive tendon displacement to motor rotation |
| `max_tendon_travel_mm` | Absolute travel bound relative to the session reference |
| `max_tendon_speed_mm_s` | Requested tendon speed cap used to set motor profiles |
| `keyboard_step_mm` | Maximum keyboard/gamepad step size in Clark coordinates; it is not tip Cartesian displacement |
| `baudrate` | Servo bus rate |
| `hardware_reviewed` | Explicit local acknowledgment that this configuration has been checked |
| `sensor_max_age_s` | Maximum measurement age when a sensor adapter is enabled |

Segment arrays must have one entry per segment. Servo arrays must have one entry per tendon. Nonfinite values, duplicate servo IDs, unexpected fields, and invalid limits are rejected. Positive numerical limits still require physical verification; parser acceptance does not establish a safe operating envelope.

The routing model assumes each distal tendon group traverses all proximal segments at a constant radius for that group. Independently actuated, helical, variable-radius, or extensible routings need an appropriate kinematic model.

## Connect real hardware

First complete the [assembly and identification workflow](hardware.md). The current driver targets **XL430-W250** servos using Protocol 2.0. It checks the model and relevant register settings instead of silently changing the servo operating mode.

With the appropriate manufacturer setup tool and torque off, configure the intended servos for extended position mode (`4`), drive mode `0`, status return level `2`, bus watchdog `0`, and secondary ID disabled (value at least `253`). The stepwise CLI is not a continuous communication heartbeat. Confirm these settings against your servo model's [official control table](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/); the driver rejects incompatible settings. Keep a physical power cutoff available.

1. Install the optional backend: `python -m pip install -e '.[hardware]'`.
2. Copy the example to `local.robot.json` and measure the real geometry, IDs, signs, limits, and bus rate.
3. Establish the intended reference posture and manual pretension. Test winding signs with tendons loose or disconnected before a loaded run.
4. Set `hardware_reviewed` to `true` only after the configuration has been checked on the actual build.
5. Open an interactive terminal and supply the real serial port explicitly:

```sh
tdcr inspect --config local.robot.json
tdcr teleop --config local.robot.json --hardware --port /dev/ttyUSB0 --confirm-home
```

`/dev/ttyUSB0` is an example; use the device path on your machine (`COM…` on Windows, or `/dev/tty.usbserial-…` on macOS). Configure appropriate serial-device permissions for your operating system rather than making the port writable by everyone.

`--confirm-home` acknowledges that the current, manually established posture should define zero for this session. It does not run a homing search or load persistent calibration. Re-establish the physical reference after a power cycle or any event that changes encoder/posture correspondence.

Hardware mode requires an interactive terminal and rejects `--commands`. On normal exit, interruption, or handled errors, the driver attempts to disable torque and close the port. A disconnected cable or failed device can prevent a software shutdown; physical power removal remains the operator's fallback. Torque is held while waiting for the next terminal command, with no background sensor polling in keyboard mode. The gamepad loop checks its controller and optional sensor while idle.

## Add a measurement device

Start with the adapter smoke test, which never opens a motor connection:

```sh
python -m opentdcr sensor --sensor examples.sensor_adapter:create_sensor --samples 5
```

Run this repository-local example from the release root using `python -m opentdcr`; it is synthetic. For your own adapter installed in the environment, use its module and factory:

```sh
tdcr sensor --sensor my_lab.sensor:create_sensor --samples 5
tdcr teleop --config local.robot.json --sensor my_lab.sensor:create_sensor
```

The second command is still dry-run. Add the explicit hardware arguments only after validating the adapter and hardware configuration. Read [the measurement contract](measurements.md) for units, timing, invalid samples, and the exact limits of the health gate.

## Calibrate before teleoperation

The separate calibration command preserves the lab's sequence and accepts the same measurement contract. Start with its synthetic dry-run:

```sh
tdcr calibrate --config configs/three_segment.example.json \
  --calibration-config configs/calibration.example.json
```

For physical calibration, the operator pauses after loosening to perturb/settle the robot and can apply common tendon adjustments after the search. Use `--teleop` to continue without closing or reopening the calibrated motor session. See [calibration](calibration.md) for parameter meanings, reviewed sensor setup, reports, and failure handling.

## Troubleshooting

- **Configuration rejected:** check array lengths, unique IDs, signs, and units. Unknown fields are errors to catch misspellings.
- **Hardware enable rejected:** inspect the local review flag, explicit port, home acknowledgment, terminal type, model number, and preconfigured servo registers.
- **Motor communication fails:** check power, bus wiring, ID, baud rate, OS port access, and whether another application owns the port.
- **Sensor rejected:** check the frame label, acquisition timestamp, finite coordinates, tracking validity, and age limit. Do not relabel stale data with a fresh timestamp.
- **Unexpected motion direction:** stop, remove torque, verify the winding map, and repeat unloaded direction checks.
