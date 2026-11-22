# Tendon calibration with your own sensor

`tdcr calibrate` preserves the lab's measured-tip calibration sequence while separating it from any particular measurement device. It loosens the tendons, measures a baseline, pulls each tendon to a tip-displacement threshold, subtracts a configured tendon-length countback, and applies the resulting references together. The operator can make common adjustments before recording a new zero.

The sensor can be the optional Lyra adapter or your own implementation of the [measurement contract](measurements.md). Thresholds and countbacks are configuration values. This procedure establishes tendon positions; it does not measure or estimate tendon force in newtons. The refactored workflow has synthetic tests but still requires validation on the physical robot and sensor.

## Try the complete sequence without hardware

From the release root after `python -m pip install -e .`:

```sh
tdcr calibrate --config configs/three_segment.example.json \
  --calibration-config configs/calibration.example.json
```

With no hardware or sensor flags, this uses a synthetic command-to-deflection source and dry-run transport. It exercises the sequence and prints a structured report. It is not simulated continuum mechanics or evidence of physical calibration accuracy.

To save a report and continue into a short teleoperation example using the newly established reference:

```sh
tdcr calibrate --config configs/three_segment.example.json \
  --calibration-config configs/calibration.example.json \
  --output configs/calibration-demo.local.json \
  --teleop --commands '1 w 2 a home q'
```

The report path must not already exist. Reports named `*.local.json` under `configs/`, files named `local.*`, and files under `measurements/` are excluded from source exports; use one of those locations and a new filename for each run. `--commands` is supported only for dry-run keyboard input after `--teleop`.

## Sequence and coordinate conventions

Positive tendon displacement must pull/retract the tendon; verify this against the physical winding and `servo_direction` before a loaded run. Until the final reference capture, all tendon positions below are relative to the initial session reference acknowledged by `--confirm-home`.

1. **Loosen all tendons.** Command each tendon to `-loosen_amount_mm` and settle while checking measurements.
2. **Operator perturbation.** In hardware mode, pause so the operator can gently perturb the loose robot to reduce hysteresis, then let it settle and press Enter. The dry-run demo passes this stage automatically.
3. **Record one baseline.** Wait for a sample acquired at or after the operator prompt returns, then record the measured point in `robot_base`. All subsequent threshold comparisons use Euclidean distance from this baseline.
4. **Search one tendon at a time.** Keep the other tendons at their loose positions. Move the selected tendon to `search_start_mm`, then command positive pull positions in `pull_step_mm` increments, starting one step above `max(0, search_start_mm)`. Stop when measured displacement is at least its configured threshold. Each threshold decision waits for a sample acquired at or after the corresponding motor move completes. Searches are bounded by an absolute upper pull coordinate and a per-tendon timeout.
5. **Record and count back.** Read the actual tendon position at the threshold crossing. Compute its candidate reference as `actual_position_mm - movement_countback_mm`. Countback is a tendon-length correction; it is not a subtraction from measured tip motion.
6. **Loosen before the next tendon.** Return all tendons to their loose positions. Repeat the search for each servo in the configured order.
7. **Apply all references together.** After every tendon succeeds, command the full vector of countback-adjusted positions.
8. **Common operator adjustment.** In hardware mode, enter a signed millimetre increment to add to every tendon's current position. Positive pulls; negative loosens. Repeat as needed, or press Enter to accept. Each adjustment is bounded and recorded.
9. **Capture the new zero.** Validate the final measurement and actuator readback, then record the final positions as the new session reference. A partial or failed search never yields a completed reference.

The initial search approach and positive-pull convention retain the existing lab sequence. `search_start_mm` is not a progressive scan of the entire interval from the loose posture. Choose these parameters for the actual robot rather than assuming small numerical examples are universally safe.

## Calibration configuration

[`configs/calibration.example.json`](../configs/calibration.example.json) is a demonstration configuration. Copy it to a local file and select values from measurements on your own build.

