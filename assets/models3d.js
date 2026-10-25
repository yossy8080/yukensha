/* 有権者 — 府省を表す物体（手続き的に作る 3D モデル）
   公式ロゴ・紋章・赤十字は使わない。外部のモデルファイルも使わず、Three.js のプリミティブ・押し出し・Lathe・Tube だけで作る。
   API: buildModel(key) -> { parts: [{ geo, w }], merged, edges }   （座標は y が上、正面が +z。最大の幅 ≒ 2.6 に正規化）
        sampleModel(model, n, seed) -> Float32Array(n * 3)          （表面と輪郭から n 点。粒子の形に使う）
   w = その部品に置く粒子の濃さ（1 が標準。面は薄く、輪郭や細い部品は濃く）。 */

import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { MeshSurfaceSampler } from "three/addons/math/MeshSurfaceSampler.js";

const PI = Math.PI;
const V = (x, y, z = 0) => new THREE.Vector3(x, y, z);

/* ── 形の部品 ── */
// 位置だけを残した、インデックスなしのジオメトリにそろえる（結合・サンプリング・輪郭の計算用）
function clean(g) {
  const x = g.index ? g.toNonIndexed() : g;
  if (x !== g) g.dispose();
  for (const k of Object.keys(x.attributes)) if (k !== "position") x.deleteAttribute(k);
  return x;
}
// 回転（x→y→z の順）してから移動
function T(g, { x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0, sx = 1, sy = 1, sz = 1 } = {}) {
  if (sx !== 1 || sy !== 1 || sz !== 1) g.scale(sx, sy, sz);
  if (rx) g.rotateX(rx);
  if (ry) g.rotateY(ry);
  if (rz) g.rotateZ(rz);
  if (x || y || z) g.translate(x, y, z);
  return g;
}
const box = (w, h, d) => new THREE.BoxGeometry(w, h, d);
const cyl = (rt, rb, h, seg = 16, open = false) => new THREE.CylinderGeometry(rt, rb, h, seg, 1, open);
const sphere = (r, ws = 12, hs = 8) => new THREE.SphereGeometry(r, ws, hs);
const torus = (R, r, rs = 6, ts = 48, arc = PI * 2) => new THREE.TorusGeometry(R, r, rs, ts, arc);
const tube = (pts, r, segs = 32, rs = 6, closed = false) =>
  new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts, closed), segs, r, rs, closed);
const extrude = (shape, depth, bevel = 0, curveSegments = 12) => new THREE.ExtrudeGeometry(shape, {
  depth, curveSegments, bevelEnabled: bevel > 0, bevelThickness: bevel, bevelSize: bevel * 0.8, bevelSegments: 2,
});
// 2点を結ぶ細い棒
const _up = V(0, 1, 0);
function rod(a, b, r = 0.012, seg = 5) {
  const d = b.clone().sub(a), len = d.length();
  const g = cyl(r, r, len, seg, true);
  g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(_up, d.normalize()));
  const m = a.clone().add(b).multiplyScalar(0.5);
  g.translate(m.x, m.y, m.z);
  return g;
}
// 角の丸い長方形
function roundRect(w, h, r) {
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  return s;
}
// 曲線に沿った細長い帯（稲の葉）。face = 帯の面が向く方向
function ribbon(curve, widthAt, face, n = 40) {
  const pos = [];
  const P = [], Q = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n, p = curve.getPoint(t), w = widthAt(t) / 2;
    const side = curve.getTangent(t).cross(face).normalize();
    P.push(p.clone().addScaledVector(side, -w));
    Q.push(p.clone().addScaledVector(side, w));
  }
  for (let i = 0; i < n; i++) {
    const a = P[i], b = Q[i], c = P[i + 1], d = Q[i + 1];
    pos.push(a.x, a.y, a.z, b.x, b.y, b.z, c.x, c.y, c.z, b.x, b.y, b.z, d.x, d.y, d.z, c.x, c.y, c.z);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  return g;
}
// 頂点を関数で動かす（反り・ふくらみ）
function warp(g, f) {
  const p = g.attributes.position, v = V(0, 0, 0);
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    f(v);
    p.setXYZ(i, v.x, v.y, v.z);
  }
  p.needsUpdate = true;
  return g;
}
// 乱数・なめらかなノイズ（地球儀の陸地用）
function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}
function hash3(x, y, z) {
  const s = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453;
  return s - Math.floor(s);
}
function vnoise(x, y, z) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const xf = x - xi, yf = y - yi, zf = z - zi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf), w = zf * zf * (3 - 2 * zf);
  const l = (a, b, t) => a + (b - a) * t;
  const c = (i, j, k) => hash3(xi + i, yi + j, zi + k);
  return l(l(l(c(0, 0, 0), c(1, 0, 0), u), l(c(0, 1, 0), c(1, 1, 0), u), v),
    l(l(c(0, 0, 1), c(1, 0, 1), u), l(c(0, 1, 1), c(1, 1, 1), u), v), w);
}

