# Release provenance and scope

OpenTDCR was prepared as a standalone tree from the internal `crl_tdcr_teleop` project. The original project and its untracked work were preserved. The public tree is designed to be exported without the internal repository's Git history.

## Retained material

| Source | Public destination | Treatment |
| --- | --- | --- |
| `LICENSE` | `LICENSE` | MIT terms and original 2024 notice retained; 2026 lab notice added for this release |
| `STLs/assembly.step` | `hardware/cad/assembly.step` | Exact supplied assembly; hardware release reference |
| Seven standalone STL files | `hardware/cad/` | Exact byte copies; matching to assembly revision still required |
| `doc/add_*.png` | `docs/images/` | Existing assembly images, retained with revision caveat |
| Legacy multi-segment kinematics and servo conventions | `src/opentdcr/` | Reworked into small configurable interfaces and explicit hardware lifecycle |
| Legacy Lyra threshold/countback calibration | `src/opentdcr/calibration.py` and optional adapter | Sequence retained; sensor acquisition and settings separated from experiment scripts |
| Legacy setup/build notes | `docs/` | Rewritten to separate verified instructions from missing build information |

`hardware/asset-manifest.json` records source paths, sizes, SHA-256 hashes, and license review status for the copied CAD and images. The STEP header identifies an Autodesk translation export on 2026-11-20. No named legacy script was treated as proof of a configuration match.

## Material excluded from the public tree

- The monolithic experiment scripts for Lyra, RealSense, and Hall-effect setups. Their common threshold/countback calibration sequence is retained in the public core; Lyra support is available through an isolated optional adapter.
- Lab-specific calibration transforms, sensor marker definitions, recorded measurements, trajectory logs, and analysis outputs.
- One-off demonstrations, arm integrations, crawling/egg demos, and hard-coded robot revisions.
- Developer environments, package caches, Git metadata, and vendor SDK checkouts.
- Serial device identifiers and machine-specific paths from example scripts.

The replacement sensor contract supports user-provided measurement adapters. It does not silently reuse a laboratory sensor transform. The calibration module preserves the original sequence with configurable thresholds/countbacks and bounded, checked transport operations; bench results from the old scripts are not validation of the new implementation.

## Claims and evidence

The existing hardware guide supports the frame assembly sequence and nominal spool naming. The supplied STEP establishes the reference geometry. Neither establishes a complete BOM, manufacturing recipe, safety limit, or measured configuration for the release.

The related research citation is verified against [arXiv:2606.22397](https://arxiv.org/abs/2606.22397); CoRL 2026 is listed on [the first author's research page](https://www.cs.utoronto.ca/~cshentu/). Simulation methodology and validation belong to that paper and [OpenCR-MuJoCo](https://github.com/ContinuumRoboticsLab/opencr-mujoco), not to the new illustrative webpage or this control package.

New software checks use fake transports, synthetic USB controller reports, and synthetic measurements. The optional gamepad adapter supports the standard wired DualSense report layout; Bluetooth and Edge support are excluded. Physical hardware was not operated during this preparation. Record actual test results and unresolved items in the release notes when the maintainers validate a build.

## Software attribution and calibration research

The public software is attributed to the Continuum Robotics Laboratory, University of Toronto. Its MIT license also retains the original Chengnan Shentu notice to preserve inherited-code provenance and the [MIT notice requirement](https://opensource.org/license/mit). This update does not relicense supplier CAD.

The calibration work acknowledges Lee, Shentu, Pogue, and Burgner-Kahrs, ICRA 2025, DOI [10.1109/ICRA55743.2025.11128689](https://doi.org/10.1109/ICRA55743.2025.11128689). The title, authors, conference, year, and DOI were verified from the [author-hosted paper](https://www.cs.toronto.edu/~cshentu/pdf/tension_calib.pdf); the [lab's ICRA report](https://crl.utm.utoronto.ca/2025/06/06/icra.html) confirms its presentation. The new implementation retains the later lab workflow's measured-position threshold and tendon-length countback approach through a sensor-independent interface. The paper's performance numbers are not claims about this implementation.