| Field | Units and meaning |
| --- | --- |
| `loosen_amount_mm` | Positive tendon payout from the initial zero; scalar or one value per tendon |
| `movement_threshold_mm` | Positive Euclidean displacement of the measured point from its baseline; scalar or one value per tendon |
| `movement_countback_mm` | Nonnegative tendon displacement subtracted from the actual threshold-crossing position; scalar or one value per tendon |
| `pull_step_mm` | Positive increment between commanded pull coordinates |
| `max_pull_mm` | Positive upper tendon coordinate relative to the initial zero, not additional travel from the loose posture |
| `search_start_mm` | Initial approach coordinate for the selected tendon, in the same initial reference |
| `settle_s` | Nonnegative settling time after commanded motion |
| `tendon_timeout_s` | Positive limit covering that tendon's approach, settling, and threshold search |

Vectors follow `servo_ids` order and must contain exactly one value per tendon. Scalar loosen, threshold, and countback values broadcast to all tendons. Unknown fields and nonfinite or invalid values are rejected. The example's `1.0`, `0.5`, and `0.1` millimetre settings are synthetic-demo choices, not recovered tuning for the CAD assembly.

The robot's `max_tendon_travel_mm`, speed limit, and sensor age limit still apply. Repeated fresh samples can satisfy health checks, but a pre-motion sample cannot trigger a threshold. Waiting for a decision sample is bounded by `sensor_max_age_s` and the active tendon deadline. Calibration endpoints must fit inside the robot travel interval. Countback results and common adjustments are checked again before use. A large maximum pull is not a substitute for selecting a meaningful threshold or checking marker visibility.

## Run with an independent measurement sensor

First verify the hardware setup, winding signs, conservative limits, and sensor units/frame/timing. Install the motor backend and make the adapter importable in the active environment:

```sh
python -m pip install -e '.[hardware]'
tdcr sensor --sensor my_lab.sensor:create_sensor --samples 5
```

Use `tdcr` with an adapter installed in the environment. For a module located only in the current project directory, launch `python -m opentdcr` from that directory instead. A factory must return a real measurement source with `read()` and `close()`; bundled mock sources are rejected for hardware calibration.

Create a reviewed `configs/robot.local.json` and a measured `configs/calibration.local.json`, then run from an interactive terminal:

```sh
tdcr calibrate --config configs/robot.local.json \
  --calibration-config configs/calibration.local.json \
  --hardware --port /dev/ttyUSB0 --confirm-home \
  --sensor my_lab.sensor:create_sensor \
  --output configs/calibration-result.local.json \
  --teleop
```

