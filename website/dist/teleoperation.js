/** Scroll-led, illustrative teleoperation sequence. All assets are native SVG. */
const SVG_NS = 'http://www.w3.org/2000/svg';
const INK = '#1e3765';
const LINE = '#dce1e8';
const SOFT = '#f3f4f5';
const TENDONS = [INK, '#657b9e', '#a8b4c7'];
const clamp = (value, min = 0, max = 1) => Math.max(min, Math.min(max, value));
const smooth = value => { const x = clamp(value); return x * x * (3 - 2 * x); };
const number = value => (Math.abs(value) < 0.005 ? 0 : value).toFixed(2);
const pathFrom = points => points.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' ');

function element(tag, attrs = {}, parent, content) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (content !== undefined) node.textContent = content;
  if (parent) parent.appendChild(node);
  return node;
}
function label(parent, x, y, content, size = 15, attrs = {}) {
  return element('text', { x, y, fill: INK, 'font-size': size, 'text-anchor': 'middle', ...attrs }, parent, content);
}
function line(parent, x1, y1, x2, y2, attrs = {}) {
  return element('line', { x1, y1, x2, y2, stroke: INK, 'stroke-width': 2, 'stroke-linecap': 'round', ...attrs }, parent);
}

/** Fixed pivots and rigid link lengths, shared by drawing and geometry checks. */
function inputDevicePose(time) {
  const joystickPivot = { x: 320, y: 291 };
  const joystickAngle = 0.26 * Math.sin(time * 0.85);
  const shaftLength = 64;
  const joystickTip = {
    x: joystickPivot.x + shaftLength * Math.sin(joystickAngle),
    y: joystickPivot.y - shaftLength * Math.cos(joystickAngle)
  };
  const base = { x: 514, y: 285 };
  const lengths = [53, 57];
  const shoulderAngle = -0.72 + 0.18 * Math.sin(time * 0.62);
  const elbowAngle = 1.65 + 0.23 * Math.sin(time * 0.62 + 1.15);
  const elbow = {
    x: base.x + lengths[0] * Math.sin(shoulderAngle),
    y: base.y - lengths[0] * Math.cos(shoulderAngle)
  };
  const wrist = {
    x: elbow.x + lengths[1] * Math.sin(shoulderAngle + elbowAngle),
    y: elbow.y - lengths[1] * Math.cos(shoulderAngle + elbowAngle)
  };
  return { joystickPivot, joystickAngle, joystickTip, shaftLength, base, elbow, wrist, lengths,
    stylusAngle: 24 + 9 * Math.sin(time * 0.62 + 0.6) };
}

