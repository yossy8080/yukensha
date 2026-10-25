/* 有権者 — 光の粒子でできた府省の物体と、次の府省への変形
   すべての物体を同じ数の点で表し、今の形（position）→ 次の形（aTo）へ補間する。
   途中は天の川の帯に吸い込まれて渦を巻き、流れに沿ってほどけてから、次の形に集まる。
   API: createMorph({ count, band }) -> { object, setShapes(a, b), update(u), pick(raycaster, which), dispose() } */

import * as THREE from "three";
import { BAND_GLSL } from "./band3d.js";

const VS = /* glsl */`
${BAND_GLSL}
attribute vec3 aTo;
attribute vec4 aRnd; // x: ほどける順のゆらぎ, y: 帯の中の位置, z: 帯の中心からの距離, w: 帯をまわる角度
attribute vec3 aCol;
uniform float uP, uTime, uScale, uSize, uPR, uHover, uFlow, uS0, uSpan, uBright;
uniform vec3 uCenter;
uniform mat3 uRot;
varying vec3 vCol;
varying float vA;

// ABC 流れ（発散のない渦の場）。粒子を流れに巻き込むのに使う
vec3 abc(vec3 p) { return vec3(sin(p.z) + cos(p.y), sin(p.x) + cos(p.z), sin(p.y) + cos(p.x)); }

void main() {
  bool forming = uP >= 0.5;
  vec3 S = uCenter + uRot * (forming ? aTo : position) * uScale;
  // ほどけるときは流れの下流側（手前）から、集まるときは上流側（奥）から
  vec3 T0 = bandTan(uS0);
  float lead = clamp(dot(S - uCenter, T0) / (2.6 * uScale) + 0.5, 0.0, 1.0);
  float order = mix(aRnd.x, forming ? lead : 1.0 - lead, 0.6);
  const float ST = 0.45;
  float q = clamp(uP * (1.0 + ST) - ST * order, 0.0, 1.0);
  float wb = smoothstep(0.0, 0.28, q) * smoothstep(1.0, 0.72, q); // 帯の中にいる度合い
  float wbS = wb * wb * (3.0 - 2.0 * wb);

  // 帯の中の位置（スクロールと時間で下流へ流れ、窓の端で消えて上流から現れる）
  float fr = fract(aRnd.y + uFlow);
  float s = uS0 + uSpan * (fr - 0.5);
  vec3 C = bandPos(s), T = bandTan(s), side, up;
  bandFrame(C, T, side, up);
  // 帯の中では、物体の場所に渦を巻く光の塊になる（中心ほど速く回る）
  float r = aRnd.z * bandWidth(s) * 0.34;
  float th = aRnd.w * 6.2831853 + (uTime * 0.5 + uP * 7.0) * (1.4 - aRnd.z);
  vec3 BP = C + side * cos(th) * r + up * sin(th) * r * 0.45;

  vec3 p = mix(S, BP, wbS);
  // 形と帯のあいだ：渦を巻き、流れの向きへ引き延ばされる
  float mid = 4.0 * wbS * (1.0 - wbS);
  p += abc(p * 0.85 + vec3(uTime * 0.21, uTime * 0.17, 0.0)) * 0.24 * mid * uScale;
  p += T * mid * (forming ? -1.0 : 1.0) * (0.4 + aRnd.x) * 0.9 * uScale;

  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  float edge = smoothstep(0.0, 0.12, fr) * smoothstep(1.0, 0.88, fr);
  vA = mix(1.0, edge * 0.7, wb) * uBright * (0.82 + 0.18 * sin(uTime * 1.7 + aRnd.y * 40.0)) * (1.0 + uHover * 0.55);
  vCol = mix(aCol, vec3(0.78, 0.84, 1.0), wb * 0.35);
  float size = uSize * mix(1.0, 0.8, wb) * (0.7 + 0.6 * aRnd.x) * (1.0 + uHover * 0.12);
  gl_PointSize = clamp(size * uPR * 9.0 / -mv.z, 0.0, 10.0 * uPR);
}`;

const FS = /* glsl */`
varying vec3 vCol;
varying float vA;
void main() {
  vec2 c = gl_PointCoord - 0.5;
  float d = dot(c, c) * 4.0;
  if (d > 1.0) discard;
  float a = exp(-d * 3.5) - 0.03;
  gl_FragColor = vec4(vCol * max(a, 0.0) * vA, 1.0);
}`;