Use the actual serial port on your machine. `--confirm-home` acknowledges the prepared starting posture as a temporary encoder reference; it does not claim the tendons are already calibrated. The hardware path requires a reviewed robot config and the servo setup described in [getting started](getting-started.md#connect-real-hardware).

`--teleop` preserves the same open motor session and the new calibration reference. Add `--input dualsense` and the gamepad extra to continue with the supported wired controller. Without `--teleop`, the process prints/saves the report and closes the hardware. Starting a separate teleoperation command captures that command's starting posture again; it does not automatically restore the report.

Ctrl-C or an error requests transport cleanup and torque-off. Missing thresholds, timeouts, invalid or stale samples, rejected targets, and operator-input failures abort the run. Software cannot guarantee torque-off if communication has failed; keep a physical power cutoff available. The manual prompts wait for the operator and do not poll the sensor in the background.

## Use the optional Lyra adapter

Install its optional SDK package along with the motor backend:

```sh
python -m pip install -e '.[hardware,lyra]'
```

Copy [`configs/lyra.example.json`](../configs/lyra.example.json) to `configs/lyra.local.json`. The example contains a non-routable placeholder host, an identity transform, and `configuration_reviewed: false`; it cannot be used as a working lab calibration. Configure and verify:

| Field | Meaning |
| --- | --- |
| `host`, `port` | Your tracker connection endpoint |
| `configuration_reviewed` | Set true after checking the endpoint, frame transform, and marker-selection policy |
| `sensor_to_base.rotation` | Proper orthonormal 3×3 rotation from tracker axes to robot-base axes |
| `sensor_to_base.translation_mm` | Three-element translation in millimetres |
| `tip.mode: "exactly_one"` | Require exactly one visible marker candidate |
| `tip.mode: "roi"` | Select inside the configured tracker-frame bounds; still require exactly one candidate |
| `tip.min_sensor_mm`, `tip.max_sensor_mm` | Inclusive three-dimensional ROI bounds in tracker coordinates, for ROI mode |
| `timeout_s` | Bound on individual worker requests/native reads |
| `open_timeout_s` | Bound on opening/configuring the tracker worker |
| `max_frame_age_s` | Adapter-level age limit, in addition to the robot's measurement age check |
| `frame_period_s` | Conservative frame-period allowance used for the host-monotonic acquisition bound |

The frame transform is `p_base = R * p_sensor + translation_mm`. It assumes the tracker and robot base remain fixed relative to one another. This adapter does not track a moving reference rigid body. An ROI is spatial isolation, not a persistent marker ID; do not allow another marker to enter the selected region or swap identity.

Check acquisition without motors before enabling calibration:

```sh
tdcr sensor --sensor lyra --sensor-config configs/lyra.local.json --samples 5

tdcr calibrate --config configs/robot.local.json \
  --calibration-config configs/calibration.local.json \
  --hardware --port /dev/ttyUSB0 --confirm-home \
  --sensor lyra --sensor-config configs/lyra.local.json \
  --output configs/lyra-calibration-result.local.json \
  --teleop
```

The adapter refuses missing, ambiguous, or nonfinite marker data, invalid frame IDs, backwards or inconsistent frames, stale data, and worker errors. A repeated frame returns the original measurement with its original timestamp; it cannot refresh the age of cached data. Native SDK calls run in a worker process with bounded requests. Its timestamps are conservative host-monotonic acquisition bounds, not a claim of precise hardware-clock synchronization. The Lyra path has not yet been validated against the physical tracker.

## Reports and reproducibility

The JSON report records whether the run was dry-run, creation time, measurement source, the reviewed Lyra configuration when used (including transform, ROI, timing, and endpoint), robot and calibration configurations, baseline, each threshold-crossing displacement and actual tendon position, countback references, common adjustments, final readback, reference offsets, raw encoder ticks when available, and elapsed time.

The CLI prints a report and writes a new file only when `--output` is supplied. Existing files are never overwritten. Reports are local experimental records, not reusable hardware configurations. Encoder values can lose their physical correspondence across reboot, rewinding, maintenance, or loss of tension. Re-establish and validate the reference rather than automatically loading saved ticks.

For custom code, `calibrate(transport, sensor, config, ...)` takes an already-open transport and leaves it open on success. `on_loosened()` supplies the operator pause; `adjustment(current_positions_mm)` returns a common increment or `None`; `on_progress(event)` receives progress dictionaries. On failure it closes the transport and raises. The caller remains responsible for sensor cleanup and closing a successful session.

## Research acknowledgment

This workflow builds on the calibration work of Kyum Lee, Chengnan Shentu, Chloe Pogue, and Jessica Burgner-Kahrs, **Automating Tension Calibration for Tendon-Driven Continuum Robots: A Low-Cost Approach Towards Consistent Teleoperation**, ICRA 2025, DOI [10.1109/ICRA55743.2025.11128689](https://doi.org/10.1109/ICRA55743.2025.11128689). [BibTeX](citation.bib).

OpenTDCR retains the lab's later measured-position threshold/countback procedure as an adaptation of that research. It does not implement the paper's Hall-effect sensor characterization or assert its measured tension accuracy or repeatability. Report those quantities only after evaluating this implementation on the actual hardware.