function makeInput(parent) {
  const keyboard = element('g', { transform: 'translate(43 218)' }, parent);
  element('path', { d: 'M0 8 L156 8 L156 95 Q156 101 150 101 H6 Q0 101 0 95 Z', fill: '#e7ebf0', stroke: INK, 'stroke-width': 1.5 }, keyboard);
  element('rect', { x: 0, y: 0, width: 156, height: 94, rx: 9, fill: SOFT, stroke: INK, 'stroke-width': 1.7 }, keyboard);
  const keys = [];
  for (let row = 0; row < 3; row += 1) {
    for (let col = 0; col < 7; col += 1) {
      keys.push(element('rect', { x: 12 + col * 19, y: 13 + row * 19, width: 14, height: 13, rx: 2, fill: '#fff', stroke: LINE, 'stroke-width': 1 }, keyboard));
    }
  }
  element('rect', { x: 40, y: 73, width: 75, height: 10, rx: 2, fill: '#fff', stroke: LINE }, keyboard);
  label(parent, 121, 358, 'Keyboard');

  const joystick = element('g', {}, parent);
  element('ellipse', { cx: 320, cy: 332, rx: 60, ry: 8, fill: '#f0f2f5' }, joystick);
  element('path', { d: 'M264 289 L376 289 L376 313 Q371 328 320 332 Q269 328 264 313 Z', fill: '#e5eaf1', stroke: INK, 'stroke-width': 1.6 }, joystick);
  element('path', { d: 'M273 279 Q320 263 367 279 Q377 283 376 291 Q366 309 320 314 Q274 309 264 291 Q263 283 273 279 Z', fill: '#fff', stroke: INK, 'stroke-width': 1.6 }, joystick);
  element('ellipse', { cx: 320, cy: 291, rx: 26, ry: 11, fill: SOFT, stroke: LINE }, joystick);
  element('ellipse', { cx: 320, cy: 291, rx: 18, ry: 8, fill: '#e0e6ee', stroke: '#b5c1d1' }, joystick);
  // The shaft and complete grip are a single rigid body about this pivot.
  const stick = element('g', {}, joystick);
  line(stick, 0, 0, 0, -64, { stroke: INK, 'stroke-width': 10 });
  line(stick, -1.5, -5, -1.5, -64, { stroke: '#dce3ed', 'stroke-width': 5 });
  element('path', { d: 'M-10 -48 Q-15 -63 -12 -83 Q-10 -95 3 -94 Q15 -93 16 -83 L12 -58 Q11 -48 4 -44 Z', fill: INK, stroke: INK, 'stroke-width': 1.3 }, stick);
  element('path', { d: 'M-7 -78 Q-7 -88 2 -88 L8 -87', fill: 'none', stroke: '#7184a3', 'stroke-width': 2, 'stroke-linecap': 'round' }, stick);
  element('path', { d: 'M11 -74 Q20 -71 16 -62 L11 -62', fill: '#e7ebf1', stroke: INK, 'stroke-width': 1.3 }, stick);
  element('ellipse', { cx: 2, cy: -91, rx: 5, ry: 2.4, fill: '#dce3ed' }, stick);
  element('ellipse', { cx: 320, cy: 291, rx: 10, ry: 4, fill: INK }, joystick);
  element('ellipse', { cx: 353, cy: 291, rx: 5, ry: 3, fill: INK }, joystick);
  label(parent, 320, 358, 'Joystick');

  const haptic = element('g', {}, parent);
  element('ellipse', { cx: 518, cy: 332, rx: 59, ry: 8, fill: '#f0f2f5' }, haptic);
  element('path', { d: 'M468 298 L552 288 L566 309 L566 322 L481 336 L468 322 Z', fill: '#e5eaf1', stroke: INK, 'stroke-width': 1.6 }, haptic);
  element('path', { d: 'M468 298 L551 287 L566 309 L482 321 Z', fill: '#fff', stroke: INK, 'stroke-width': 1.6 }, haptic);
  line(haptic, 482, 321, 482, 335, { 'stroke-width': 1.2 });
  element('path', { d: 'M501 304 L501 280 Q514 268 527 280 L527 301 Q514 311 501 304 Z', fill: '#e6ebf2', stroke: INK, 'stroke-width': 1.5 }, haptic);
  const links = Array.from({ length: 2 }, () => {
    const group = element('g', {}, haptic);
    const edge = line(group, 0, 0, 0, 0, { stroke: INK, 'stroke-width': 11 });
    const body = line(group, 0, 0, 0, 0, { stroke: '#e0e6ee', 'stroke-width': 8 });
    const highlight = line(group, 0, 0, 0, 0, { stroke: '#fff', 'stroke-width': 2, opacity: 0.8 });
    return [edge, body, highlight];
  });
  const joints = [8, 7, 5].map(r => element('circle', { r, fill: '#fff', stroke: INK, 'stroke-width': 1.7 }, haptic));
  const jointCenters = [3, 2.5].map(r => element('circle', { r, fill: '#a7b5c9' }, haptic));
  const stylus = element('g', {}, haptic);
  element('ellipse', { cx: 0, cy: 0, rx: 9, ry: 6, fill: '#fff', stroke: INK, 'stroke-width': 1.4 }, stylus);
  element('ellipse', { cx: 0, cy: 0, rx: 4, ry: 8, fill: 'none', stroke: '#8a9bb5', 'stroke-width': 1.2 }, stylus);
  line(stylus, -16, 0, 22, 0, { stroke: INK, 'stroke-width': 6 });
  line(stylus, -13, -1.5, 15, -1.5, { stroke: '#8b9bb3', 'stroke-width': 1.3 });
  element('path', { d: 'M22 -3 L31 0 L22 3 Z', fill: INK }, stylus);
  element('rect', { x: 7, y: -4, width: 6, height: 2.5, rx: 1, fill: '#dce3ed' }, stylus);
  label(parent, 515, 358, 'Haptic device');
  label(parent, 515, 383, 'Adapter extension', 12, { opacity: 0.62 });

  element('path', { d: 'M121 414 V435 H515 V414 M320 414 V455', fill: 'none', stroke: LINE, 'stroke-width': 1.4 }, parent);
  element('circle', { cx: 320, cy: 455, r: 4, fill: INK }, parent);
  return time => {
    const activeKey = [3, 9, 10, 11][Math.floor(time * 1.5) % 4];
    keys.forEach((key, index) => key.setAttribute('fill', index === activeKey ? INK : '#fff'));
    const pose = inputDevicePose(time);
    stick.setAttribute('transform', `translate(${pose.joystickPivot.x} ${pose.joystickPivot.y}) rotate(${pose.joystickAngle * 180 / Math.PI})`);
    const points = [pose.base, pose.elbow, pose.wrist];
    links.forEach((parts, index) => parts.forEach(part => {
      part.setAttribute('x1', points[index].x); part.setAttribute('y1', points[index].y);
      part.setAttribute('x2', points[index + 1].x); part.setAttribute('y2', points[index + 1].y);
    }));
    joints.forEach((joint, index) => { joint.setAttribute('cx', points[index].x); joint.setAttribute('cy', points[index].y); });
    jointCenters.forEach((joint, index) => { joint.setAttribute('cx', points[index].x); joint.setAttribute('cy', points[index].y); });
    stylus.setAttribute('transform', `translate(${pose.wrist.x} ${pose.wrist.y}) rotate(${pose.stylusAngle})`);
  };
}

