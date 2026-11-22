# Hardware assets

The release reference is [`cad/assembly.step`](cad/assembly.step), supplied by the project maintainer and exported on 2026-11-20 according to the STEP header. All files below are unchanged copies of the supplied files. SHA-256 hashes are in [`asset-manifest.json`](asset-manifest.json).

The STEP contains the actuation module and mounts, with 16 modeled servo-housing occurrences. It does not include the long flexible backbone seen in the older assembly photographs. A complete TDCR therefore needs additional backbone, disk/module, tendon, and routing specifications. The geometric servo count is not a verified actuator assignment or purchasing BOM.

## CAD inventory

| File | Existing description | Release status |
| --- | --- | --- |
| [assembly.step](cad/assembly.step) | Complete supplied CAD assembly reference | Inspect assembly tree; supplier geometry and compatibility review pending |
| [base_plate.stl](cad/base_plate.stl) | Bottom servo-frame plate | Earlier build guide specifies 2 per frame; verify against assembly |
| [front_plate v2.stl](cad/front_plate%20v2.stl) | Front servo-frame plate | Earlier build guide specifies 2 per frame; verify against assembly |
| [top_plate.stl](cad/top_plate.stl) | Top servo-frame plate | Earlier build guide specifies 2 per frame; verify against assembly |
| [XL-430_servo_spool_r10.stl](cad/XL-430_servo_spool_r10.stl) | XL-430 tendon spool, nominal 10 mm winding radius | Verify attachment and effective loaded radius |
| [robot_mount.stl](cad/robot_mount.stl) | Robot-to-frame adapter | Correspondence to the assembly's transition-frame part unverified |
| [franka_mount_wo_d405.stl](cad/franka_mount_wo_d405.stl) | Franka/frame and U2D2 mounting adapter | Optional for bench-mounted builds; correspondence unverified |
| [u2d2_small_mount.stl](cad/u2d2_small_mount.stl) | U2D2 mount | Correspondence to the assembly's U2D2 case unverified |

STL is unitless. These source names and existing build instructions suggest millimetre-scale parts, but confirm scale against the STEP model before manufacturing. Do not scale parts to fit a build plate.

The assembly contains parts named `vertebra_base_v5`, `transition_frame_v4`, `fan mount`, and supplier electronics that do not have a one-to-one match in the standalone STL names. The current STL set should not yet be advertised as a complete, revision-matched print kit. Extract and verify missing custom parts from the editable design before the first hardware release.

Continue with the [hardware guide](../docs/hardware.md), [BOM worksheet](bom.csv), and [licensing status](LICENSING.md).