// 形の上にごく薄く重ねる面（輪郭がにじんで光る）
const SURF_VS = /* glsl */`
varying vec3 vN;
varying vec3 vV;
void main() {
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vN = normalize(mat3(modelMatrix) * normal);
  vV = normalize(cameraPosition - wp.xyz);
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;
const SURF_FS = /* glsl */`
uniform vec3 uC;
uniform float uO;
varying vec3 vN;
varying vec3 vV;
void main() {
  float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.5);
  gl_FragColor = vec4(uC * (0.01 + f * 0.15) * uO, 1.0);
}`;

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

export function createMorph({ count, band }) {
  const r = rng(99);
  const geo = new THREE.BufferGeometry();
  const posA = new Float32Array(count * 3), posB = new Float32Array(count * 3);
  const rnd = new Float32Array(count * 4), col = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    // 帯の中心ほど多く（ガウスに近い分布）
    const g = Math.min(1, Math.abs((r() + r() + r() - 1.5) / 1.5) * 1.15);
    rnd.set([r(), r(), g, r()], i * 4);
    const k = r();
    // 青白い白を基調に、ほんのり紫と琥珀
    const c = k < 0.12 ? [0.82, 0.74, 1.0] : k < 0.22 ? [1.0, 0.84, 0.62] : [0.8 + r() * 0.1, 0.88 + r() * 0.06, 1.0];
    col.set(c, i * 3);
  }
  geo.setAttribute("position", new THREE.BufferAttribute(posA, 3));
  geo.setAttribute("aTo", new THREE.BufferAttribute(posB, 3));
  geo.setAttribute("aRnd", new THREE.BufferAttribute(rnd, 4));
  geo.setAttribute("aCol", new THREE.BufferAttribute(col, 3));
  geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e4); // 位置はシェーダーで決めるので、視錐台で切らない

  const uniforms = {
    ...band.uniforms,
    uP: { value: 0.5 }, uTime: { value: 0 }, uScale: { value: 1 }, uSize: { value: 2.2 }, uPR: { value: 1 },
    uHover: { value: 0 }, uFlow: { value: 0 }, uS0: { value: 0.62 }, uSpan: { value: 0.075 }, uBright: { value: 1 },
    uCenter: { value: new THREE.Vector3() }, uRot: { value: new THREE.Matrix3() },
  };
  const mat = new THREE.ShaderMaterial({
    vertexShader: VS, fragmentShader: FS, uniforms,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  const points = new THREE.Points(geo, mat);
  points.frustumCulled = false;
  points.renderOrder = 6;

  const object = new THREE.Group();
  object.add(points);
  // 落ち着いた形に重ねる、ごく薄い輪郭線と面（今の形 A と次の形 B）
  const holders = [0, 1].map(() => {
    const h = new THREE.Group();
    const lineMat = new THREE.LineBasicMaterial({ color: 0xa8d4ff, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
    const surfMat = new THREE.ShaderMaterial({
      vertexShader: SURF_VS, fragmentShader: SURF_FS, side: THREE.DoubleSide,
      uniforms: { uC: { value: new THREE.Color(0x8fc4ff) }, uO: { value: 0 } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const lines = new THREE.LineSegments(new THREE.BufferGeometry(), lineMat);
    const surf = new THREE.Mesh(new THREE.BufferGeometry(), surfMat);
    lines.renderOrder = 7;
    surf.renderOrder = 5;
    h.add(surf, lines);
    h.visible = false;
    h.matrixAutoUpdate = false;
    object.add(h);
    return { h, lines, surf, lineMat, surfMat };
  });

  let cur = [null, null];
  function setShapes(a, b) {
    if (cur[0] !== a) { posA.set(a.pts); geo.attributes.position.needsUpdate = true; }
    if (cur[1] !== b) { posB.set(b.pts); geo.attributes.aTo.needsUpdate = true; }
    [a, b].forEach((s, k) => {
      holders[k].lines.geometry = s.model.edges;
      holders[k].surf.geometry = s.model.merged;
    });
    cur = [a, b];
  }

  const _m4 = new THREE.Matrix4();
  // u = { p, time, center, scale, rot(Matrix4), flow, hover, pr, bright, size }
  function update(u) {
    uniforms.uP.value = u.p;
    uniforms.uTime.value = u.time;
    uniforms.uCenter.value.copy(u.center);
    uniforms.uScale.value = u.scale;
    uniforms.uRot.value.setFromMatrix4(u.rot);
    uniforms.uFlow.value = u.flow;
    uniforms.uHover.value = u.hover;
    uniforms.uPR.value = u.pr;
    uniforms.uBright.value = u.bright;
    uniforms.uSize.value = u.size;
    // 形が落ち着いているほど輪郭と面を見せる
    const settle = [1 - smooth(0.0, 0.16, u.p), smooth(0.84, 1.0, u.p)];
    if (cur[0] === cur[1]) settle[1] = 0;
    _m4.compose(u.center, new THREE.Quaternion().setFromRotationMatrix(u.rot), new THREE.Vector3(u.scale, u.scale, u.scale));
    holders.forEach((h, k) => {
      const o = settle[k] * u.bright;
      h.h.visible = o > 0.01;
      h.h.matrix.copy(_m4);
      h.lineMat.opacity = o * (0.13 + u.hover * 0.12);
      h.surfMat.uniforms.uO.value = o * (1 + u.hover * 0.8);
    });
  }

  // which = 0（今の形）/ 1（次の形）。面に当たるか、中心近くなら当たり
  const _sph = new THREE.Sphere();
  function pick(raycaster, which) {
    const h = holders[which];
    if (!cur[which]) return false;
    h.h.updateMatrixWorld(true);
    if (raycaster.intersectObject(h.surf, false).length) return true;
    _sph.set(uniforms.uCenter.value, cur[which].model.radius * uniforms.uScale.value * 0.55);
    return raycaster.ray.intersectsSphere(_sph);
  }

  function dispose() {
    geo.dispose();
    mat.dispose();
    holders.forEach((h) => { h.lineMat.dispose(); h.surfMat.dispose(); });
  }

  return { object, setShapes, update, pick, dispose, uniforms };
}

function smooth(a, b, x) {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
}