function coordinates(time, index) {
  return { x: 0.62 * Math.sin(time * 0.65 + index * 1.45), y: 0.52 * Math.cos(time * 0.53 + index * 1.15) };
}
function makeCoordinates(parent) {
  const pads = ['Base', 'Middle', 'Tip'].map((name, index) => {
    const cx = 138 + index * 182, cy = 263, radius = 70;
    label(parent, cx, 156, name, 16);
    element('circle', { cx, cy, r: radius, fill: SOFT, stroke: LINE, 'stroke-width': 1.2 }, parent);
    line(parent, cx - radius, cy, cx + radius, cy, { stroke: '#dce1e8', 'stroke-width': 1 });
    line(parent, cx, cy - radius, cx, cy + radius, { stroke: '#dce1e8', 'stroke-width': 1 });
    label(parent, cx + radius + 13, cy + 4, 'qₓ', 12, { opacity: 0.66 });
    label(parent, cx + 2, cy + radius + 23, 'qᵧ', 12, { opacity: 0.66 });
    element('circle', { cx, cy, r: 2, fill: INK, opacity: 0.5 }, parent);
    const vector = line(parent, cx, cy, cx, cy, { 'stroke-width': 1.4, opacity: 0.45 });
    const halo = element('circle', { cx, cy, r: 13, fill: INK, opacity: 0.055 }, parent);
    const point = element('circle', { cx, cy, r: 7, fill: INK, stroke: '#fff', 'stroke-width': 2 }, parent);
    const value = label(parent, cx, 402, '', 13, { 'font-variant-numeric': 'tabular-nums' });
    return { cx, cy, radius, vector, point, halo, value };
  });
  return time => pads.forEach((pad, index) => {
    const q = coordinates(time, index);
    // Positive q_y is down on screen, matching the hero's Clarke controls.
    const x = pad.cx + q.x * pad.radius, y = pad.cy + q.y * pad.radius;
    pad.vector.setAttribute('x2', x); pad.vector.setAttribute('y2', y);
    for (const point of [pad.point, pad.halo]) { point.setAttribute('cx', x); point.setAttribute('cy', y); }
    pad.value.textContent = `${number(q.x)}  ,  ${number(q.y)} mm`;
  });
}

