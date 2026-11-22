#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {NodeIO} from '@gltf-transform/core';
import {KHRMeshQuantization, EXTMeshoptCompression} from '@gltf-transform/extensions';
import {dedup, prune, quantize, weld, meshopt} from '@gltf-transform/functions';
import {MeshoptEncoder} from 'meshoptimizer';

const directory = path.resolve(process.argv[2] || 'website/assets/cad');
const asset = path.join(directory, 'assembly.glb');
await MeshoptEncoder.ready;
const io = new NodeIO().registerExtensions([KHRMeshQuantization, EXTMeshoptCompression])
  .registerDependencies({'meshopt.encoder': MeshoptEncoder});
const document = await io.read(asset);
await document.transform(weld(), dedup(), quantize({quantizePosition: 16, quantizeNormal: 10}), prune());
await io.write(asset, document);
const bytes = await fs.readFile(asset);
const manifestPath = path.join(directory, 'manifest.json');
const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
manifest.assetSha256 = crypto.createHash('sha256').update(bytes).digest('hex');
manifest.byteLength = bytes.length;
manifest.optimization = {
  tool: '@gltf-transform 4.2.1', operations: ['weld', 'dedup', 'quantize', 'prune'],
  positionBits: 16, normalBits: 10,
  extension: 'KHR_mesh_quantization (supported directly by Three.js GLTFLoader)',
  note: 'Topology unchanged; quantization precision is finer than the STEP tessellation tolerance.',
};
await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
console.log(JSON.stringify({asset, megabytes: bytes.length / 1e6}));

await document.transform(meshopt({encoder: MeshoptEncoder, level: 'high', quantizePosition: 16, quantizeNormal: 10}));
const compressedPath = path.join(directory, 'assembly-optimized.glb');
await io.write(compressedPath, document);
const compressed = await fs.readFile(compressedPath);
manifest.compressedAsset = {
  asset: 'assembly-optimized.glb', byteLength: compressed.length,
  sha256: crypto.createHash('sha256').update(compressed).digest('hex'),
  extension: 'EXT_meshopt_compression',
  loader: 'GLTFLoader.setMeshoptDecoder(MeshoptDecoder)',
};
await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
console.log(JSON.stringify({asset: compressedPath, megabytes: compressed.length / 1e6}));