/* ── 物体ごとの作り方（add(ジオメトリ, 濃さ)） ── */
const BUILD = {};

// 国会議事堂：中央の塔と階段状のピラミッド屋根、左右に低い翼棟
BUILD.diet = (add) => {
  add(T(box(3.1, 0.1, 0.9), { y: 0.05 }), 0.5);
  for (const s of [-1, 1]) {
    add(T(box(1.05, 0.48, 0.62), { x: s * 0.82, y: 0.34 }), 0.55);
    add(T(box(1.12, 0.04, 0.66), { x: s * 0.82, y: 0.6 }), 1);
    add(T(box(0.3, 0.58, 0.7), { x: s * 1.42, y: 0.39 }), 0.6);
    for (let k = 0; k < 7; k++) add(T(box(0.025, 0.36, 0.02), { x: s * (0.38 + k * 0.13), y: 0.33, z: 0.32 }), 1.6);
  }
  add(T(box(0.66, 0.74, 0.72), { y: 0.47 }), 0.55);
  for (let k = 0; k < 6; k++) add(T(cyl(0.022, 0.022, 0.5, 8), { x: -0.25 + k * 0.1, y: 0.36, z: 0.42 }), 1.8);
  add(T(box(0.7, 0.07, 0.18), { y: 0.645, z: 0.4 }), 1.2);
  for (let k = 0; k < 3; k++) add(T(box(0.74 - k * 0.04, 0.035, 0.12), { y: 0.12 + k * 0.035, z: 0.5 - k * 0.04 }), 0.8);
  add(T(box(0.38, 0.52, 0.38), { y: 1.1 }), 0.9);
  for (const s of [-1, 1]) for (const t of [-1, 1]) add(T(cyl(0.02, 0.02, 0.5, 6), { x: s * 0.2, y: 1.1, z: t * 0.2 }), 1.6);
  for (let k = 0; k < 7; k++) {
    const w = 0.46 - k * 0.06;
    add(T(box(w, 0.06, w), { y: 1.39 + k * 0.06 }), 1.3);
  }
  add(T(cyl(0.012, 0.03, 0.22, 6), { y: 1.9 }), 2);
};

// 首相官邸：ガラス張りの低層棟と、大きく張り出した水平の庇（2層）
BUILD.kantei = (add) => {
  add(T(box(3.0, 0.05, 1.7), { y: 0.025 }), 0.35);
  const glass = (w, h, d, y) => {
    add(T(box(w, h, d), { y }), 0.25);
    for (let x = -w / 2 + 0.06; x <= w / 2 - 0.05; x += 0.11) add(T(box(0.012, h, 0.012), { x, y, z: d / 2 + 0.004 }), 1.8);
    for (let z = -d / 2 + 0.08; z <= d / 2 - 0.05; z += 0.14) {
      add(T(box(0.012, h, 0.012), { x: w / 2 + 0.004, y, z }), 1.2);
      add(T(box(0.012, h, 0.012), { x: -w / 2 - 0.004, y, z }), 1.2);
    }
  };
  glass(2.0, 0.44, 1.0, 0.27);
  add(T(box(2.9, 0.04, 1.55), { y: 0.51 }), 1);
  glass(1.6, 0.38, 0.8, 0.72);
  add(T(box(2.6, 0.05, 1.35), { y: 0.935 }), 1);
  for (const s of [-1, 1]) for (const t of [-1, 1]) {
    add(T(cyl(0.012, 0.012, 0.46, 6), { x: s * 1.36, y: 0.28, z: t * 0.7 }), 2);
    add(T(cyl(0.012, 0.012, 0.4, 6), { x: s * 1.2, y: 0.71, z: t * 0.6 }), 2);
  }
  // 前庭の低い植え込み（竹の庭の名残）
  for (let k = 0; k < 9; k++) add(T(cyl(0.008, 0.008, 0.22, 4), { x: -0.4 + k * 0.1, y: 0.16, z: 0.72 }), 1.4);
};

