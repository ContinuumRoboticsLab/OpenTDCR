# Supplied assembly preview

`assembly-optimized.glb` is the preferred web asset (about 2 MB). It is a
tessellation of the user-supplied `STLs/assembly.step`, with Meshopt compression.
The 8.4 MB `assembly.glb` is the equivalent without Meshopt compression.

`manifest.json` records exact source/output hashes, coordinate transform,
tessellation parameters, dimensions, and original CAD group names. Regenerate
with the scripts in `tools/cad/`.

## Inspection findings

- The supplied STEP is an actuation assembly, not a complete flexible robot.
  It includes a vertebra base/mount, but no long backbone or routed tendon model.
- Its tessellated bounding box is approximately **237.25 × 134.00 × 92.00 mm**
  along the original CAD X/Y/Z axes. These are CAD envelope measurements, not
  manufacturing tolerances or a physical measurement of the robot.
- There are **16 matching servo housing occurrences** in the geometry. The STEP
  product table contains shared definitions, so counting product names alone
  undercounts instances. This observation does not establish the number of
  actuated tendons, segment count, wiring, motor IDs, or control configuration.
- The original group hierarchy contains servos, plates, transition frame,
  Franka adapter/U2D2, vertebra base, and fan assembly.
- Supplier geometry includes XL-430 housings, ROBOTIS U2D2/power hub and JST
  connectors. The supplied files do not establish redistribution rights for
  those models; review before public distribution.
- `doc/add_robot.png` depicts an older complete robot with a long backbone.
  It should not be presented as an exact image of the supplied assembly.
- The seven standalone STL files are watertight according to trimesh inspection.
  `printable-parts.json` records their mesh extents and triangle counts. STL has
  no inherent unit metadata; millimeters follow the repository's build context.
  Watertightness alone does not verify printability, fit, or material suitability.

## Renderer integration

The glTF coordinates use meters, Y up, with the original CAD -X axis pointing
upward toward the robot mount. The actuation unit bottom is approximately Y=0
and its top is Y=0.23725. X/Z are centered. Component transforms include vertex
quantization; preserve their initial transforms when implementing explode views.

```js
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {MeshoptDecoder} from 'three/addons/libs/meshopt_decoder.module.js';
const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
const {scene} = await loader.loadAsync('assets/cad/assembly-optimized.glb');
```

Verification: both glTF files pass Khronos glTF Validator with zero errors and
warnings. The validator does not inspect Meshopt compressed payloads; the
compressed file was separately decoded with Three.js 0.181.0 `GLTFLoader` and
its bundled Meshopt decoder, preserving all 315,146 triangles and the bounding
box to within 0.003 mm of the uncompressed tessellation.