/** A constant-curvature planar illustration, with multiple serial segments. */
function backbone(angles, lengths, base = { x: 258, y: 435 }) {
  const points = [{ ...base, angle: 0 }];
  let x = base.x, y = base.y, angle = 0;
  angles.forEach((bend, segment) => {
    const steps = 28, ds = lengths[segment] / steps;
    for (let step = 0; step < steps; step += 1) {
      const midpointAngle = angle + bend / steps / 2;
      x += Math.sin(midpointAngle) * ds; y -= Math.cos(midpointAngle) * ds;
      angle += bend / steps;
      points.push({ x, y, angle, segment });
    }
  });
  return points;
}
function makeRobot(parent, discCount, baseX = 258) {
  element('ellipse', { cx: baseX, cy: 456, rx: 64, ry: 9, fill: '#f0f2f5' }, parent);
  element('path', { d: `M${baseX - 42} 435 Q${baseX} 420 ${baseX + 42} 435 L${baseX + 42} 450 Q${baseX} 466 ${baseX - 42} 450 Z`, fill: SOFT, stroke: LINE, 'stroke-width': 1.2 }, parent);
  element('ellipse', { cx: baseX, cy: 435, rx: 42, ry: 12, fill: '#fff', stroke: LINE, 'stroke-width': 1.2 }, parent);
  const tendonBack = element('path', { fill: 'none', stroke: TENDONS[2], 'stroke-width': 1.7, 'stroke-linecap': 'round' }, parent);
  const center = element('path', { fill: 'none', stroke: '#cdd5df', 'stroke-width': 7, 'stroke-linecap': 'round' }, parent);
  const discs = Array.from({ length: discCount }, () => element('ellipse', { rx: 19, ry: 5.6, fill: '#fff', stroke: '#bcc6d3', 'stroke-width': 1.2 }, parent));
  const tendons = [
    element('path', { fill: 'none', stroke: TENDONS[0], 'stroke-width': 1.8, 'stroke-linecap': 'round' }, parent),
    element('path', { fill: 'none', stroke: TENDONS[1], 'stroke-width': 1.5, 'stroke-linecap': 'round' }, parent),
    tendonBack
  ];
  const cap = element('ellipse', { rx: 19, ry: 5.6, fill: '#e8ecf2', stroke: INK, 'stroke-width': 1.5 }, parent);
  return points => {
    center.setAttribute('d', pathFrom(points));
    // Three equally spaced tendon paths, with a small oblique depth projection.
    tendons.forEach((tendon, index) => {
      const psi = index * Math.PI * 2 / 3;
      const side = 14 * Math.cos(psi), depth = 14 * Math.sin(psi);
      tendon.setAttribute('d', pathFrom(points.map(point => ({
        x: point.x + Math.cos(point.angle) * side + .3 * depth,
        y: point.y + Math.sin(point.angle) * side - .3 * depth
      }))));
    });
    discs.forEach((disc, index) => {
      const point = points[Math.round(index * (points.length - 1) / (discCount - 1))];
      disc.setAttribute('cx', point.x); disc.setAttribute('cy', point.y);
      disc.setAttribute('transform', `rotate(${point.angle * 180 / Math.PI} ${point.x} ${point.y})`);
    });
    const tip = points[points.length - 1];
    cap.setAttribute('cx', tip.x); cap.setAttribute('cy', tip.y);
    cap.setAttribute('transform', `rotate(${tip.angle * 180 / Math.PI} ${tip.x} ${tip.y})`);
    return tip;
  };
}
/** Inverse Clarke map, Eq. 6; positive pull shortens a tendon (Eq. 13).
 * https://arxiv.org/html/2503.12265v1 — uniformly spaced, equal-radius tendons.
 */
function clarkePulls(q, count) {
  return Array.from({ length: count }, (_, index) => {
    const psi = index * Math.PI * 2 / count;
    return q.x * Math.cos(psi) + q.y * Math.sin(psi);
  });
}