// 羅針盤：円い盤、目盛り、南北の針、上の吊り輪
BUILD.compass = (add) => {
  add(T(cyl(1.0, 1.0, 0.12, 48), { rx: PI / 2 }), 0.3);
  add(T(torus(1.0, 0.06, 8, 64), { z: 0.06 }), 1.3);
  add(T(torus(0.84, 0.012, 4, 64), { z: 0.075 }), 1.6);
  for (let k = 0; k < 32; k++) {
    const len = k % 8 === 0 ? 0.2 : k % 4 === 0 ? 0.12 : 0.06;
    const a = (k / 32) * PI * 2, r = 0.84 - len / 2 - 0.02;
    add(T(box(k % 8 === 0 ? 0.04 : 0.018, len, 0.02), { rz: a - PI / 2, x: Math.cos(a) * r, y: Math.sin(a) * r, z: 0.08 }), 2);
  }
  const tri = (pts) => { const s = new THREE.Shape(); s.moveTo(pts[0], pts[1]); for (let i = 2; i < pts.length; i += 2) s.lineTo(pts[i], pts[i + 1]); return s; };
  add(T(extrude(tri([0, 0.68, 0.12, 0, -0.12, 0]), 0.05), { z: 0.1, rz: 0.35 }), 2.6);
  add(T(extrude(tri([0, -0.68, -0.12, 0, 0.12, 0]), 0.05), { z: 0.1, rz: 0.35 }), 1.1);
  add(T(cyl(0.06, 0.06, 0.08, 16), { rx: PI / 2, z: 0.17 }), 1.5);
  add(T(box(0.12, 0.14, 0.1), { y: 1.06 }), 1);
  add(T(torus(0.13, 0.03, 6, 24), { y: 1.25 }), 1.6);
};

// スマートフォン：角の丸い板、画面に格子状のアイコン
BUILD.phone = (add) => {
  const body = extrude(roundRect(1.22, 2.36, 0.17), 0.1, 0.03);
  add(T(body, { z: -0.05 }), 0.35);
  const sw = 1.06, sh = 2.04;
  const frame = [V(-sw / 2, -sh / 2), V(sw / 2, -sh / 2), V(sw / 2, sh / 2), V(-sw / 2, sh / 2)];
  for (let i = 0; i < 4; i++) add(rod(frame[i].clone().setZ(0.09), frame[(i + 1) % 4].clone().setZ(0.09), 0.008, 4), 1.4);
  const tile = 0.19, gap = 0.255;
  for (let r = 0; r < 6; r++) for (let c = 0; c < 4; c++) {
    if (r === 5) continue;
    add(T(extrude(roundRect(tile, tile, 0.05), 0.025), { x: (c - 1.5) * gap, y: 0.72 - r * gap * 1.08, z: 0.07 }), 2.2);
  }
  for (let c = 0; c < 4; c++) add(T(extrude(roundRect(tile, tile, 0.05), 0.025), { x: (c - 1.5) * gap, y: -0.8, z: 0.07 }), 2.2);
  add(T(box(0.88, 0.006, 0.01), { y: -0.62, z: 0.09 }), 1.2);
  add(T(extrude(roundRect(0.3, 0.07, 0.035), 0.02), { y: 0.96, z: 0.07 }), 2);
  add(T(box(0.34, 0.022, 0.02), { y: -0.97, z: 0.09 }), 2);
  add(T(box(0.03, 0.26, 0.05), { x: 0.64, y: 0.55 }), 1.5);
  add(T(box(0.03, 0.14, 0.05), { x: -0.64, y: 0.62 }), 1.5);
};

// 電波塔：反りのある4本脚の鉄塔、格子の筋かい、展望台とアンテナ
BUILD.tower = (add) => {
  const H = 1.95;
  const half = (y) => 0.07 + 0.62 * Math.pow(1 - y / H, 2.3);
  const C = [[-1, -1], [1, -1], [1, 1], [-1, 1]];
  for (const [sx, sz] of C) {
    const pts = [];
    for (let k = 0; k <= 10; k++) { const y = (k / 10) * H; pts.push(V(sx * half(y), y, sz * half(y))); }
    add(tube(pts, 0.024, 40, 5), 1.4);
  }
  const levels = [0, 0.22, 0.46, 0.72, 0.98, 1.24, 1.5, 1.74, H];
  for (let i = 0; i < levels.length; i++) {
    const y = levels[i], h = half(y);
    const P = C.map(([sx, sz]) => V(sx * h, y, sz * h));
    for (let k = 0; k < 4; k++) add(rod(P[k], P[(k + 1) % 4], 0.01), 1.2);
    if (i === 0) continue;
    const y0 = levels[i - 1], h0 = half(y0);
    const Q = C.map(([sx, sz]) => V(sx * h0, y0, sz * h0));
    for (let k = 0; k < 4; k++) {
      add(rod(Q[k], P[(k + 1) % 4], 0.007, 4), 1.1);
      add(rod(Q[(k + 1) % 4], P[k], 0.007, 4), 1.1);
    }
  }
  const deck = (y, w, h) => { add(T(box(w, h, w), { y }), 0.8); add(T(box(w + 0.08, 0.02, w + 0.08), { y: y + h / 2 }), 1.2); };
  deck(0.98, half(0.98) * 2 + 0.16, 0.12);
  deck(1.6, half(1.6) * 2 + 0.12, 0.08);
  add(T(cyl(0.012, 0.03, 0.62, 6), { y: H + 0.31 }), 2.2);
  for (const y of [H + 0.12, H + 0.32]) add(T(cyl(0.045, 0.045, 0.05, 8), { y }), 1.6);
  // 足元のアーチ
  for (const [sx, sz] of [[0, 1], [0, -1], [1, 0], [-1, 0]]) {
    const pts = [];
    for (let k = 0; k <= 8; k++) {
      const t = k / 8 * 2 - 1, y = 0.2 * (1 - t * t), h = half(y);
      pts.push(sx ? V(sx * h, y, t * h) : V(t * h, y, sz * h));
    }
    add(tube(pts, 0.012, 16, 4), 1.2);
  }
};

