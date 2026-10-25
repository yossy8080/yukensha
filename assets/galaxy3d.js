/* 有権者 — 天の川の帯（無数の星・星雲のにじみ・中央の暗い塵の筋・府省の節）
   帯の形は band3d.js の曲線。星はスクロール（flow）に合わせて奥から手前へ流れる。
   府省の節：帯の上に府省ごとの光の点を並べる。今の府省は物体の位置、これからの府省は奥（青白）、通り過ぎた府省は手前（琥珀）。
   API: createGalaxy({ band, isMobile, nodes }) -> { object, update(u), dispose() } */

import * as THREE from "three";
import { BAND_GLSL } from "./band3d.js";

const NOISE_GLSL = /* glsl */`
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p) { return noise(p) * 0.5 + noise(p * 2.03 + 3.1) * 0.27 + noise(p * 4.1 + 7.7) * 0.15 + noise(p * 8.3 + 1.3) * 0.08; }
// 塵の筋の通り道（帯の中心から少しずれて、ゆるく蛇行する）
float lane(float s) { return 0.05 * sin(s * 23.0 + 1.0) + 0.03 * sin(s * 61.0) + 0.04; }
`;

/* ── 星（と星雲のにじみ） ── */
const STAR_VS = /* glsl */`
${BAND_GLSL}
${NOISE_GLSL}
attribute float aS;
attribute vec2 aOff;
attribute float aSize;
attribute vec3 aCol;
attribute float aKind;
uniform float uFlow, uTime, uPR, uDim, uClear, uClearR;
uniform vec3 uCenter;
varying vec3 vCol;
varying float vA;
varying float vKind;
void main() {
  float s = fract(aS + uFlow);
  vec3 C = bandPos(s), T = bandTan(s), side, up;
  bandFrame(C, T, side, up);
  float w = bandWidth(s);
  vec3 p = C + side * aOff.x * w + up * aOff.y * w * 0.22;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  float dist = -mv.z;
  float sf = s - uFlow; // 帯の光（GLOW_FS）と同じ座標で塵の筋を決める
  float l = exp(-pow((aOff.x - lane(sf)) / 0.085, 2.0)) * smoothstep(0.3, 0.65, fbm(vec2(sf * 20.0, aOff.x * 6.0) + 7.0));
  float a = (1.0 - 0.8 * l) * mix(0.3, 1.0, exp(-aOff.x * aOff.x * 5.0));
  a *= smoothstep(1.5, 5.0, dist) * smoothstep(0.0, 0.12, s) * smoothstep(1.0, 0.93, s);
  // 物体のまわりは少し暗くして、形を読みやすくする
  a *= 1.0 - uClear * (1.0 - smoothstep(uClearR * 0.45, uClearR * 1.25, distance(p, uCenter)));
  vKind = aKind;
  if (aKind > 0.5) {
    gl_PointSize = clamp(aSize * 300.0 / dist, 2.0, 240.0) * uPR;
  } else {
    a *= 0.72 + 0.28 * sin(uTime * (0.8 + aSize) + aS * 900.0);
    float px = aSize * 26.0 / dist;
    a *= clamp(px, 0.25, 1.0); // 1px より小さい星は、大きさの代わりに明るさを落とす
    gl_PointSize = clamp(px, 1.0, 6.5) * uPR;
  }
  vCol = aCol;
  vA = a * uDim;
}`;
const STAR_FS = /* glsl */`
varying vec3 vCol;
varying float vA;
varying float vKind;
void main() {
  vec2 c = gl_PointCoord - 0.5;
  float d = dot(c, c) * 4.0;
  if (d > 1.0) discard;
  float a = vKind > 0.5 ? exp(-d * 3.2) * 0.075 : exp(-d * 5.5);
  gl_FragColor = vec4(vCol * a * vA, 1.0);
}`;

