# Contributing to OpenTDCR

Useful contributions include reproducible bug reports, measured robot configurations, sensor adapters, manufacturing notes, and small improvements to the control tools.

Start in a virtual environment and run:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
tdcr teleop --config configs/three_segment.example.json --commands '1 w 2 a q'
```

When reporting a bug, include the Python version, platform, command, expected behavior, and minimal configuration. Remove serial numbers, personal paths, unpublished data, and other private details. For a hardware issue, also report the actual servo model, firmware, wiring, and whether the issue reproduces with tendons disconnected.

A pull request should explain the behavior change and its validation. Keep hardware access optional, use explicit units, and test error paths alongside successful commands. Changes to optional gamepad input should test stale reports, disconnects, malformed reports, and hold-to-move behavior using synthetic reports. New sensor adapters should demonstrate finite-data checks, lost tracking, timestamps, and frame conversion without requiring the vendor device in CI.

Calibration changes should preserve the documented sequence and test scalar/vector settings, threshold crossing, countback calculation, actual readback, no-hit termination, invalid measurements, operator cancellation, and cleanup. Distinguish displacement thresholds from force calibration, and acknowledge the ICRA 2025 calibration paper when extending that workflow.

Mechanical changes should include editable source where available, a drawing or dimensioned explanation, material/print assumptions, and compatibility with the assembly reference. Confirm that you may contribute any supplier geometry or images. Do not replace a CAD file with a different revision under the same name without updating its provenance.

Software contributions are offered under the existing MIT license. The hardware license is pending maintainer selection; resolve contribution terms for mechanical work before publishing it. A contribution does not grant rights to third-party assets you do not own.