// 天秤：台座・柱・水平の棹、鎖で下がる2枚の皿
BUILD.scales = (add) => {
  add(new THREE.LatheGeometry([V(0.0, 0), V(0.62, 0), V(0.62, 0.06), V(0.4, 0.11), V(0.14, 0.18), V(0.1, 0.24)], 40), 0.7);
  add(T(cyl(0.045, 0.065, 1.66, 16), { y: 1.07 }), 1.2);
  add(T(box(2.36, 0.05, 0.06), { y: 1.86 }), 1.6);
  add(T(sphere(0.075, 16, 10), { y: 1.98 }), 1.4);
  add(T(torus(0.09, 0.018, 6, 24), { y: 1.86, z: 0.035 }), 1.6);
  for (const s of [-1, 1]) {
    add(T(sphere(0.04, 10, 8), { x: s * 1.18, y: 1.86 }), 1.4);
    const top = V(s * 1.12, 1.83, 0);
    for (let k = 0; k < 3; k++) {
      const a = (k / 3) * PI * 2 + 0.5;
      add(rod(top, V(s * 1.12 + Math.cos(a) * 0.38, 0.98, Math.sin(a) * 0.38), 0.008, 4), 2);
    }
    add(T(new THREE.LatheGeometry([V(0, 0), V(0.22, 0.015), V(0.36, 0.06), V(0.42, 0.11), V(0.44, 0.12)], 36), { x: s * 1.12, y: 0.87 }), 1);
  }
};

// 地球儀：経線・緯線と陸地、傾いた軸、半円の支え、台座
BUILD.globe = (add) => {
  const tilt = -0.41, R = 0.95, cy = 1.25;
  const onAxis = (g) => T(g, { rz: tilt, y: cy });
  add(onAxis(sphere(R, 32, 20)), 0.08);
  for (let k = 0; k < 6; k++) add(onAxis(T(torus(R, 0.01, 4, 72), { ry: (k * PI) / 6 })), 1.3);
  for (const lat of [-60, -30, 0, 30, 60]) {
    const a = (lat * PI) / 180;
    add(onAxis(T(torus(R * Math.cos(a), lat ? 0.01 : 0.016, 4, 72), { rx: PI / 2, y: R * Math.sin(a) })), lat ? 1.3 : 2);
  }
  // 陸地：ノイズで選んだ球面の三角形だけを残す
  const land = sphere(R * 1.004, 72, 44).toNonIndexed();
  const p = land.attributes.position, keep = [], a = V(0, 0, 0), c = V(0, 0, 0);
  for (let t = 0; t < p.count; t += 3) {
    c.set(0, 0, 0);
    for (let k = 0; k < 3; k++) c.add(a.fromBufferAttribute(p, t + k));
    c.normalize();
    const n = vnoise(c.x * 1.8 + 3.1, c.y * 1.8 + 7.7, c.z * 1.8 + 1.3) * 0.65 + vnoise(c.x * 4 + 9, c.y * 4, c.z * 4 + 2) * 0.35;
    if (n > 0.56 && Math.abs(c.y) < 0.9) for (let k = 0; k < 3; k++) { a.fromBufferAttribute(p, t + k); keep.push(a.x, a.y, a.z); }
  }
  land.dispose();
  const lg = new THREE.BufferGeometry();
  lg.setAttribute("position", new THREE.Float32BufferAttribute(keep, 3));
  add(onAxis(lg), 0.9);
  add(onAxis(rod(V(0, -1.12, 0), V(0, 1.12, 0), 0.016, 6)), 1.6);
  add(onAxis(T(torus(1.08, 0.03, 6, 48, PI), { rz: PI / 2 })), 1.4);
  add(T(cyl(0.04, 0.07, 0.24, 12), { y: 0.12 + 0.02 }), 1.2);
  add(new THREE.LatheGeometry([V(0, 0), V(0.5, 0), V(0.5, 0.04), V(0.3, 0.09), V(0.08, 0.12)], 36), 0.8);
};

