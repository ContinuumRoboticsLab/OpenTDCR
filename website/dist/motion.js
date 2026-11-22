import * as THREE from 'three';
import { createStudio } from './studio.js';
import { loadAssembly } from './cad.js';

// A representative constant-curvature backbone, not a calibrated digital twin.
// Clarke coordinates are tendon-pull coordinates (mm); |q| / r is bend in radians.
const TENDON_RADIUS_MM = 3;
const LIMIT_MM = 3.2;
const SEGMENTS = 3;
const STEPS = 30;
const LENGTH = .88;
const BASE_HEIGHT = .94;
const TENDON_OFFSETS = [0, -Math.PI / 6, -Math.PI / 3];
const PAD_RADIUS = 48;
const NAMES = ['Base', 'Middle', 'Tip'];
const round = value => (Math.abs(value) < .005 ? 0 : value).toFixed(2);
const ease = t => t * t * t * (t * (t * 6 - 15) + 10);
const clampVector = (x, y) => {
  const scale = Math.min(1, LIMIT_MM / Math.max(Math.hypot(x, y), 1e-8));
  return [x * scale, y * scale];
};

function makeTube(count, radius, sides = 7) {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(count * sides * 3);
  const normals = new Float32Array(positions.length);
  const indices = new Uint16Array((count - 1) * sides * 6);
  let offset = 0;
  for (let row = 0; row < count - 1; row++) {
    for (let col = 0; col < sides; col++) {
      const a = row * sides + col, b = row * sides + (col + 1) % sides;
      indices.set([a, a + sides, b, b, a + sides, b + sides], offset);
      offset += 6;
    }
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3).setUsage(THREE.DynamicDrawUsage));
  geometry.setAttribute('normal', new THREE.BufferAttribute(normals, 3).setUsage(THREE.DynamicDrawUsage));
  geometry.setIndex(new THREE.BufferAttribute(indices, 1));
  const radial = Array.from({ length: sides }, (_, i) => new THREE.Vector3(Math.cos(i * 2 * Math.PI / sides), 0, Math.sin(i * 2 * Math.PI / sides)));
  const n = new THREE.Vector3(), p = new THREE.Vector3(), center = new THREE.Vector3();
  return {
    geometry,
    update(points, rotations, localOffset) {
      for (let row = 0; row < count; row++) {
        center.copy(localOffset).applyQuaternion(rotations[row]).add(points[row]);
        for (let col = 0; col < sides; col++) {
          n.copy(radial[col]).applyQuaternion(rotations[row]);
          p.copy(n).multiplyScalar(radius).add(center);
          const at = (row * sides + col) * 3;
          positions[at] = p.x; positions[at + 1] = p.y; positions[at + 2] = p.z;
          normals[at] = n.x; normals[at + 1] = n.y; normals[at + 2] = n.z;
        }
      }
      geometry.attributes.position.needsUpdate = true;
      geometry.attributes.normal.needsUpdate = true;
    }
  };
}

// Match the assembly explorer's presentation finishes. loadAssembly() gives
// this viewer independent materials; the supplied CAD geometry stays intact.
function styleAssembly(model, ownedMaterials) {
  model.traverse(node => {
    if (!node.isMesh) return;
    node.castShadow = node.receiveShadow = true;
    let component = node;
    while (component !== model && !/plate|transition_frame|vertebra_base/i.test(component.name)) component = component.parent;
    const printed = component !== model;
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    for (const material of materials) {
      if (!material?.color) continue;
      if (printed) {
        const grayInterface = /transition_frame|vertebra_base/i.test(component.name);
        material.color.setHex(grayInterface ? 0x747474 : 0x1e3765);
        material.metalness = .02;
        material.roughness = grayInterface ? .70 : .52;
        material.envMapIntensity = grayInterface ? .30 : .65;
      } else {
        const luminance = (material.color.r + material.color.g + material.color.b) / 3;
        const lightPart = luminance > .7;
        material.color.setHex(lightPart ? 0x747474 : luminance > .32 ? 0x99a6b7 : 0x293a51);
        material.metalness = lightPart ? .20 : luminance > .32 ? .48 : .12;
        material.roughness = lightPart ? .64 : .36;
        material.envMapIntensity = lightPart ? .30 : .65;
      }
      ownedMaterials.push(material);
    }
  });
}