/* ── 帯の光（加算）と塵の筋（暗く重ねる）：帯に沿った細長い面 ── */
const RIBBON_VS = /* glsl */`
${BAND_GLSL}
attribute vec2 aSV;
varying float vS;
varying float vV;
varying float vFade;
void main() {
  float s = aSV.x;
  vec3 C = bandPos(s), T = bandTan(s), side, up;
  bandFrame(C, T, side, up);
  vec3 p = C + side * aSV.y * bandWidth(s) * 1.3;
  vS = s;
  vV = aSV.y * 1.3;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  vFade = smoothstep(2.0, 8.0, -mv.z) * smoothstep(0.0, 0.2, s) * smoothstep(1.0, 0.9, s);
  gl_Position = projectionMatrix * mv;
}`;
const GLOW_FS = /* glsl */`
${NOISE_GLSL}
uniform float uFlow, uDim;
varying float vS;
varying float vV;
varying float vFade;
void main() {
  float sf = vS - uFlow;
  float n = fbm(vec2(sf * 34.0, vV * 3.2));
  float core = exp(-vV * vV * 6.0), body = exp(-vV * vV * 1.7);
  float glow = (core * 0.6 + body * 0.28) * (0.35 + 1.0 * n);
  float l = exp(-pow((vV - lane(sf)) / 0.085, 2.0)) * smoothstep(0.3, 0.65, fbm(vec2(sf * 20.0, vV * 6.0) + 7.0));
  glow *= 1.0 - 0.8 * l;
  vec3 col = mix(vec3(0.38, 0.47, 0.86), vec3(1.0, 0.86, 0.68), core * 0.55);
  col = mix(col, vec3(0.72, 0.55, 0.98), smoothstep(0.55, 0.8, fbm(vec2(sf * 9.0, vV * 2.0) + 3.0)) * 0.45);
  gl_FragColor = vec4(col * glow * 0.15 * vFade * uDim, 1.0);
}`;
const DUST_FS = /* glsl */`
${NOISE_GLSL}
uniform float uFlow, uDim;
varying float vS;
varying float vV;
varying float vFade;
void main() {
  float sf = vS - uFlow;
  float l = exp(-pow((vV - lane(sf)) / 0.075, 2.0)) * smoothstep(0.3, 0.65, fbm(vec2(sf * 20.0, vV * 6.0) + 7.0));
  l *= 0.7 + 0.3 * fbm(vec2(sf * 70.0, vV * 14.0));
  gl_FragColor = vec4(0.008, 0.012, 0.024, l * 0.6 * vFade * (0.5 + 0.5 * uDim));
}`;

/* ── 府省の節 ── */
const NODE_VS = /* glsl */`
${BAND_GLSL}
attribute float aK;
uniform float uF, uStep, uS0, uPR, uSettled, uDim, uTime;
varying vec3 vCol;
varying float vA;
void main() {
  float d = aK - uF;               // >0 これからの府省、<0 通り過ぎた府省
  float s = uS0 - d * uStep;
  vec3 p = bandPos(s);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  float dist = -mv.z;
  float cur = 1.0 - smoothstep(0.0, 0.6, abs(d));
  float vis = smoothstep(0.0, 0.05, s) * smoothstep(0.98, 0.88, s) * smoothstep(1.5, 5.0, dist);
  vis *= 1.0 - uSettled * cur * 0.92; // 今の府省の節は、物体そのものになっている
  vCol = mix(vec3(0.74, 0.86, 1.0), vec3(1.0, 0.76, 0.48), smoothstep(0.35, -0.35, d));
  vCol = mix(vCol, vec3(1.0), cur * 0.4);
  vA = vis * uDim * (0.85 + 0.15 * sin(uTime * 1.4 + aK * 1.7));
  gl_PointSize = clamp(56.0 * 8.0 / dist, 7.0, 72.0) * uPR;
}`;
const NODE_FS = /* glsl */`
varying vec3 vCol;
varying float vA;
void main() {
  vec2 c = gl_PointCoord - 0.5;
  float r = length(c) * 2.0;
  if (r > 1.0) discard;
  float core = exp(-r * r * 60.0) * 1.8, halo = exp(-r * r * 7.0) * 0.32, ring = exp(-pow((r - 0.56) / 0.045, 2.0)) * 0.45;
  gl_FragColor = vec4(vCol * (core + halo + ring) * vA, 1.0);
}`;

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}
function vnoise2(x, y) {
  const h = (i, j) => { const s = Math.sin(i * 127.1 + j * 311.7) * 43758.5453; return s - Math.floor(s); };
  const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const a = h(xi, yi) + (h(xi + 1, yi) - h(xi, yi)) * u, b = h(xi, yi + 1) + (h(xi + 1, yi + 1) - h(xi, yi + 1)) * u;
  return a + (b - a) * v;
}