// 積み重ねた硬貨：高さの違う3つの山と、手前に立てた穴あきの硬貨
BUILD.coins = (add) => {
  const r = rng(11);
  const coin = (x, y, z, rad = 0.42, h = 0.1) => {
    add(T(cyl(rad, rad, h, 40, true), { x, y, z }), 0.45);
    add(T(cyl(rad, rad, 0.004, 40), { x, y: y + h / 2, z }), 0.3);
    add(T(torus(rad * 0.82, 0.008, 3, 40), { rx: PI / 2, x, y: y + h / 2 + 0.003, z }), 1.4);
  };
  for (const [x, z, n] of [[-0.95, 0.05, 5], [0.0, -0.2, 9], [0.95, 0.0, 7]]) {
    for (let k = 0; k < n; k++) coin(x + (r() - 0.5) * 0.07, 0.05 + k * 0.125, z + (r() - 0.5) * 0.07);
  }
  // 手前に立てた穴あきの硬貨（正面を向けて穴が見えるように）
  const stand = (g) => T(g, { ry: -0.12, x: 0.42, y: 0.42, z: 0.75 });
  const s = new THREE.Shape();
  s.absarc(0, 0, 0.42, 0, PI * 2, false);
  const hole = new THREE.Path();
  hole.absarc(0, 0, 0.11, 0, PI * 2, true);
  s.holes.push(hole);
  add(stand(extrude(s, 0.07, 0.015, 40)), 0.7);
  add(stand(torus(0.35, 0.009, 3, 40).translate(0, 0, 0.09)), 1.6);
  add(stand(torus(0.17, 0.009, 3, 24).translate(0, 0, 0.09)), 1.6);
};

// 開いた本：ふくらんだページの重なりと行、下の表紙
BUILD.book = (add) => {
  const W = 1.2, D = 1.6;
  const lift = (a) => 0.3 * Math.sqrt(a) * (1 - 0.55 * a);
  for (const s of [-1, 1]) {
    for (let L = 0; L < 4; L++) {
      const g = new THREE.PlaneGeometry(W, D, 24, 1);
      g.rotateX(-PI / 2);
      warp(g, (v) => { const a = Math.min(1, Math.max(0, (v.x + W / 2) / W)); v.x = s * a * W; v.y = lift(a) - L * 0.035 * a; });
      add(g, L ? 0.15 : 0.4);
    }
    for (let k = 0; k < 11; k++) {
      if (k === 5) continue; // 段落の切れ目
      const z = -0.66 + k * 0.132;
      const a0 = 0.12, a1 = k % 5 === 4 ? 0.55 : 0.88;
      const pts = [];
      for (let j = 0; j <= 8; j++) { const a = a0 + ((a1 - a0) * j) / 8; pts.push(V(s * a * W, lift(a) + 0.012, z)); }
      add(tube(pts, 0.007, 16, 3), 1.5);
    }
    add(T(box(W + 0.06, 0.03, D + 0.1), { x: s * (W / 2 + 0.03), y: -0.03 }), 0.35);
  }
  add(rod(V(0, 0, -D / 2), V(0, 0, D / 2), 0.012, 5), 1.6);
};

// 手のひらに乗ったハート（十字は使わない）
BUILD.heart = (add) => {
  const s = new THREE.Shape();
  s.moveTo(0, -0.9);
  s.bezierCurveTo(0.18, -0.68, 1.0, -0.28, 1.0, 0.25);
  s.bezierCurveTo(1.0, 0.78, 0.42, 0.98, 0, 0.56);
  s.bezierCurveTo(-0.42, 0.98, -1.0, 0.78, -1.0, 0.25);
  s.bezierCurveTo(-1.0, -0.28, -0.18, -0.68, 0, -0.9);
  const h = extrude(s, 0.28, 0.16, 24);
  h.translate(0, 0, -0.14);
  add(T(h, { sx: 0.6, sy: 0.6, sz: 0.6, rz: -0.08, y: 0.55 }), 1.1);
  // 上向きに開いた手のひら（ハートの下）。指は右へ伸びて先が少し丸まり、親指は手前に立つ
  add(T(sphere(1, 24, 12), { sx: 0.6, sy: 0.13, sz: 0.46, x: -0.12, y: -0.34 }), 0.55);
  const finger = (z, len, curl) => add(tube([V(0.36, -0.32, z), V(0.36 + len * 0.55, -0.3, z),
    V(0.36 + len * 0.88, -0.2 + curl * 0.05, z), V(0.36 + len, -0.05 + curl * 0.1, z)], 0.062, 20, 8), 0.9);
  finger(-0.3, 0.5, 1); finger(-0.1, 0.62, 1.2); finger(0.1, 0.6, 1.1); finger(0.29, 0.46, 0.9);
  add(tube([V(-0.2, -0.3, 0.38), V(0.02, -0.2, 0.52), V(0.2, -0.04, 0.56), V(0.28, 0.06, 0.5)], 0.068, 20, 8), 0.9);
  add(tube([V(-0.68, -0.38, 0), V(-0.95, -0.44, 0), V(-1.15, -0.5, 0)], 0.17, 12, 12), 0.25);
};