function locateBackboneMount(model, anchor) {
  let mount;
  model.traverse(node => { if (!mount && /^vertebra_base(?:_|$)/i.test(node.name)) mount = node; });
  if (!mount) return;
  model.updateMatrixWorld(true);
  const bounds = new THREE.Box3().setFromObject(mount);
  const topFace = new THREE.Box3();
  const vertex = new THREE.Vector3();
  const tolerance = Math.max((bounds.max.y - bounds.min.y) * .0001, .000001);
  mount.traverse(node => {
    const positions = node.isMesh && node.geometry.getAttribute('position');
    if (!positions) return;
    for (let index = 0; index < positions.count; index++) {
      vertex.fromBufferAttribute(positions, index).applyMatrix4(node.matrixWorld);
      if (vertex.y >= bounds.max.y - tolerance) topFace.expandByPoint(vertex);
    }
  });
  // The supplied upper mount is offset from the full assembly's AABB center.
  // Its highest face locates the backbone socket without changing the CAD.
  (topFace.isEmpty() ? bounds : topFace).getCenter(anchor);
  anchor.y = bounds.max.y;
}

export function initMotionExplorer() {
  const container = document.getElementById('motion-view');
  if (!container) return null;
  const status = document.getElementById('motion-status');
  const toggle = document.getElementById('motion-toggle');
  const help = document.getElementById('motion-help');
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  let automatic = !preference.matches;
  let contextLost = false;
  let disposed = false;
  let dirty = true;
  const listeners = [];
  const listen = (element, event, fn, options) => {
    if (!element) return;
    element.addEventListener(event, fn, options);
    listeners.push(() => element.removeEventListener(event, fn, options));
  };
  const states = [
    { x: .8, y: .3 }, { x: -1.4, y: .8 }, { x: .7, y: -1.1 }
  ].map((pose, index) => ({ ...pose, index, fromX: pose.x, fromY: pose.y, targetX: pose.x, targetY: pose.y, elapsed: 0, duration: 4, hover: false, keyboardFocus: false, pointer: null }));
  function beginWander(state) {
    const angle = Math.random() * Math.PI * 2;
    const radius = (.18 + Math.random() * .60) * LIMIT_MM;
    state.fromX = state.x; state.fromY = state.y;
    state.targetX = Math.cos(angle) * radius;
    state.targetY = Math.sin(angle) * radius;
    state.elapsed = 0;
    state.duration = 3.8 + Math.random() * 2.8;
  }
  states.forEach(beginWander);

  let studio;
  try {
    studio = createStudio(container, { cameraPosition: [3.4, 2.6, 7.1], target: [0, 1.8, 0], controls: false });
    listen(studio.renderer.domElement, 'webglcontextlost', event => {
      event.preventDefault(); contextLost = true;
      if (status) { status.hidden = false; status.textContent = 'The 3D view is temporarily unavailable.'; }
    });
    listen(studio.renderer.domElement, 'webglcontextrestored', () => {
      contextLost = false; dirty = true;
      if (status) { status.textContent = ''; status.hidden = true; }
    });
  } catch (error) {
    if (status) { status.hidden = false; status.textContent = '3D viewing requires WebGL. The segment controls remain available.'; }
    console.warn('OpenTDCR motion viewer:', error);
  }

  const points = Array.from({ length: SEGMENTS * STEPS + 1 }, () => new THREE.Vector3());
  const rotations = Array.from({ length: points.length }, () => new THREE.Quaternion());
  const backboneAnchor = new THREE.Vector3(0, BASE_HEIGHT, 0);
  const generatedGeometry = [], generatedMaterials = [];
  const rings = [], ribs = [], tubes = [];
  const dummy = new THREE.Object3D();
  const zero = new THREE.Vector3();
  const direction = new THREE.Vector3(0, 1, 0);
  const axis = new THREE.Vector3();
  const dq = new THREE.Quaternion(), halfway = new THREE.Quaternion(), orientation = new THREE.Quaternion();
  const p = new THREE.Vector3(), q = new THREE.Quaternion();
  const local = new THREE.Vector3();
  const cameraTarget = new THREE.Vector3(0, 1.8, 0);
  const cameraDirection = new THREE.Vector3(3.4, .8, 7.1).normalize();
  const cameraRight = new THREE.Vector3(cameraDirection.z, 0, -cameraDirection.x).normalize();
  const cameraUp = new THREE.Vector3().crossVectors(cameraDirection, cameraRight);
  const cameraRelative = new THREE.Vector3();
  const baseCorners = Array.from({ length: 8 }, () => new THREE.Vector3());
  const minimumCameraDistance = Math.hypot(3.4, .8, 7.1);
  const ringCount = 13;
  let tip;
  const material = options => {
    const value = new THREE.MeshStandardMaterial(options); generatedMaterials.push(value); return value;
  };
  if (studio) {
    const ringGeometry = new THREE.TorusGeometry(.064, .0065, 6, 28).rotateX(Math.PI / 2);
    const ribGeometry = new THREE.CylinderGeometry(.0025, .0025, .058, 5).rotateZ(Math.PI / 2);
    generatedGeometry.push(ringGeometry, ribGeometry);
    for (let segment = 0; segment < SEGMENTS; segment++) {
      const finish = material({ color: [0xcbd5e5, 0x91a5c0, 0x5f7fa9][segment], metalness: .48, roughness: .35 });
      const ring = new THREE.InstancedMesh(ringGeometry, finish, ringCount);
      const rib = new THREE.InstancedMesh(ribGeometry, finish, ringCount * 3);
      for (const mesh of [ring, rib]) {
        mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
        mesh.frustumCulled = false;
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        studio.scene.add(mesh);
      }
      rings.push(ring); ribs.push(rib);
    }
    const addTube = (count, radius, offset, color, roughness) => {
      const tube = makeTube(count, radius);
      const mesh = new THREE.Mesh(tube.geometry, material({ color, metalness: .72, roughness }));
      mesh.frustumCulled = false; mesh.castShadow = true;
      studio.scene.add(mesh); generatedGeometry.push(tube.geometry);
      tubes.push({ ...tube, offset });
    };
    addTube(points.length, .016, zero, 0x7f91a9, .27);
    for (let segment = 0; segment < SEGMENTS; segment++) {
      for (let tendon = 0; tendon < 3; tendon++) {
        const angle = TENDON_OFFSETS[segment] + tendon * 2 * Math.PI / 3;
        addTube((segment + 1) * STEPS + 1, .0028, new THREE.Vector3(.054 * Math.cos(angle), 0, .054 * Math.sin(angle)), [0x1e3765, 0x708bab, 0xa6b8cf][segment], .34);
      }
    }
    const tipGeometry = new THREE.SphereGeometry(.026, 20, 12);
    generatedGeometry.push(tipGeometry);
    tip = new THREE.Mesh(tipGeometry, material({ color: 0x1e3765, metalness: .6, roughness: .24 }));
    studio.scene.add(tip);
    // The actual actuation CAD supports the illustrative backbone. No invented
    // backbone is written into the source model or described as measured geometry.
    loadAssembly().then(model => {
      if (disposed) return;
      const bounds = new THREE.Box3().setFromObject(model);
      const dimensions = bounds.getSize(new THREE.Vector3());
      const center = bounds.getCenter(new THREE.Vector3());
      const scale = BASE_HEIGHT / dimensions.y;
      model.scale.setScalar(scale);
      model.position.set(-center.x * scale, -bounds.min.y * scale, -center.z * scale);
      styleAssembly(model, generatedMaterials);
      locateBackboneMount(model, backboneAnchor);
      for (let corner = 0; corner < 8; corner++) {
        baseCorners[corner].set((corner & 1 ? .5 : -.5) * dimensions.x * scale, corner & 2 ? BASE_HEIGHT : 0, (corner & 4 ? .5 : -.5) * dimensions.z * scale);
      }
      studio.scene.add(model);
      if (status) { status.textContent = ''; status.hidden = true; }
      dirty = true;
    }).catch(error => {
      if (disposed) return;
      if (status) { status.hidden = false; status.textContent = 'Actuation model unavailable. The backbone is illustrative.'; }
      console.warn('OpenTDCR actuation asset:', error);
    });
  }

  function fitCamera() {
    if (!studio) return;
    const aspect = Math.max(.2, container.clientWidth / Math.max(1, container.clientHeight));
    const camera = studio.camera;
    const tangent = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
    const horizontal = tangent * aspect;
    let distance = minimumCameraDistance;
    // Fit the full animated centerline and actual base corners in camera space.
    // Perspective depth and a margin for the rings keep dragged poses in view
    // even on a narrow phone, without shrinking the default desktop pose.
    for (let index = 0; index < points.length + baseCorners.length; index++) {
      const point = index < points.length ? points[index] : baseCorners[index - points.length];
      cameraRelative.copy(point).sub(cameraTarget);
      const depth = cameraRelative.dot(cameraDirection) + .12;
      distance = Math.max(distance, depth + (Math.abs(cameraRelative.dot(cameraRight)) + .12) / horizontal, depth + (Math.abs(cameraRelative.dot(cameraUp)) + .12) / tangent);
    }
    camera.position.copy(cameraTarget).addScaledVector(cameraDirection, distance);
    camera.lookAt(cameraTarget);
    if (camera.aspect !== aspect) { camera.aspect = aspect; camera.updateProjectionMatrix(); }
  }

  const resizeObserver = new ResizeObserver(() => { dirty = true; });
  resizeObserver.observe(container);

  function updateBackbone() {
    p.copy(backboneAnchor); q.identity();
    points[0].copy(p); rotations[0].copy(q);
    let index = 0;
    for (let segment = 0; segment < SEGMENTS; segment++) {
      const state = states[segment];
      const norm = Math.hypot(state.x, state.y);
      const angle = norm / TENDON_RADIUS_MM / STEPS;
      if (norm > 1e-9) axis.set(state.y / norm, 0, -state.x / norm);
      else axis.set(0, 0, 1);
      dq.setFromAxisAngle(axis, angle);
      halfway.setFromAxisAngle(axis, angle * .5);
      for (let step = 0; step < STEPS; step++) {
        orientation.copy(q).multiply(halfway);
        local.copy(direction).applyQuaternion(orientation).multiplyScalar(LENGTH / STEPS);
        p.add(local); q.multiply(dq);
        index++;
        points[index].copy(p); rotations[index].copy(q);
      }
    }
    if (!studio) return;
    for (const tube of tubes) tube.update(points, rotations, tube.offset);
    for (let segment = 0; segment < SEGMENTS; segment++) {
      for (let ring = 0; ring < ringCount; ring++) {
        const at = segment * STEPS + Math.round(ring * STEPS / (ringCount - 1));
        dummy.position.copy(points[at]); dummy.quaternion.copy(rotations[at]); dummy.updateMatrix();
        rings[segment].setMatrixAt(ring, dummy.matrix);
        for (let rib = 0; rib < 3; rib++) {
          const angle = TENDON_OFFSETS[segment] + rib * 2 * Math.PI / 3;
          local.set(.030 * Math.cos(angle), 0, .030 * Math.sin(angle)).applyQuaternion(rotations[at]);
          dummy.position.copy(points[at]).add(local);
          orientation.setFromAxisAngle(direction, -angle);
          dummy.quaternion.copy(rotations[at]).multiply(orientation);
          dummy.updateMatrix(); ribs[segment].setMatrixAt(ring * 3 + rib, dummy.matrix);
        }
      }
      rings[segment].instanceMatrix.needsUpdate = true;
      ribs[segment].instanceMatrix.needsUpdate = true;
    }
    tip.position.copy(points[points.length - 1]);
    fitCamera();
  }

  const pads = Array.from(document.querySelectorAll('.clark-pad'));
  const bindings = pads.map(pad => {
    const state = states[Number(pad.dataset.segment)];
    if (!state) return null;
    const parent = pad.closest('.segment-control') || pad.parentElement;
    const handle = pad.querySelector('.pad-handle');
    const vector = pad.querySelector('.pad-vector');
    const xOutput = parent?.querySelector('.coord-x');
    const yOutput = parent?.querySelector('.coord-y');
    pad.tabIndex = 0;
    pad.setAttribute('role', 'group');
    pad.setAttribute('aria-roledescription', 'two-dimensional control');
    if (help) pad.setAttribute('aria-describedby', help.id);
    pad.style.touchAction = 'none';
    const held = () => state.hover || state.keyboardFocus || state.pointer !== null;
    const refreshMode = () => {
      pad.dataset.mode = held() ? 'manual' : automatic ? 'automatic' : 'paused';
      pad.classList.toggle('is-manual', held());
      pad.classList.toggle('is-dragging', state.pointer !== null);
    };
    const resume = () => { beginWander(state); refreshMode(); };
    const setFromPointer = event => {
      const box = pad.getBoundingClientRect();
      const radius = Math.min(box.width, box.height) * PAD_RADIUS / 120;
      if (!radius) return;
      // Keep mathematical +y bending toward world +Z (the viewer); the pad
      // presents that direction downward, like moving toward the near edge.
      const [x, y] = clampVector((event.clientX - box.left - box.width / 2) / radius * LIMIT_MM, (event.clientY - box.top - box.height / 2) / radius * LIMIT_MM);
      state.x = x; state.y = y; dirty = true;
      renderPad();
    };
    const renderPad = () => {
      const cx = 60 + PAD_RADIUS * state.x / LIMIT_MM;
      const cy = 60 + PAD_RADIUS * state.y / LIMIT_MM;
      if (handle?.tagName.toLowerCase() === 'circle') {
        handle.setAttribute('cx', cx); handle.setAttribute('cy', cy);
      } else if (handle) {
        handle.style.left = `${cx / 1.2}%`; handle.style.top = `${cy / 1.2}%`;
      }
      if (vector) { vector.setAttribute('x2', cx); vector.setAttribute('y2', cy); }
      if (xOutput) xOutput.textContent = round(state.x);
      if (yOutput) yOutput.textContent = round(state.y);
      pad.setAttribute('aria-label', `${NAMES[state.index]} segment Clarke coordinates: x ${round(state.x)}, y ${round(state.y)} millimetres. Drag or use arrow keys; down bends toward the viewer. Home centers.`);
      refreshMode();
    };
    listen(pad, 'pointerenter', () => { state.hover = true; refreshMode(); });
    listen(pad, 'pointerleave', () => { state.hover = false; if (state.pointer === null) resume(); });
    listen(pad, 'focus', () => { state.keyboardFocus = state.pointer === null && pad.matches(':focus-visible'); refreshMode(); });
    listen(pad, 'blur', () => { state.keyboardFocus = false; resume(); });
    listen(pad, 'pointerdown', event => {
      if (event.button !== 0) return;
      event.preventDefault(); state.pointer = event.pointerId; state.keyboardFocus = false;
      pad.focus({ preventScroll: true }); pad.setPointerCapture(event.pointerId);
      setFromPointer(event); refreshMode();
    });
    listen(pad, 'pointermove', event => { if (event.pointerId === state.pointer) setFromPointer(event); });
    const endPointer = event => {
      if (event.pointerId !== state.pointer) return;
      state.pointer = null;
      const box = pad.getBoundingClientRect();
      state.hover = event.pointerType !== 'touch' && event.clientX >= box.left && event.clientX <= box.right && event.clientY >= box.top && event.clientY <= box.bottom;
      if (pad.hasPointerCapture(event.pointerId)) pad.releasePointerCapture(event.pointerId);
      resume();
    };
    listen(pad, 'pointerup', endPointer);
    listen(pad, 'pointercancel', event => { state.hover = false; endPointer(event); state.hover = false; resume(); });
    listen(pad, 'lostpointercapture', event => { if (state.pointer === event.pointerId) { state.pointer = null; state.hover = false; resume(); } });
    listen(pad, 'keydown', event => {
      const step = event.shiftKey ? .4 : .12;
      const delta = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowDown: [0, step], ArrowUp: [0, -step] }[event.key];
      if (!delta && event.key !== 'Home') return;
      event.preventDefault(); state.keyboardFocus = true;
      [state.x, state.y] = event.key === 'Home' ? [0, 0] : clampVector(state.x + delta[0], state.y + delta[1]);
      dirty = true; renderPad();
    });
    renderPad();
    return { state, held, renderPad, refreshMode };
  }).filter(Boolean);

  function updateToggle() {
    if (toggle) {
      toggle.textContent = automatic ? 'Pause motion' : 'Resume motion';
      toggle.setAttribute('aria-pressed', String(!automatic));
      toggle.setAttribute('aria-label', automatic ? 'Pause automatic robot motion' : 'Resume automatic robot motion');
    }
    bindings.forEach(binding => binding.refreshMode());
  }
  function setAutomatic(value) {
    automatic = value;
    states.forEach(beginWander);
    updateToggle();
  }
  listen(toggle, 'click', () => setAutomatic(!automatic));
  listen(preference, 'change', event => { if (event.matches) setAutomatic(false); });
  updateToggle(); updateBackbone();
  let frameId = 0, previous = 0, lastPaint = 0;
  const frame = now => {
    if (disposed) return;
    frameId = requestAnimationFrame(frame);
    if (document.hidden || contextLost || (studio && !studio.visible())) { previous = now; return; }
    if (now - lastPaint < 1000 / 30) return;
    const dt = previous ? Math.min((now - previous) / 1000, .08) : 0;
    previous = now; lastPaint = now;
    if (automatic) {
      for (const state of states) {
        if (state.hover || state.keyboardFocus || state.pointer !== null) continue;
        state.elapsed = Math.min(state.duration, state.elapsed + dt);
        const amount = ease(state.elapsed / state.duration);
        state.x = THREE.MathUtils.lerp(state.fromX, state.targetX, amount);
        state.y = THREE.MathUtils.lerp(state.fromY, state.targetY, amount);
        if (state.elapsed >= state.duration) beginWander(state);
        dirty = true;
      }
    }
    if (dirty) { updateBackbone(); bindings.forEach(binding => binding.renderPad()); dirty = false; }
    studio?.render();
  };
  frameId = requestAnimationFrame(frame);
  return {
    pause: () => setAutomatic(false),
    resume: () => setAutomatic(true),
    dispose() {
      disposed = true; cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
      listeners.forEach(remove => remove());
      generatedGeometry.forEach(geometry => geometry.dispose());
      generatedMaterials.forEach(value => value.dispose());
      studio?.dispose?.();
    }
  };
}