export function createGalaxy({ band, isMobile, nodes = 0 }) {
  const object = new THREE.Group();
  const r = rng(2024);
  const gauss = () => (r() + r() + r() + r() - 2) / 2; // おおよそ -1..1、中心に集まる

  /* 星：中心ほど濃く、ところどころ星団のように固まる */
  const NS = isMobile ? 11000 : 26000, NN = isMobile ? 50 : 90;
  const N = NS + NN;
  const aS = new Float32Array(N), aOff = new Float32Array(N * 2), aSize = new Float32Array(N), aCol = new Float32Array(N * 3), aKind = new Float32Array(N);
  let i = 0;
  while (i < NS) {
    const s = r(), x = gauss() * 0.75, y = gauss();
    const clump = vnoise2(s * 46, x * 4) * 0.7 + vnoise2(s * 130, x * 9 + 5) * 0.3;
    if (r() > 0.25 + clump * 0.95) continue;
    aS[i] = s; aOff[i * 2] = x; aOff[i * 2 + 1] = y;
    const k = r();
    aSize[i] = k < 0.04 ? 1.8 + r() * 1.0 : k < 0.28 ? 1.0 + r() * 0.6 : 0.5 + r() * 0.5;
    const c = r();
    const rgb = c < 0.1 ? [1.0, 0.82, 0.6] : c < 0.2 ? [0.8, 0.72, 1.0] : [0.82 + r() * 0.12, 0.88 + r() * 0.08, 1.0];
    aCol.set(rgb, i * 3);
    i++;
  }
  for (; i < N; i++) {
    aS[i] = r(); aOff[i * 2] = gauss() * 0.6; aOff[i * 2 + 1] = gauss() * 0.5;
    aSize[i] = 0.5 + r() * 0.9; aKind[i] = 1;
    const c = r();
    aCol.set(c < 0.4 ? [0.62, 0.45, 0.95] : c < 0.65 ? [1.0, 0.7, 0.42] : [0.45, 0.62, 1.0], i * 3);
  }
  const starGeo = new THREE.BufferGeometry();
  starGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(N * 3), 3)); // 位置はシェーダーで決める
  starGeo.setAttribute("aS", new THREE.BufferAttribute(aS, 1));
  starGeo.setAttribute("aOff", new THREE.BufferAttribute(aOff, 2));
  starGeo.setAttribute("aSize", new THREE.BufferAttribute(aSize, 1));
  starGeo.setAttribute("aCol", new THREE.BufferAttribute(aCol, 3));
  starGeo.setAttribute("aKind", new THREE.BufferAttribute(aKind, 1));
  const common = { uFlow: { value: 0 }, uTime: { value: 0 }, uPR: { value: 1 }, uDim: { value: 1 } };
  const starMat = new THREE.ShaderMaterial({
    vertexShader: STAR_VS, fragmentShader: STAR_FS,
    uniforms: { ...band.uniforms, ...common, uClear: { value: 0 }, uClearR: { value: 1.5 }, uCenter: { value: new THREE.Vector3() } },
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  const stars = new THREE.Points(starGeo, starMat);
  stars.frustumCulled = false;
  stars.renderOrder = 3;

  /* 帯の光と塵の筋 */
  const SEG = isMobile ? 220 : 360, ACR = 14;
  const sv = [], idx = [];
  for (let a = 0; a <= SEG; a++) for (let b = 0; b <= ACR; b++) sv.push(Math.pow(a / SEG, 0.85), (b / ACR) * 2 - 1);
  for (let a = 0; a < SEG; a++) for (let b = 0; b < ACR; b++) {
    const k = a * (ACR + 1) + b;
    idx.push(k, k + ACR + 1, k + 1, k + 1, k + ACR + 1, k + ACR + 2);
  }
  const ribGeo = new THREE.BufferGeometry();
  ribGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array((sv.length / 2) * 3), 3));
  ribGeo.setAttribute("aSV", new THREE.Float32BufferAttribute(sv, 2));
  ribGeo.setIndex(idx);
  const ribU = { ...band.uniforms, uFlow: common.uFlow, uDim: common.uDim };
  const glowMat = new THREE.ShaderMaterial({ vertexShader: RIBBON_VS, fragmentShader: GLOW_FS, uniforms: ribU, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide });
  const dustMat = new THREE.ShaderMaterial({ vertexShader: RIBBON_VS, fragmentShader: DUST_FS, uniforms: ribU, transparent: true, depthWrite: false, side: THREE.DoubleSide });
  const glow = new THREE.Mesh(ribGeo, glowMat), dust = new THREE.Mesh(ribGeo, dustMat);
  glow.frustumCulled = dust.frustumCulled = false;
  glow.renderOrder = 1;
  dust.renderOrder = 2;

  /* 府省の節 */
  const nodeGeo = new THREE.BufferGeometry();
  nodeGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(Math.max(1, nodes) * 3), 3));
  nodeGeo.setAttribute("aK", new THREE.BufferAttribute(Float32Array.from({ length: Math.max(1, nodes) }, (_, k) => k), 1));
  const nodeMat = new THREE.ShaderMaterial({
    vertexShader: NODE_VS, fragmentShader: NODE_FS,
    uniforms: { ...band.uniforms, uF: { value: -1 }, uStep: { value: 0.055 }, uS0: { value: 0.62 }, uPR: common.uPR, uSettled: { value: 0 }, uDim: common.uDim, uTime: common.uTime },
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  const nodePts = new THREE.Points(nodeGeo, nodeMat);
  nodePts.frustumCulled = false;
  nodePts.renderOrder = 4;
  nodePts.visible = nodes > 0;

  object.add(glow, dust, stars, nodePts);

  // u = { time, flow, f, step, s0, pr, settled, center, radius, dim }
  function update(u) {
    common.uTime.value = u.time;
    common.uFlow.value = u.flow;
    common.uPR.value = u.pr;
    common.uDim.value = u.dim;
    starMat.uniforms.uClear.value = u.settled * 0.75;
    starMat.uniforms.uClearR.value = u.radius;
    starMat.uniforms.uCenter.value.copy(u.center);
    nodeMat.uniforms.uF.value = u.f;
    nodeMat.uniforms.uStep.value = u.step;
    nodeMat.uniforms.uS0.value = u.s0;
    nodeMat.uniforms.uSettled.value = u.settled;
  }

  function dispose() {
    [starGeo, ribGeo, nodeGeo].forEach((g) => g.dispose());
    [starMat, glowMat, dustMat, nodeMat].forEach((m) => m.dispose());
  }
  return { object, update, dispose };
}