// 稲穂：垂れた穂に粒が並ぶ3本の茎と葉
BUILD.rice = (add) => {
  const r = rng(5);
  const stalk = (x0, z0, lean, droop) => {
    const curve = new THREE.CatmullRomCurve3([V(x0, -1.25, z0), V(x0 + lean * 0.1, -0.3, z0), V(x0 + lean * 0.35, 0.5, z0),
      V(x0 + lean * 0.75, 0.95, z0), V(x0 + lean * 1.1, 0.85 - droop * 0.2, z0), V(x0 + lean * 1.3, 0.5 - droop * 0.4, z0 + 0.05)]);
    add(new THREE.TubeGeometry(curve, 60, 0.018, 5, false), 1.3);
    // 粒は左右交互に、短い枝の先に1つずつ（一粒ずつ見分けられる間隔で）
    for (let k = 0; k < 15; k++) {
      const t = 0.6 + (k / 15) * 0.4;
      const p = curve.getPoint(t), tg = curve.getTangent(t);
      const side = V(-tg.y, tg.x, 0).normalize();
      const sgn = k % 2 ? 1 : -1;
      const dir = tg.clone().multiplyScalar(0.75).addScaledVector(side, sgn * 0.85).add(V(0, 0, (r() - 0.5) * 0.6)).normalize();
      const c = p.clone().addScaledVector(dir, 0.13);
      add(rod(p, c, 0.006, 3), 1.2);
      const g = sphere(1, 10, 8);
      g.scale(0.045, 0.1, 0.045);
      g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(_up, dir));
      g.translate(c.x, c.y, c.z);
      add(g, 1.2);
    }
    const leaf = new THREE.CatmullRomCurve3([V(x0, -0.95, z0), V(x0 - lean * 0.25, -0.4, z0 + 0.05),
      V(x0 - lean * 0.6, 0.0, z0 + 0.08), V(x0 - lean * 0.98, 0.05 - droop * 0.1, z0 + 0.1)]);
    add(ribbon(leaf, (t) => 0.1 * Math.sin(PI * Math.min(1, t * 0.92 + 0.08)), V(0, 0, 1)), 0.9);
  };
  stalk(-0.35, 0.0, 1, 1);
  stalk(0.05, -0.15, 0.85, 1.3);
  stalk(0.42, 0.12, 0.7, 0.8);
};

// 噛み合う歯車（大小2枚）
function gearShape(R, n, toothH, holeR, windows) {
  const s = new THREE.Shape(), rr = R - toothH, step = (PI * 2) / n;
  for (let i = 0; i < n; i++) {
    const a = i * step;
    [[rr, a - step * 0.3], [R, a - step * 0.16], [R, a + step * 0.16], [rr, a + step * 0.3]].forEach(([r, t], k) => {
      const x = Math.cos(t) * r, y = Math.sin(t) * r;
      if (i === 0 && k === 0) s.moveTo(x, y); else s.lineTo(x, y);
    });
  }
  s.closePath();
  const h = new THREE.Path();
  h.absarc(0, 0, holeR, 0, PI * 2, true);
  s.holes.push(h);
  for (let k = 0; k < windows; k++) {
    const a = (k / windows) * PI * 2 + step / 2, w = new THREE.Path();
    w.absarc(Math.cos(a) * R * 0.52, Math.sin(a) * R * 0.52, R * 0.16, 0, PI * 2, true);
    s.holes.push(w);
  }
  return s;
}
BUILD.gear = (add) => {
  const R1 = 0.95, R2 = 0.6, n1 = 18, n2 = 11, th = 0.15, ang = -0.62;
  const d = R1 + R2 - th * 0.85;
  const gear = (R, n, hole, win, rot, x, y) => {
    const g = extrude(gearShape(R, n, th, hole, win), 0.22, 0.02, 10);
    g.translate(0, 0, -0.11);
    add(T(g, { rz: rot, x, y }), 0.75);
    add(T(torus(hole + 0.08, 0.03, 6, 32), { x, y, z: 0.14 }), 1.6);
  };
  const x1 = -0.5, y1 = 0.25;
  gear(R1, n1, 0.17, 6, ang - (0.5 * PI * 2) / n1, x1, y1); // 相手に向く側は歯と歯のすき間
  gear(R2, n2, 0.12, 4, ang + PI, x1 + Math.cos(ang) * d, y1 + Math.sin(ang) * d); // こちらは歯の先
};

// アーチ橋：2本のアーチ、吊り材、橋桁と橋台
BUILD.bridge = (add) => {
  const half = 1.3, H = 0.95;
  const archY = (x) => H * (1 - (x / half) ** 2);
  add(T(box(3.3, 0.07, 0.56), {}), 0.6);
  for (const z of [-0.24, 0.24]) {
    const pts = [];
    for (let k = 0; k <= 24; k++) { const x = -half + (2 * half * k) / 24; pts.push(V(x, archY(x), z)); }
    add(tube(pts, 0.035, 48, 6), 1.5);
    for (let x = -1.1; x <= 1.11; x += 0.2) add(rod(V(x, archY(x), z), V(x, 0.035, z), 0.009, 4), 1.6);
    add(T(box(3.3, 0.05, 0.02), { y: 0.1, z: z * 1.12 }), 1.1);
  }
  for (let x = -0.7; x <= 0.71; x += 0.35) add(rod(V(x, archY(x), -0.24), V(x, archY(x), 0.24), 0.012, 4), 1.2);
  for (const s of [-1, 1]) add(T(box(0.26, 0.8, 0.66), { x: s * 1.42, y: -0.4 }), 0.55);
  for (let k = 0; k < 5; k++) add(T(box(0.5 + (k % 2) * 0.3, 0.008, 0.008), { x: -1 + k * 0.5, y: -0.72, z: 0.3 - (k % 3) * 0.2 }), 1);
};

