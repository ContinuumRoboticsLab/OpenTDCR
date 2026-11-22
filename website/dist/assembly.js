import * as THREE from 'three';
import { createStudio } from './studio.js';
import { loadAssembly } from './cad.js';

const clamp = (x, low = 0, high = 1) => Math.min(high, Math.max(low, x));
const smoothstep = (x) => { const t = clamp(x); return t * t * (3 - 2 * t); };

// The supplied CAD has ten component roots. Its merged servos_4 material mesh
// contains sixteen disconnected printed spools, verified against the supplied
// XL-430_servo_spool_r10.stl (24 × 24 × 7 mm). Extract their original triangles;
// every other material submesh stays with its actual source subassembly.
const componentNames = /^(servos$|printed_spool_|base_plate|front_plate|transition_frame|franka_adapter|vertebra_base|fan_mount|solid$)/i;
const assembledDirection = new THREE.Vector3(5.4, 3.2, 7.2).normalize();
const flatDirection = new THREE.Vector3(0.5, 10, 5.8).normalize();
const worldUp = new THREE.Vector3(0, 1, 0);

function componentRoots(scene) {
  const roots = [];
  scene.traverse((node) => { if (componentNames.test(node.name)) roots.push(node); });
  const selected = new Set(roots);
  return roots.filter((node) => {
    for (let p = node.parent; p; p = p.parent) if (selected.has(p)) return false;
    return true;
  });
}

// Orient the narrowest source dimension vertically, then put the longer
// footprint dimension across the layout. Geometry within each part is intact.
function flatOrientation(size) {
  const rotation = new THREE.Quaternion();
  if (size.z < size.y && size.z <= size.x) rotation.setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2);
  else if (size.x < size.y && size.x < size.z) rotation.setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI / 2);
  return rotation;
}

function detachPrintedSpools(model) {
  const source = model.getObjectByName('servos_4');
  if (!source?.isMesh || !source.geometry.index) return [];
  const geometry = source.geometry;
  const position = geometry.attributes.position;
  const indices = geometry.index;
  const parents = Int32Array.from({ length: position.count }, (_, i) => i);
  const welded = new Map();
  const find = (value) => {
    while (parents[value] !== value) { parents[value] = parents[parents[value]]; value = parents[value]; }
    return value;
  };
  const join = (a, b) => { parents[find(a)] = find(b); };
  // CAD tessellation duplicates vertices at normal seams; position welding
  // recovers connectivity without changing any source vertex or normal.
  for (let i = 0; i < position.count; i++) {
    const key = `${position.getX(i)},${position.getY(i)},${position.getZ(i)}`;
    if (welded.has(key)) join(i, welded.get(key));
    else welded.set(key, i);
  }
  for (let i = 0; i < indices.count; i += 3) {
    join(indices.getX(i), indices.getX(i + 1));
    join(indices.getX(i), indices.getX(i + 2));
  }
  const connected = new Map();
  for (let i = 0; i < indices.count; i += 3) {
    const root = find(indices.getX(i));
    if (!connected.has(root)) connected.set(root, []);
    connected.get(root).push(indices.getX(i), indices.getX(i + 1), indices.getX(i + 2));
  }
  const components = [...connected.values()];
  model.updateMatrixWorld(true);
  const point = new THREE.Vector3();
  const verified = components.length === 16 && components.every((triangles) => {
    if (triangles.length !== 1696 * 3) return false;
    const box = new THREE.Box3();
    for (const i of triangles) box.expandByPoint(point.fromBufferAttribute(position, i).applyMatrix4(source.matrixWorld));
    const size = box.getSize(new THREE.Vector3()).toArray().sort((a, b) => a - b);
    return Math.abs(size[0] - 0.007) < 0.0002 && Math.abs(size[1] - 0.024) < 0.0002 && Math.abs(size[2] - 0.024) < 0.0002;
  });
  // A changed asset must remain intact rather than splitting unverified solids.
  if (!verified) return [];
  const spools = components.map((triangles, number) => {
    const oldVertices = [...new Set(triangles)];
    const remap = new Map(oldVertices.map((oldIndex, newIndex) => [oldIndex, newIndex]));
    const partGeometry = new THREE.BufferGeometry();
    for (const [name, attribute] of Object.entries(geometry.attributes)) {
      const original = attribute.isInterleavedBufferAttribute ? attribute.data.array : attribute.array;
      const stride = attribute.isInterleavedBufferAttribute ? attribute.data.stride : attribute.itemSize;
      const offset = attribute.isInterleavedBufferAttribute ? attribute.offset : 0;
      const values = new original.constructor(oldVertices.length * attribute.itemSize);
      oldVertices.forEach((oldIndex, newIndex) => {
        for (let axis = 0; axis < attribute.itemSize; axis++) values[newIndex * attribute.itemSize + axis] = original[oldIndex * stride + offset + axis];
      });
      partGeometry.setAttribute(name, new THREE.BufferAttribute(values, attribute.itemSize, attribute.normalized));
    }
    partGeometry.setIndex(triangles.map((oldIndex) => remap.get(oldIndex)));
    partGeometry.computeBoundingBox();
    partGeometry.computeBoundingSphere();
    const spool = new THREE.Mesh(partGeometry, source.material.clone());
    spool.name = `printed_spool_${String(number + 1).padStart(2, '0')}`;
    spool.position.copy(source.position);
    spool.quaternion.copy(source.quaternion);
    spool.scale.copy(source.scale);
    source.parent.add(spool);
    model.attach(spool);
    return spool;
  });
  source.removeFromParent();
  return spools;
}

