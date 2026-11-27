# Working on OpenTDCR

This is the standalone public release tree. Start with `README.md`, then `docs/architecture.md`. The hardware reference is `hardware/cad/assembly.step`; example JSON configurations are illustrative until a maintainer verifies their mapping to the assembly.

## Commands

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
tdcr inspect --config configs/three_segment.example.json
tdcr teleop --config configs/three_segment.example.json --commands '1 w 2 a q'
tdcr calibrate --config configs/three_segment.example.json --calibration-config configs/calibration.example.json
```

Use the dry-run backend for development. Do not enable hardware merely to test a change. Real motor operation requires explicit operator authorization and a reviewed local configuration.

## Boundaries

- Keep serial paths, servo maps, measured offsets, and sensor transforms in local configuration; do not bake lab identifiers into code.
- Imports must not open devices, enable torque, move motors, or start infinite loops.
- Preserve explicit hardware opt-in, command limits, sensor validity checks, and cleanup on errors.
- The optional wired DualSense path requires fresh reports and L1 for motion. Preserve release-before-start and disarm-on-release-during-motion behavior; test disconnect and malformed-report cases without physical devices.
- Preserve the calibration order: loosen, operator settle/perturb, baseline, per-tendon threshold search, countback, loosen, apply all references, common manual adjustment, then new zero. Thresholds are measured-point millimetres; countbacks are tendon millimetres. Keep settings configurable and reject partial results as a completed calibration.
- Never restore saved calibration ticks automatically across a power cycle; optional reports are evidence, not verified homing records.
- Sensor adapters translate vendor data into the documented measurement contract. Keep vendor SDKs optional and outside the kinematics core.
- Use millimetres for tendon/position values and radians for angles. Specify frames and clock domains in interfaces.
- The default teleop is open-loop. A measurement health gate is not feedback control, collision avoidance, tension measurement, or a safety-rated stop.
- Add tests for behavioral changes in configuration, kinematics, calibration searches, sensor validation, or hardware state transitions; do not require devices in CI.
- Do not claim that a configuration matches the assembly or paper without evidence. Do not infer hardware dimensions, materials, part quantities, costs, or license rights from appearance.
- Preserve third-party notices and consult `hardware/LICENSING.md` before redistributing CAD.
- Keep logs, credentials, recordings, environment folders, and development caches out of the release.

## Website and packaging

The static webpage lives in `website/dist/`. Preview it with `python3 -m http.server 4173 --directory website/dist`. Its shape explorer is illustrative, and its CAD viewer uses the supplied actuation module; do not present either as measured robot behavior.

For CAD conversion, use explicit release-relative paths: `node tools/cad/convert-step.cjs hardware/cad/assembly.step website/dist/assets/cad`, then `node tools/cad/optimize-glb.mjs website/dist/assets/cad` (install locked dependencies with `npm ci --prefix tools/cad`). Refresh provenance whenever geometry changes.

Package with `python tools/package_release.py --output /tmp/OpenTDCR-source.zip`. Keep generated release archives, caches, local settings, and dependencies out of the source payload. This repository is published as a hardware release candidate. Keep unresolved licensing and hardware-release items visible; do not describe them as verified or complete without maintainer evidence.

## Documentation

Update the relevant guide when changing a public command, config field, unit, or sensor contract. `docs/release-checklist.md` tracks unverified release requirements; close items only with recorded evidence. Keep announcement drafts outside this public repository; do not commit them or include them in release archives.
