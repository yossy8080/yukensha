/* 有権者 — 天の川の帯の通り道（3次ベジェ曲線）
   帯は奥の空（t=0）から、府省の物体の少し後ろ（t=S0）を通って、カメラの横（t=1）へ流れてくる。
   同じ式を JS（節の位置）と GLSL（星・粒子）の両方で使う。 */

import * as THREE from "three";

export const S0 = 0.62; // 物体のところの帯のパラメータ

export const BAND_GLSL = /* glsl */`
uniform vec3 uB0, uB1, uB2, uB3;
vec3 bandPos(float t) {
  float u = 1.0 - t;
  return u * u * u * uB0 + 3.0 * u * u * t * uB1 + 3.0 * u * t * t * uB2 + t * t * t * uB3;
}
vec3 bandTan(float t) {
  float u = 1.0 - t;
  return normalize(3.0 * u * u * (uB1 - uB0) + 6.0 * u * t * (uB2 - uB1) + 3.0 * t * t * (uB3 - uB2));
}
// 帯の半幅（遠くは広く、物体のあたりは物体と同じくらい）
float bandWidth(float t) { return mix(13.0, 1.9, smoothstep(0.0, 0.6, t)); }
// 帯の横方向（いつもカメラに広い面を向ける）と厚み方向
void bandFrame(vec3 p, vec3 T, out vec3 side, out vec3 up) {
  vec3 v = normalize(cameraPosition - p);
  side = normalize(cross(T, v));
  up = normalize(cross(side, T));
}
`;

export function createBand() {
  const P = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
  const uniforms = { uB0: { value: P[0] }, uB1: { value: P[1] }, uB2: { value: P[2] }, uB3: { value: P[3] } };
  const _a = new THREE.Vector3();

  // C = 物体の中心（ワールド）。帯が t=S0 で物体の少し奥を通るように P2 を解く
  function setAnchor(C, mobile) {
    // 始まり（t=0）は画面の外の、左上の遠い空
    P[0].set(mobile ? -70 : -120, mobile ? 70 : 46, -150);
    P[1].set(mobile ? -14 : -26, mobile ? 16 : 10, -60);
    P[3].set(C.x + (mobile ? 4.5 : 8), C.y - (mobile ? 3.0 : 1.6), 13); // 手前の端も海面より上を通る
    _a.copy(C).add(new THREE.Vector3(0, 0, -1.1));
    const t = S0, u = 1 - t, a = u * u * u, b = 3 * u * u * t, c = 3 * u * t * t, d = t * t * t;
    P[2].copy(_a).addScaledVector(P[0], -a).addScaledVector(P[1], -b).addScaledVector(P[3], -d).multiplyScalar(1 / c);
  }
  function pos(t, out) {
    const u = 1 - t;
    return out.set(0, 0, 0).addScaledVector(P[0], u * u * u).addScaledVector(P[1], 3 * u * u * t)
      .addScaledVector(P[2], 3 * u * t * t).addScaledVector(P[3], t * t * t);
  }
  function width(t) {
    const k = Math.min(1, Math.max(0, t / 0.6)), s = k * k * (3 - 2 * k);
    return 13 + (1.9 - 13) * s;
  }
  return { P, uniforms, setAnchor, pos, width };
}