/** A spatial arc with transported cross-sections; q and tendon radius are mm. */
function spatialSegment(q, length = 55, radius = 3, divisions = 42) {
  const magnitude = Math.hypot(q.x, q.y), theta = magnitude / radius;
  const nx = magnitude > 1e-9 ? q.x / magnitude : 1;
  const ny = magnitude > 1e-9 ? q.y / magnitude : 0;
  return Array.from({ length: divisions + 1 }, (_, index) => {
    const u = index / divisions, angle = theta * u;
    const c = Math.cos(angle), s = Math.sin(angle);
    const lateral = theta > 1e-9 ? length * (1 - c) / theta : 0;
    return {
      center: { x: nx * lateral, y: ny * lateral, z: theta > 1e-9 ? length * s / theta : length * u },
      dx: { x: 1 + (c - 1) * nx * nx, y: (c - 1) * nx * ny, z: -s * nx },
      dy: { x: (c - 1) * nx * ny, y: 1 + (c - 1) * ny * ny, z: -s * ny }
    };
  });
}
function tendonPoint(sample, psi, radius = 3) {
  const a = radius * Math.cos(psi), b = radius * Math.sin(psi);
  return {
    x: sample.center.x + a * sample.dx.x + b * sample.dy.x,
    y: sample.center.y + a * sample.dx.y + b * sample.dy.y,
    z: sample.center.z + a * sample.dx.z + b * sample.dy.z
  };
}
function projectSegment(point) {
  // y points toward the camera: positive q_y bends down on screen, as in the hero.
  return { x: 213 + 4.8 * (point.x + 0.22 * point.y), y: 435 + 4.8 * (0.42 * point.y - point.z) };
}

function makeTendons(parent) {
  const counts = [3, 4, 6, 8];
  const colors = [INK, '#526c93', '#8b9db7', '#3d5b85', '#7890b0', '#acb8ca', '#647d9f', '#93a4bc'];
  element('ellipse', { cx: 213, cy: 456, rx: 64, ry: 9, fill: '#f0f2f5' }, parent);
  element('path', { d: 'M171 435 Q213 420 255 435 L255 450 Q213 466 171 450 Z', fill: SOFT, stroke: LINE, 'stroke-width': 1.2 }, parent);
  element('ellipse', { cx: 213, cy: 435, rx: 42, ry: 12, fill: '#fff', stroke: LINE, 'stroke-width': 1.2 }, parent);
  const robot = element('g', { 'data-tendon-rig': '' }, parent);
  const center = element('path', { fill: 'none', stroke: '#cdd5df', 'stroke-width': 6, 'stroke-linecap': 'round' }, robot);
  const discs = Array.from({ length: 16 }, () => element('path', { fill: '#fff', stroke: '#bdc7d5', 'stroke-width': 1.1 }, robot));
  const paths = Array.from({ length: 8 }, (_, index) => element('path', { fill: 'none', stroke: colors[index], 'stroke-width': 1.6, 'stroke-linecap': 'round', 'data-tendon': index + 1 }, robot));
  const cap = element('path', { fill: '#eef1f6', stroke: INK, 'stroke-width': 1.4 }, robot);
  label(parent, 486, 146, 'Clarke transform', 21);
  const mapping = label(parent, 486, 177, '', 16);
  label(parent, 580, 208, 'mm', 12, { opacity: 0.6 });
  const subscript = ['₁', '₂', '₃', '₄', '₅', '₆', '₇', '₈'];
  const bars = Array.from({ length: 8 }, (_, index) => {
    const group = element('g', { 'data-tendon-bar': index + 1 }, parent);
    label(group, 397, 4, `ρ${subscript[index]}`, 15);
    line(group, 424, 0, 536, 0, { stroke: LINE, 'stroke-width': 3.5 });
    line(group, 480, -7, 480, 7, { stroke: '#b8c3d1', 'stroke-width': 1 });
    const bar = line(group, 480, 0, 480, 0, { stroke: colors[index], 'stroke-width': 3.5 });
    const marker = element('circle', { cx: 480, cy: 0, r: 3.5, fill: colors[index] }, group);
    const value = label(group, 580, 4, '', 13, { 'font-variant-numeric': 'tabular-nums' });
    return { group, bar, marker, value };
  });
  let lastCount = 0;
  return time => {
    const count = counts[Math.floor(time / 3.8) % counts.length];
    const q = { x: 2.0 * Math.sin(time * 0.62), y: 1.4 * Math.cos(time * 0.47) };
    const samples = spatialSegment(q);
    const pulls = clarkePulls(q, count);
    if (count !== lastCount) {
      lastCount = count; robot.dataset.tendonCount = count;
      mapping.textContent = `2 coordinates → ${count} tendons`;
      paths.forEach((path, index) => path.setAttribute('display', index < count ? 'inline' : 'none'));
      bars.forEach((bar, index) => {
        bar.group.setAttribute('display', index < count ? 'inline' : 'none');
        // Fixed row spacing for legibility; shorter lists remain vertically centered.
        bar.group.setAttribute('transform', `translate(0 ${325 + (index - (count - 1) / 2) * 28})`);
      });
    }
    center.setAttribute('d', pathFrom(samples.map(sample => projectSegment(sample.center))));
    const crossSection = sample => `${pathFrom(Array.from({ length: 33 }, (_, index) => projectSegment(tendonPoint(sample, index * Math.PI * 2 / 32, 3.7))))} Z`;
    discs.forEach((disc, index) => disc.setAttribute('d', crossSection(samples[Math.round(index * (samples.length - 1) / (discs.length - 1))])));
    cap.setAttribute('d', crossSection(samples[samples.length - 1]));
    for (let index = 0; index < count; index += 1) {
      const psi = index * Math.PI * 2 / count;
      paths[index].setAttribute('d', pathFrom(samples.map(sample => projectSegment(tendonPoint(sample, psi)))));
      const x = 480 + 21 * pulls[index];
      bars[index].bar.setAttribute('x2', x); bars[index].marker.setAttribute('cx', x);
      bars[index].value.textContent = number(pulls[index]);
    }
  };
}