function arrangeOnPlane(parts) {
  const gap = 0.32;
  const sideGap = 0.70;
  const motors = parts.filter((part) => /^servos$/i.test(part.node.name));
  const plates = parts.filter((part) => /^(base_plate|front_plate)/i.test(part.node.name));
  const spools = parts.filter((part) => /^printed_spool_/i.test(part.node.name));
  const other = parts.filter((part) => !motors.includes(part) && !plates.includes(part) && !spools.includes(part));
  const descending = (a, b) => b.flatSize.z - a.flatSize.z || b.flatSize.x - a.flatSize.x;
  // Read the layout from the camera: blue plates in front (+Z), then their
  // printed spools, with the remaining interfaces behind and servo bank right.
  const categories = [plates.sort(descending), spools, other.sort(descending)].filter((group) => group.length);
  const main = categories.flat();
  const minimumWidth = Math.max(...main.map((part) => part.flatSize.x));
  const maximumWidth = main.reduce((width, part) => width + part.flatSize.x + gap, -gap);
  const sideWidth = Math.max(0, ...motors.map((part) => part.flatSize.x));
  let best;
  for (let width = minimumWidth; width <= maximumWidth + 0.08; width += 0.08) {
    const rows = [];
    for (const category of categories) {
      const spacing = category === spools ? 0.12 : gap;
      let row = { parts: [], width: 0, depth: 0, spacing };
      for (const part of category) {
        const nextWidth = row.width + (row.parts.length ? spacing : 0) + part.flatSize.x;
        if (row.parts.length && nextWidth > width) {
          rows.push(row);
          row = { parts: [], width: 0, depth: 0, spacing };
        }
        row.width += (row.parts.length ? spacing : 0) + part.flatSize.x;
        row.depth = Math.max(row.depth, part.flatSize.z);
        row.parts.push(part);
      }
      rows.push(row);
    }
    const usedWidth = Math.max(...rows.map((row) => row.width));
    const usedDepth = rows.reduce((depth, row) => depth + row.depth + gap, -gap);
    const fullWidth = usedWidth + (motors.length ? sideGap + sideWidth : 0);
    const fullDepth = Math.max(usedDepth, ...motors.map((part) => part.flatSize.z));
    const ratioPenalty = Math.log(fullWidth / fullDepth / 1.40);
    const score = fullWidth * fullDepth * (1 + 1.1 * ratioPenalty * ratioPenalty);
    if (!best || score < best.score) best = { rows, width: usedWidth, depth: usedDepth, fullWidth, fullDepth, score };
  }
  const left = -best.fullWidth / 2;
  const place = (part, x, z) => {
    const flatCenter = part.flatBox.getCenter(new THREE.Vector3());
    part.targetPosition.set(x - flatCenter.x, -part.flatBox.min.y, z - flatCenter.z);
    part.targetBox = part.flatBox.clone().translate(part.targetPosition);
  };
  let z = best.depth / 2;
  for (const row of best.rows) {
    let x = left + (best.width - row.width) / 2;
    for (const part of row.parts) {
      place(part, x + part.flatSize.x / 2, z - row.depth / 2);
      x += part.flatSize.x + row.spacing;
    }
    z -= row.depth + gap;
  }
  for (const part of motors) place(part, left + best.width + sideGap + part.flatSize.x / 2, 0);
  return best;
}

