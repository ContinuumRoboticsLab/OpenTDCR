# CAD preview assets

This conversion pipeline tessellates the supplied STEP assembly with OpenCascade,
retains its appearance colors, and writes a browser-ready glTF binary. It does not
add a backbone or infer missing manufacturing geometry.

From the repository root:

```sh
npm ci --prefix tools/cad
node tools/cad/convert-step.cjs hardware/cad/assembly.step website/assets/cad
node tools/cad/optimize-glb.mjs
```

Optional arguments to the converter are the input STEP path and output directory.
The optimizer accepts the output directory as its first argument. Defaults are
`STLs/assembly.step` and `website/assets/cad`.

The generated `manifest.json` records source and asset SHA-256 hashes, CAD bounds,
tessellation tolerances, original component groups, and the coordinate transform.
glTF uses meters with Y up. The original CAD -X direction points up, toward the
robot mount, and the model bottom is at Y = 0. Vertex colors retain source CAD
appearance; the roughness and metallic factors are visualization choices.

Meshes are grouped by top-level STEP assembly component. Optimization welds
identical vertices and quantizes attributes with `KHR_mesh_quantization`; a
standard Three.js `GLTFLoader` can read the result without an external decoder.
16-bit position quantization is much finer than the 0.4 mm tessellation tolerance.

The optimizer also creates `assembly-optimized.glb` using Meshopt compression.
Load this smaller variant with `GLTFLoader.setMeshoptDecoder(MeshoptDecoder)`;
the decoder is distributed with Three.js as
`examples/jsm/libs/meshopt_decoder.module.js`.

The STEP contains supplier components including ROBOTIS and JST geometry. Confirm
redistribution rights before public distribution. The converter dependencies
have their own licenses in `node_modules`; dependencies are not shipped in the
website, only the resulting mesh.