function actuationPoints(time) {
  const phase = time * 0.48;
  return backbone([
    0.18 + 0.37 * Math.sin(phase),
    0.1 + 0.46 * Math.sin(phase + 1.3),
    0.2 + 0.42 * Math.sin(phase + 2.4)
  ], [91, 91, 91]);
}
function makeActuation(parent) {
  const trailPoints = Array.from({ length: 181 }, (_, index) => {
    const points = actuationPoints(index * Math.PI * 2 / 180 / 0.48);
    return points[points.length - 1];
  });
  element('path', { d: `${pathFrom(trailPoints)} Z`, fill: 'none', stroke: '#ccd4e0', 'stroke-width': 1.5, 'stroke-dasharray': '3 6', 'stroke-linecap': 'round' }, parent);
  label(parent, 430, 112, 'Tip trajectory', 13, { opacity: 0.72 });
  const drawRobot = makeRobot(parent, 22);
  const halo = element('circle', { r: 15, fill: INK, opacity: 0.08 }, parent);
  const tipDot = element('circle', { r: 6, fill: INK, stroke: '#fff', 'stroke-width': 2 }, parent);
  const tangent = line(parent, 0, 0, 0, 0, { stroke: INK, 'stroke-width': 2, opacity: 0.8 });
  return time => {
    const tip = drawRobot(actuationPoints(time));
    for (const node of [halo, tipDot]) { node.setAttribute('cx', tip.x); node.setAttribute('cy', tip.y); }
    const futurePoints = actuationPoints(time + 0.15), future = futurePoints[futurePoints.length - 1];
    const dx = future.x - tip.x, dy = future.y - tip.y, magnitude = Math.hypot(dx, dy) || 1;
    tangent.setAttribute('x1', tip.x + dx / magnitude * 13); tangent.setAttribute('y1', tip.y + dy / magnitude * 13);
    tangent.setAttribute('x2', tip.x + dx / magnitude * 32); tangent.setAttribute('y2', tip.y + dy / magnitude * 32);
  };
}