// 葉：反りのある葉身と、主脈・側脈・葉柄
BUILD.leaf = (add) => {
  const bend = (v) => { v.z += -0.16 * v.x * v.x + 0.1 * Math.sin(v.y * 1.3); };
  const s = new THREE.Shape();
  s.moveTo(0, -1.1);
  s.bezierCurveTo(0.78, -0.72, 0.82, 0.42, 0, 1.25);
  s.bezierCurveTo(-0.82, 0.42, -0.78, -0.72, 0, -1.1);
  const g = extrude(s, 0.02, 0, 32);
  g.translate(0, 0, -0.01);
  add(warp(g, bend), 0.4);
  const B = (x, y) => { const v = V(x, y, 0.025); bend(v); return v; };
  const mid = [];
  for (let k = 0; k <= 12; k++) mid.push(B(0, -1.1 + (k * 2.33) / 12));
  add(tube(mid, 0.02, 40, 5), 2);
  const width = (y) => 0.62 * Math.pow(Math.max(0, Math.sin((PI * (y + 1.1)) / 2.35)), 0.8);
  for (let k = 1; k <= 7; k++) {
    const y0 = -0.95 + k * 0.25;
    for (const sgn of [-1, 1]) {
      const y1 = y0 + 0.36, w = width(y1) * 0.86;
      add(tube([B(0, y0), B(sgn * w * 0.45, y0 + 0.19), B(sgn * w, y1)], 0.009, 14, 3), 1.6);
    }
  }
  add(tube([B(0, -1.1), B(0.02, -1.35), B(0.08, -1.6)], 0.028, 12, 5), 1.6);
};

// 盾：ふくらんだ盾の板、内側の縁取り、山形の帯（武器は出さない）
BUILD.shield = (add) => {
  const bulge = (v) => { v.z += 0.22 * (1 - Math.min(1, (v.x / 0.95) ** 2)) * (1 - 0.3 * Math.max(0, -v.y)); };
  const outline = (k) => {
    const s = new THREE.Shape();
    s.moveTo(-0.9 * k, 1.0 * k);
    s.quadraticCurveTo(0, 1.12 * k, 0.9 * k, 1.0 * k);
    s.lineTo(0.9 * k, 0.3 * k);
    s.bezierCurveTo(0.9 * k, -0.5 * k, 0.42 * k, -0.95 * k, 0, -1.25 * k);
    s.bezierCurveTo(-0.42 * k, -0.95 * k, -0.9 * k, -0.5 * k, -0.9 * k, 0.3 * k);
    s.closePath();
    return s;
  };
  const body = extrude(outline(1), 0.08, 0.04, 24);
  body.translate(0, 0, -0.04);
  add(warp(body, bulge), 0.45);
  const rim = outline(0.86).getSpacedPoints(90).slice(0, -1).map((p) => { const v = V(p.x, p.y, 0.09); bulge(v); return v; });
  add(tube(rim, 0.03, 180, 5, true), 2);
  const c = new THREE.Shape();
  c.moveTo(-0.6, -0.14); c.lineTo(0, 0.4); c.lineTo(0.6, -0.14); c.lineTo(0.6, -0.4); c.lineTo(0, 0.12); c.lineTo(-0.6, -0.4); c.closePath();
  const cg = extrude(c, 0.04, 0, 4);
  cg.translate(0, 0, 0.07);
  add(warp(cg, bulge), 1.8);
  add(warp(T(sphere(0.12, 16, 10), { sz: 0.5, y: -0.66, z: 0.09 }), bulge), 1.6);
};

/* ── 組み立て・正規化 ── */
// 見やすい向き（カメラは少し上から見る。建物は屋根が見えるように、本は手前に起こす）
const POSE = {
  diet: { rx: 0.14, ry: -0.18 }, kantei: { rx: 0.34, ry: -0.22 }, compass: { rx: -0.12 }, phone: { rz: -0.1, ry: -0.2 },
  tower: { ry: 0.4 }, scales: { rx: 0.08 }, globe: {}, coins: { rx: 0.22, ry: -0.1 }, book: { rx: 0.95 },
  heart: { rx: 0.22 }, rice: { ry: -0.2 }, gear: { ry: -0.15 }, bridge: { rx: 0.14, ry: -0.32 }, leaf: { rz: -0.5 }, shield: {},
};
export const MODEL_KEYS = Object.keys(BUILD);
const cache = new Map();

