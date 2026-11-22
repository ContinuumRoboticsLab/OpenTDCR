#!/usr/bin/env node
/* Tessellate the supplied STEP assembly into a self-contained glTF 2.0 binary.
 * Run from repository root: node tools/cad/convert-step.cjs
 * Node >=18; npm ci --prefix tools/cad
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const input = path.resolve(process.argv[2] || 'STLs/assembly.step');
const output = path.resolve(process.argv[3] || 'website/assets/cad');
const params = {
  linearUnit: 'millimeter', linearDeflectionType: 'absolute_value',
  linearDeflection: 0.4, angularDeflection: 0.5,
};

async function main() {
  const source = fs.readFileSync(input);
  const occt = await require('occt-import-js')();
  const result = occt.ReadStepFile(source, params);
  if (!result.success || !result.meshes.length) throw new Error('STEP tessellation failed');
  const low = [Infinity, Infinity, Infinity], high = [-Infinity, -Infinity, -Infinity];
  for (const mesh of result.meshes) {
    mesh.attributes.position.array.forEach((v, i) => {
      if (!Number.isFinite(v)) throw new Error('Non-finite position');
      const d = i % 3; low[d] = Math.min(low[d], v); high[d] = Math.max(high[d], v);
    });
  }
  const center = low.map((v, i) => (v + high[i]) / 2);
  // The supplied robot mount faces -X. Put that direction along glTF +Y.
  // Keep CAD geometry intact; only apply a rigid frame change + mm to m.
  const point = (x, y, z) => [(y - center[1]) / 1000, (high[0] - x) / 1000, (z - center[2]) / 1000];
  const vector = (x, y, z) => [y, -x, z];
  const gltf = {
    asset: {version: '2.0', generator: 'OpenTDCR STEP converter / occt-import-js 0.0.23'},
    scene: 0, scenes: [{nodes: [0]}], nodes: [{name: 'OpenTDCR supplied assembly', children: []}],
    meshes: [], materials: [], accessors: [], bufferViews: [], buffers: [{byteLength: 0}],
  };
  const chunks = []; let length = 0;
  const materialCache = new Map();
  function material(color) {
    const c = color || [0.28, 0.29, 0.30];
    const key = c.map(v => v.toFixed(5)).join(',');
    if (materialCache.has(key)) return materialCache.get(key);
    const index = gltf.materials.length;
    gltf.materials.push({name: `CAD ${key}`, pbrMetallicRoughness: {
      baseColorFactor: [...c, 1], metallicFactor: 0.08, roughnessFactor: 0.46,
    }});
    materialCache.set(key, index); return index;
  }
  function accessor(array, type, componentType, target, bounds = false) {
    const bytes = Buffer.from(array.buffer, array.byteOffset, array.byteLength);
    const view = gltf.bufferViews.length;
    gltf.bufferViews.push({buffer: 0, byteOffset: length, byteLength: bytes.length, target});
    chunks.push(bytes); length += bytes.length;
    const padding = (4 - length % 4) % 4;
    if (padding) { chunks.push(Buffer.alloc(padding)); length += padding; }
    const item = {bufferView: view, componentType, count: array.length / (type === 'VEC3' ? 3 : 1), type};
    if (bounds) {
      item.min = [Infinity, Infinity, Infinity]; item.max = [-Infinity, -Infinity, -Infinity];
      array.forEach((v, i) => { const d = i % 3; item.min[d] = Math.min(item.min[d], v); item.max[d] = Math.max(item.max[d], v); });
    }
    gltf.accessors.push(item); return gltf.accessors.length - 1;
  }
  const groupManifest = [];
  function addGroup(group) {
    if (!group.meshes.length) { for (const c of group.children || []) addGroup(c); return; }
    const positions = [], normals = [], byMaterial = new Map();
    for (const sourceIndex of group.meshes) {
      const mesh = result.meshes[sourceIndex];
      const offset = positions.length / 3;
      const p = mesh.attributes.position.array, n = mesh.attributes.normal?.array;
      if (!n || p.length !== n.length) throw new Error('Missing normals');
      for (let i = 0; i < p.length; i += 3) {
        positions.push(...point(p[i], p[i + 1], p[i + 2]));
        normals.push(...vector(n[i], n[i + 1], n[i + 2]));
      }
      const sourceIndices = mesh.index.array;
      const triangleMaterial = new Uint16Array(sourceIndices.length / 3).fill(material(mesh.color));
      for (const face of mesh.brep_faces || []) {
        if (face.color) triangleMaterial.fill(material(face.color), face.first, face.last + 1);
      }
      for (let i = 0; i < sourceIndices.length; i += 3) {
        const mat = triangleMaterial[i / 3];
        if (!byMaterial.has(mat)) byMaterial.set(mat, []);
        const indices = byMaterial.get(mat);
        for (let k = 0; k < 3; k++) {
          if (sourceIndices[i + k] * 3 >= p.length) throw new Error('Index outside vertex buffer');
          indices.push(sourceIndices[i + k] + offset);
        }
      }
    }
    const position = accessor(new Float32Array(positions), 'VEC3', 5126, 34962, true);
    const normal = accessor(new Float32Array(normals), 'VEC3', 5126, 34962);
    const primitives = [];
    for (const [mat, indices] of byMaterial) {
      const short = positions.length / 3 <= 65535;
      primitives.push({attributes: {POSITION: position, NORMAL: normal},
        indices: accessor(short ? new Uint16Array(indices) : new Uint32Array(indices), 'SCALAR', short ? 5123 : 5125, 34963), material: mat});
    }
    const meshIndex = gltf.meshes.length;
    gltf.meshes.push({name: group.name, primitives});
    gltf.nodes[0].children.push(gltf.nodes.length);
    gltf.nodes.push({name: group.name || 'assembly_part', mesh: meshIndex,
      extras: {sourceMeshCount: group.meshes.length, source: 'assembly.step'}});
    groupManifest.push({name: group.name, sourceMeshes: group.meshes.length,
      triangles: [...byMaterial.values()].reduce((s, v) => s + v.length / 3, 0),
      sourceNames: [...new Set(group.meshes.map(i => result.meshes[i].name).filter(Boolean))]});
    for (const c of group.children || []) addGroup(c);
  }
  addGroup(result.root);
  gltf.buffers[0].byteLength = length;
  const jsonRaw = Buffer.from(JSON.stringify(gltf));
  const json = Buffer.concat([jsonRaw, Buffer.alloc((4 - jsonRaw.length % 4) % 4, 0x20)]);
  const binary = Buffer.concat(chunks);
  const header = Buffer.alloc(12); header.writeUInt32LE(0x46546c67, 0); header.writeUInt32LE(2, 4); header.writeUInt32LE(12 + 8 + json.length + 8 + binary.length, 8);
  const jh = Buffer.alloc(8); jh.writeUInt32LE(json.length, 0); jh.writeUInt32LE(0x4e4f534a, 4);
  const bh = Buffer.alloc(8); bh.writeUInt32LE(binary.length, 0); bh.writeUInt32LE(0x004e4942, 4);
  fs.mkdirSync(output, {recursive: true});
  const glb = Buffer.concat([header, jh, json, bh, binary]);
  fs.writeFileSync(path.join(output, 'assembly.glb'), glb);
  const manifest = {
    source: 'STLs/assembly.step', sourceSha256: crypto.createHash('sha256').update(source).digest('hex'),
    asset: 'assembly.glb', assetSha256: crypto.createHash('sha256').update(glb).digest('hex'),
    sourceBoundsMm: {min: low, max: high, size: high.map((v, i) => v - low[i])},
    gltfUnits: 'meters', gltfAxes: 'Y up; original CAD -X maps to +Y; original +Y maps to +X; original +Z unchanged',
    transform: {x: '(CAD_y - bounds_center_y) / 1000', y: '(bounds_max_x - CAD_x) / 1000', z: '(CAD_z - bounds_center_z) / 1000'},
    meshCount: result.meshes.length, triangleCount: groupManifest.reduce((s, v) => s + v.triangles, 0),
    byteLength: glb.length, tessellation: params, groups: groupManifest,
    notes: [
      'Literal tessellation of the supplied actuation assembly; no geometry was invented.',
      'A long flexible backbone is absent from this assembly; a browser bending demonstration must be labeled illustrative.',
      'CAD appearance colors retained where available; fallback gray and PBR surface response are presentation choices.',
      'Contains supplier component geometry. Review redistribution rights before public release.',
    ],
  };
  fs.writeFileSync(path.join(output, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
  console.log(JSON.stringify({asset: path.join(output, 'assembly.glb'), megabytes: glb.length / 1e6, triangles: manifest.triangleCount, groups: groupManifest.length}));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