export function initTeleoperationStory() {
  const story = document.getElementById('teleoperation-story');
  const container = document.getElementById('teleoperation-view');
  if (!story || !container || container.dataset.initialized === 'true') return;
  container.dataset.initialized = 'true';
  const svg = element('svg', { viewBox: '0 0 640 540', width: '100%', height: '100%', 'aria-hidden': 'true', focusable: 'false', style: 'display:block;overflow:visible;font-family:var(--body, sans-serif)' }, container);
  const groups = Array.from({ length: 4 }, () => element('g', { opacity: 0 }, svg));
  const renderers = [makeInput(groups[0]), makeCoordinates(groups[1]), makeTendons(groups[2]), makeActuation(groups[3])];
  const steps = [...story.querySelectorAll('.teleoperation-step')];
  const phases = [...story.querySelectorAll('.teleoperation-sequence [data-phase]')];
  const progressbar = document.getElementById('teleoperation-progress');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let visible = false, frame = 0, lastTime = 0, elapsed = 1.2, progress = 0, targetProgress = 0, activeStage = -1;
  const readProgress = () => {
    const bounds = story.getBoundingClientRect();
    targetProgress = clamp(-bounds.top / Math.max(1, bounds.height - window.innerHeight));
  };
  const setStage = index => {
    if (index === activeStage) return;
    activeStage = index; story.dataset.stage = String(index);
    steps.forEach((step, stepIndex) => {
      const active = stepIndex === index;
      step.classList.toggle('is-active', active);
      step.setAttribute('aria-hidden', String(!active));
      step.inert = !active;
    });
    phases.forEach((phase, phaseIndex) => {
      const active = phaseIndex === index;
      phase.classList.toggle('is-active', active);
      phase.setAttribute('aria-current', active ? 'step' : 'false');
    });
  };
  const draw = now => {
    frame = 0;
    const delta = lastTime ? Math.min(now - lastTime, 64) : 16;
    lastTime = now;
    if (!reducedMotion.matches) elapsed += delta / 1000;
    progress = reducedMotion.matches ? targetProgress : progress + (targetProgress - progress) * (1 - Math.exp(-delta / 90));
    if (Math.abs(progress - targetProgress) < 0.0001) progress = targetProgress;
    const stage = Math.min(3, Math.floor(progress * 4));
    setStage(stage);
    story.style.setProperty('--progress', progress);
    story.dataset.progress = progress.toFixed(3);
    if (progressbar) {
      progressbar.style.setProperty('--progress', progress);
      progressbar.setAttribute('aria-valuenow', String(Math.round(progress * 100)));
    }
    const time = reducedMotion.matches ? 1.2 : elapsed;
    groups.forEach((group, index) => {
      const fadeIn = index === 0 ? 1 : smooth((progress - index / 4 + 0.025) / 0.05);
      const fadeOut = index === 3 ? 1 : 1 - smooth((progress - (index + 1) / 4 + 0.025) / 0.05);
      const opacity = reducedMotion.matches ? Number(stage === index) : Math.min(fadeIn, fadeOut);
      group.setAttribute('opacity', opacity.toFixed(3));
      group.setAttribute('transform', `translate(${reducedMotion.matches ? 0 : (1 - fadeIn) * 22 - (1 - fadeOut) * 22} 0)`);
      if (opacity > 0) renderers[index](time);
    });
    if (visible && !document.hidden && (!reducedMotion.matches || progress !== targetProgress)) frame = requestAnimationFrame(draw);
  };
  const schedule = () => { if (visible && !document.hidden && !frame) frame = requestAnimationFrame(draw); };
  const onScroll = () => { readProgress(); schedule(); };
  const onVisibility = () => {
    if (document.hidden && frame) { cancelAnimationFrame(frame); frame = 0; }
    lastTime = 0; schedule();
  };
  const observer = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    if (!visible && frame) { cancelAnimationFrame(frame); frame = 0; }
    lastTime = 0; readProgress(); schedule();
  });
  observer.observe(story);
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll, { passive: true });
  document.addEventListener('visibilitychange', onVisibility);
  reducedMotion.addEventListener('change', onVisibility);
  readProgress(); progress = targetProgress; draw(performance.now());
  return () => {
    if (frame) cancelAnimationFrame(frame);
    observer.disconnect();
    window.removeEventListener('scroll', onScroll); window.removeEventListener('resize', onScroll);
    document.removeEventListener('visibilitychange', onVisibility); reducedMotion.removeEventListener('change', onVisibility);
    svg.remove(); delete container.dataset.initialized;
  };
}
