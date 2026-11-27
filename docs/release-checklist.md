# Release checklist

This checklist separates a usable software release candidate from a verified, reproducible hardware release. It should be completed against the exact assets in `hardware/asset-manifest.json`.

## Decisions still needed from maintainers

- [x] Select the planned destination repository: https://github.com/ContinuumRoboticsLab/OpenTDCR.
- [x] Create the public repository: https://github.com/ContinuumRoboticsLab/OpenTDCR. Publish the project page: https://continuumroboticslab.github.io/OpenTDCR/.
- [ ] Confirm software contributors and the first release version; lab-facing MIT attribution and the original notice are already present.
- [ ] Select and apply the hardware license; verify rights and attribution for embedded supplier CAD and assembly photographs.
- [ ] Confirm whether the supplied assembly exactly matches the CoRL experimental robot or document the differences.

## Hardware reproducibility

- [ ] Match each standalone STL to the supplied STEP revision and export missing custom parts.
- [ ] Complete `hardware/bom.csv`: exact quantities, product variants, sources, and procurement alternatives.
- [ ] Supply connector PCB schematic, layout, manufacturing outputs, pinout, and license, or document an available replacement.
- [ ] Add the flexible-backbone and disk/module design absent from the supplied actuation assembly.
- [ ] Record backbone material, diameter and length; segment lengths; disk geometry and spacing; tendon material/diameter; routing and terminations.
- [ ] Record validated print material, orientation, tolerances, and fastening procedure.
- [ ] Confirm servo count, unique IDs, tendon map, winding signs, effective spool radii, geometry, command limits, and bus settings in a configuration for this exact assembly.
- [ ] Build or inspect a complete assembly from the released files and document any deviations.

## Software and physical validation

- [x] Run the documented install and dry-run commands in a fresh environment. See [verification](verification.md).
- [x] Run the unit suite and record the command/results in the release notes; 102 tests pass on Python 3.10 and 3.12 in GitHub Actions; see [verification](verification.md).
- [ ] Verify SDK communication and readback with the target servo model; test direction and travel with tendons disconnected before loaded tests.
- [ ] Verify startup behavior, shutdown, communication failure, and an interrupted session with an operator at the robot.
- [ ] Validate the retained calibration sequence on this assembly: loosen/settle, threshold search, countback, apply-all, common adjustment, and final reference; record measured thresholds and countbacks.
- [ ] Validate wired DualSense acquisition, segment selection, hold-to-move, release during motion, Circle exit, and disconnect behavior on each supported OS.
- [ ] Verify calibration time/travel limits, no-threshold abort, stale or ambiguous tracking, operator cancellation, and partial-run cleanup before loaded use.
- [ ] Verify report contents and same-session teleoperation; confirm reports are not automatically restored after restart.
- [ ] Test a real measurement adapter, including unit/frame conversion, lost tracking, and stale samples.
- [ ] Document the tested operating systems, Python versions, servo firmware, and optional device libraries.

## Publication

- [x] Verify that the archive contains only the standalone public release tree and excludes internal Git history, experimental logs, sensor recordings, and local configuration. The public repository starts with root commit `3f57aadb91955b83ed24af313ef80e351bf6b8af`.
- [x] Review the webpage's CAD rendering against the assembly and label illustrative kinematics separately from physics simulation.
- [x] Keep announcement drafts outside the public repository and source archive.
- [ ] Confirm citation metadata and contributor acknowledgments before posting.
- [ ] Tag the reviewed source, archive the hardware release, and retain the manifest hashes with the release.

The browser and software tests do not replace physical validation. Keep incomplete items visible in a release candidate; do not mark them complete from a successful dry-run alone.