export function buildModel(key) {
  if (!BUILD[key]) key = "compass";
  if (cache.has(key)) return cache.get(key);
  const parts = [];
  BUILD[key]((g, w = 1) => parts.push({ geo: clean(g), w }));
  const bb = new THREE.Box3();
  for (const p of parts) {
    T(p.geo, POSE[key] || {});
    p.geo.computeBoundingBox();
    bb.union(p.geo.boundingBox);
  }
  const c = bb.getCenter(V(0, 0, 0)), size = bb.getSize(V(0, 0, 0));
  const s = 2.6 / Math.max(size.x, size.y, size.z * 0.8);
  for (const p of parts) {
    p.geo.translate(-c.x, -c.y, -c.z);
    p.geo.scale(s, s, s);
    // 輪郭：面の角度が 28° 以上の辺と、面が1枚しかない辺（葉の縁・陸地の海岸線など）
    const e = new THREE.EdgesGeometry(p.geo, 28);
    p.edges = e.attributes.position.array;
    e.dispose();
  }
  const merged = mergeGeometries(parts.map((p) => p.geo), false);
  merged.computeVertexNormals();
  merged.computeBoundingSphere();
  const edges = new THREE.BufferGeometry();
  const all = new Float32Array(parts.reduce((n, p) => n + p.edges.length, 0));
  let o = 0;
  for (const p of parts) { all.set(p.edges, o); o += p.edges.length; }
  edges.setAttribute("position", new THREE.BufferAttribute(all, 3));
  const model = { key, parts, merged, edges, radius: merged.boundingSphere.radius };
  cache.set(key, model);
  return model;
}

function triArea(pos) {
  const a = V(0, 0, 0), b = V(0, 0, 0), c = V(0, 0, 0);
  let s = 0;
  for (let i = 0; i < pos.count; i += 3) {
    a.fromBufferAttribute(pos, i); b.fromBufferAttribute(pos, i + 1); c.fromBufferAttribute(pos, i + 2);
    s += b.sub(a).cross(c.sub(a)).length() * 0.5;
  }
  return s;
}
// 重みに比例して n 個を配る（端数は大きい順）
function allocate(weights, n) {
  const sum = weights.reduce((a, b) => a + b, 0) || 1;
  const raw = weights.map((w) => (w / sum) * n), out = raw.map(Math.floor);
  let left = n - out.reduce((a, b) => a + b, 0);
  raw.map((r, i) => [r - Math.floor(r), i]).sort((a, b) => b[0] - a[0]).forEach(([, i]) => { if (left > 0) { out[i]++; left--; } });
  return out;
}

// 表面（面積×濃さ）から 7 割、輪郭（長さ×濃さ）から 3 割の点を取り、順番をばらばらにする
export function sampleModel(model, n, seed = 1) {
  const rnd = rng(seed * 7919 + 17);
  const out = new Float32Array(n * 3);
  const nEdge = Math.round(n * 0.3);
  const v = V(0, 0, 0);
  let o = 0;
  const surf = allocate(model.parts.map((p) => triArea(p.geo.attributes.position) * p.w), n - nEdge);
  model.parts.forEach((p, i) => {
    if (!surf[i]) return;
    const smp = new MeshSurfaceSampler(new THREE.Mesh(p.geo)).setRandomGenerator(rnd).build();
    for (let k = 0; k < surf[i]; k++) { smp.sample(v); out[o++] = v.x; out[o++] = v.y; out[o++] = v.z; }
  });
  const segs = [], cum = [];
  let total = 0;
  for (const p of model.parts) {
    const e = p.edges;
    for (let i = 0; i < e.length; i += 6) {
      const len = Math.hypot(e[i + 3] - e[i], e[i + 4] - e[i + 1], e[i + 5] - e[i + 2]) * p.w;
      if (len <= 0) continue;
      total += len;
      segs.push(e, i);
      cum.push(total);
    }
  }
  for (let k = 0; k < nEdge; k++) {
    if (!cum.length) { out[o++] = 0; out[o++] = 0; out[o++] = 0; continue; }
    const x = rnd() * total;
    let lo = 0, hi = cum.length - 1;
    while (lo < hi) { const m = (lo + hi) >> 1; if (cum[m] < x) lo = m + 1; else hi = m; }
    const e = segs[lo * 2], i = segs[lo * 2 + 1], t = rnd();
    out[o++] = e[i] + (e[i + 3] - e[i]) * t;
    out[o++] = e[i + 1] + (e[i + 4] - e[i + 1]) * t;
    out[o++] = e[i + 2] + (e[i + 5] - e[i + 2]) * t;
  }
  for (let i = n - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    for (let a = 0; a < 3; a++) { const t = out[i * 3 + a]; out[i * 3 + a] = out[j * 3 + a]; out[j * 3 + a] = t; }
  }
  return out;
}