function styleComponent(component) {
  const printed = /plate|transition_frame|vertebra_base|printed_spool/i.test(component.name);
  component.traverse((node) => {
    if (!node.isMesh) return;
    node.castShadow = node.receiveShadow = true;
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    const styled = materials.map((original) => {
      const material = original.clone();
      if (printed) {
        const grayInterface = /transition_frame|vertebra_base/i.test(component.name);
        material.color.setHex(grayInterface ? 0x747474 : 0x1e3765);
        material.metalness = 0.02;
        material.roughness = grayInterface ? 0.70 : 0.52;
        material.envMapIntensity = grayInterface ? 0.30 : 0.65;
      } else {
        const luminance = (original.color.r + original.color.g + original.color.b) / 3;
        const lightPart = luminance > 0.7;
        material.color.setHex(lightPart ? 0x747474 : luminance > 0.32 ? 0x99a6b7 : 0x293a51);
        material.metalness = lightPart ? 0.20 : luminance > 0.32 ? 0.48 : 0.12;
        material.roughness = lightPart ? 0.64 : 0.36;
        material.envMapIntensity = lightPart ? 0.30 : 0.65;
      }
      return material;
    });
    node.material = Array.isArray(node.material) ? styled : styled[0];
  });
}

export function initAssemblyExplorer() {
  const story = document.getElementById('assembly-story');
  const stage = document.getElementById('assembly-stage');
  const container = document.getElementById('assembly-view');
  if (!story || !stage || !container) return null;
  const status = document.getElementById('assembly-status');
  const fallback = document.getElementById('assembly-fallback');
  const meter = document.getElementById('assembly-progress');
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  let reducedMotion = preference.matches;
  let studio;
  let failed = false;
  const fail = (error) => {
    failed = true;
    if (fallback) fallback.hidden = false;
    if (studio?.renderer) studio.renderer.domElement.hidden = true;
    if (status) status.textContent = 'The 3D assembly view is unavailable. The source download includes the STEP assembly and printable parts.';
    console.warn('OpenTDCR assembly viewer:', error);
  };
  try {
    studio = createStudio(container, {
      cameraPosition: [5.4, 4.55, 7.2], target: [0, 1.35, 0], controls: false,
    });
  } catch (error) {
    fail(error);
  }

  let rawProgress = 0;
  let shownProgress = 0;
  let dirty = true;
  let loaded = false;
  let disposed = false;
  let lastMeter = -1;
  const pieces = [];
  const bounds = new THREE.Box3();
  const workBox = new THREE.Box3();
  const center = new THREE.Vector3();
  const corner = new THREE.Vector3();
  const relative = new THREE.Vector3();
  const direction = new THREE.Vector3();
  const right = new THREE.Vector3();
  const up = new THREE.Vector3();
  const identityRotation = new THREE.Quaternion();

  function readProgress() {
    const rect = story.getBoundingClientRect();
    const top = parseFloat(getComputedStyle(stage).top) || 0;
    const distance = Math.max(1, story.offsetHeight - stage.offsetHeight);
    rawProgress = clamp((top - rect.top) / distance);
    const percent = Math.round(rawProgress * 100);
    if (percent !== lastMeter) {
      story.dataset.progress = rawProgress.toFixed(3);
      story.style.setProperty('--assembly-progress', String(rawProgress));
      if (meter) {
        meter.setAttribute('aria-valuenow', String(percent));
        meter.setAttribute('aria-valuetext', percent < 12 ? 'Assembly together' : percent > 88 ? 'Components laid out flat' : 'Laying out the assembly components');
        meter.style.setProperty('--progress', String(rawProgress));
        meter.dataset.progress = rawProgress.toFixed(3);
        if (meter.tagName === 'PROGRESS') { meter.max = 100; meter.value = percent; }
      }
      lastMeter = percent;
    }
    dirty = true;
  }

  function frameParts(amount) {
    bounds.makeEmpty();
    for (const part of pieces) {
      part.pivot.position.lerpVectors(part.initialPosition, part.targetPosition, amount);
      // A small lift keeps rotating pieces clear of the common ground plane.
      part.pivot.position.y += Math.sin(Math.PI * amount) * 0.48;
      part.pivot.quaternion.slerpQuaternions(identityRotation, part.targetRotation, amount);
      part.pivot.updateMatrixWorld(true);
      // Bounds follow the rotating geometry, not just interpolated end positions.
      workBox.setFromObject(part.pivot);
      bounds.union(workBox);
    }
    direction.lerpVectors(assembledDirection, flatDirection, amount).normalize();
    right.crossVectors(worldUp, direction).normalize();
    up.crossVectors(direction, right).normalize();
    bounds.getCenter(center);
    let halfWidth = 0, halfHeight = 0, halfDepth = 0;
    for (let i = 0; i < 8; i++) {
      corner.set(i & 1 ? bounds.max.x : bounds.min.x, i & 2 ? bounds.max.y : bounds.min.y, i & 4 ? bounds.max.z : bounds.min.z);
      relative.copy(corner).sub(center);
      halfWidth = Math.max(halfWidth, Math.abs(relative.dot(right)));
      halfHeight = Math.max(halfHeight, Math.abs(relative.dot(up)));
      halfDepth = Math.max(halfDepth, Math.abs(relative.dot(direction)));
    }
    const camera = studio.camera;
    const aspect = Math.max(0.35, container.clientWidth / Math.max(1, container.clientHeight));
    const tangent = Math.tan(THREE.MathUtils.degToRad(camera.fov ?? 32) / 2);
    const distance = 1.12 * Math.max(halfHeight / tangent, halfWidth / (tangent * aspect)) + halfDepth;
    camera.position.copy(center).addScaledVector(direction, distance);
    camera.lookAt(center);
    if (studio.controls?.target) studio.controls.target.copy(center);
    story.dataset.exploded = amount.toFixed(3);
  }

  if (studio) {
    loadAssembly().then((model) => {
      if (disposed) return;
      const spools = detachPrintedSpools(model);
      const sourceBox = new THREE.Box3().setFromObject(model);
      const height = sourceBox.getSize(new THREE.Vector3()).y;
      if (!(height > 0)) throw new Error('The assembly has no measurable bounds.');
      const sourceCenter = sourceBox.getCenter(new THREE.Vector3());
      const scale = 2.7 / height;
      model.scale.multiplyScalar(scale);
      model.position.add(new THREE.Vector3(-sourceCenter.x * scale, -sourceBox.min.y * scale, -sourceCenter.z * scale));
      studio.scene.add(model);
      model.updateMatrixWorld(true);
      const roots = componentRoots(model);
      if (!roots.length) throw new Error('No known CAD components were found.');
      for (const node of roots) {
        styleComponent(node);
        const box = new THREE.Box3().setFromObject(node, true);
        const initialPosition = box.getCenter(new THREE.Vector3());
        const pivot = new THREE.Group();
        pivot.name = `${node.name}_layout_pivot`;
        pivot.position.copy(initialPosition);
        studio.scene.add(pivot);
        pivot.updateMatrixWorld(true);
        // attach preserves the complete original world transform and all children.
        pivot.attach(node);
        const targetRotation = flatOrientation(box.getSize(new THREE.Vector3()));
        pivot.position.set(0, 0, 0);
        pivot.quaternion.copy(targetRotation);
        pivot.updateMatrixWorld(true);
        let flatBox = new THREE.Box3().setFromObject(pivot, true);
        let flatSize = flatBox.getSize(new THREE.Vector3());
        if (flatSize.z > flatSize.x) {
          targetRotation.premultiply(new THREE.Quaternion().setFromAxisAngle(worldUp, Math.PI / 2));
          pivot.quaternion.copy(targetRotation);
          pivot.updateMatrixWorld(true);
          flatBox = new THREE.Box3().setFromObject(pivot, true);
          flatSize = flatBox.getSize(new THREE.Vector3());
        }
        pieces.push({ node, pivot, initialPosition, targetRotation, flatBox, flatSize, targetPosition: new THREE.Vector3() });
        pivot.position.copy(initialPosition);
        pivot.quaternion.identity();
        pivot.updateMatrixWorld(true);
      }
      arrangeOnPlane(pieces);
      loaded = true;
      dirty = true;
      story.dataset.componentCount = String(pieces.length);
      story.dataset.spoolCount = String(spools.length);
      if (fallback) fallback.hidden = true;
      if (status) status.textContent = '';
      readProgress();
    }).catch(fail);
  }

  const onPreference = (event) => { reducedMotion = event.matches; dirty = true; };
  preference.addEventListener('change', onPreference);
  window.addEventListener('scroll', readProgress, { passive: true });
  window.addEventListener('resize', readProgress, { passive: true });
  const observer = new ResizeObserver(readProgress);
  observer.observe(container);
  observer.observe(story);
  readProgress();

  let request = 0;
  let lastTime = 0;
  function animate(time) {
    if (disposed) return;
    request = requestAnimationFrame(animate);
    const dt = Math.min(0.08, Math.max(0, (time - lastTime) / 1000));
    lastTime = time;
    if (!loaded || failed || document.hidden || !studio.visible()) return;
    const delta = rawProgress - shownProgress;
    if (!dirty && Math.abs(delta) < 0.0002) return;
    shownProgress = reducedMotion ? rawProgress : shownProgress + delta * (1 - Math.exp(-dt * 10));
    const amount = reducedMotion ? (rawProgress < 0.5 ? 0 : 1) : smoothstep((shownProgress - 0.12) / 0.76);
    frameParts(amount);
    studio.render();
    dirty = false;
  }
  request = requestAnimationFrame(animate);
  return {
    dispose() {
      disposed = true;
      cancelAnimationFrame(request);
      preference.removeEventListener('change', onPreference);
      window.removeEventListener('scroll', readProgress);
      window.removeEventListener('resize', readProgress);
      observer.disconnect();
    },
  };
}
