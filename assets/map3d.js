/* 有権者 — 地方ページ（local.html）の 3D 日本地図（夜の海に浮かぶ、少し厚みのある47都道府県）
   local.js から dynamic import される。three の読み込みに失敗したら local.js が SVG の地図に切り替える。
   API: createMap({ canvas, overlay, dec, prefs, isMobile, reduced, onPick }) -> { select(id, instant), setPaused(b), dispose() }
     dec = prefmap.js の decodeMap の結果、prefs = [{ id, name, count }]（count = 記事の数）
     overlay = 地図の上に重ねる要素（名前のラベルと記事数のバッジをここに置く）
     onPick(id) = 都道府県をクリック・タップしたとき
   形は全部まとめて1つのジオメトリ（描画1回）。持ち上がる・光るなどの県ごとの状態は uniform の配列で渡す（毎フレームの new はしない）。 */

import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { hitTest } from "./prefmap.js";

const H = 0.14;          // 県の厚み（1 = 緯度1度）
const LIFT = 0.32;       // ホバー・選んだ県が持ち上がる高さ
const FOV = 34;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerpK = (dt, speed) => 1 - Math.exp(-dt * speed);

const LAND_VS = /* glsl */`
attribute float aPref;
uniform vec4 uState[47]; // x = 持ち上がり, y = 光り（ホバー・選択）, z = 記事あり, w = 暗く（ほかの県を選んでいる）
varying vec3 vW;
varying float vTop;
varying vec4 vS;
void main() {
  vec4 s = uState[int(aPref + 0.5)];
  vec3 p = position;
  p.y += s.x;
  vec4 wp = modelMatrix * vec4(p, 1.0);
  vW = wp.xyz;
  vTop = step(0.5, normal.y);
  vS = s;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;
const LAND_FS = /* glsl */`
uniform vec3 uBase, uHas, uHot, uSide;
uniform float uTime;
varying vec3 vW;
varying float vTop;
varying vec4 vS;
void main() {
  float has = vS.z, hot = vS.y, dim = vS.w;
  float sh = 0.5 + 0.5 * sin(vW.x * 1.3 + vW.z * 0.9 + uTime * 0.7);
  vec3 top = mix(uBase, uHas * (0.85 + 0.25 * sh), has);
  top = mix(top, uHot, hot * 0.62);
  float h = clamp((vW.y - vS.x) / ${H.toFixed(3)}, 0.0, 1.0); // 側面の上ほど明るい
  vec3 side = mix(uSide * 0.35, uSide * (0.8 + 0.6 * has), h) + uHot * hot * 0.3 * h;
  vec3 col = mix(side, top, vTop);
  col *= mix(1.0, 0.5, dim);
  gl_FragColor = vec4(col, 1.0);
}`;
const LINE_VS = /* glsl */`
attribute float aPref;
uniform vec4 uState[47];
varying vec4 vS;
void main() {
  vec4 s = uState[int(aPref + 0.5)];
  vec3 p = position;
  p.y += s.x;
  vS = s;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
}`;
const LINE_FS = /* glsl */`
uniform vec3 uLine, uHot;
varying vec4 vS;
void main() {
  vec3 col = uLine * (0.55 + 0.6 * vS.z) + uHot * vS.y * 1.4;
  gl_FragColor = vec4(col * mix(1.0, 0.45, vS.w), 1.0);
}`;
const SEA_VS = /* glsl */`
varying vec3 vW;
void main() { vec4 wp = modelMatrix * vec4(position, 1.0); vW = wp.xyz; gl_Position = projectionMatrix * viewMatrix * wp; }`;
const SEA_FS = /* glsl */`
uniform float uTime;
uniform vec3 uDeep, uGlow, uCenter;
varying vec3 vW;
void main() {
  vec2 p = vW.xz;
  float r = length(p - uCenter.xz);
  float w = sin(p.x * 2.1 + uTime * 0.5) * sin(p.y * 1.7 - uTime * 0.37) + sin((p.x + p.y) * 3.3 + uTime * 0.8) * 0.5;
  vec3 col = uDeep + uGlow * (exp(-r * 0.16) * 0.55 + smoothstep(0.9, 1.5, w) * 0.05 * exp(-r * 0.08));
  col *= 1.0 - smoothstep(10.0, 34.0, r);
  gl_FragColor = vec4(col, 1.0);
}`;
const DUST_VS = /* glsl */`
attribute float aSeed;
uniform float uTime, uPr, uTw;
varying float vA;
void main() {
  vec3 p = position;
  p.y += sin(uTime * 0.12 + aSeed * 6.28) * 0.15 * uTw;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  vA = (0.35 + 0.65 * (0.5 + 0.5 * sin(uTime * (0.6 + aSeed) + aSeed * 40.0) * uTw)) * (0.4 + 0.6 * fract(aSeed * 7.3));
  gl_PointSize = uPr * (1.2 + 2.6 * fract(aSeed * 13.1)) * (14.0 / -mv.z);
  gl_Position = projectionMatrix * mv;
}`;
const DUST_FS = /* glsl */`
uniform vec3 uColor;
varying float vA;
void main() {
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.0, d) * vA;
  gl_FragColor = vec4(uColor * a, a);
}`;

export function createMap({ canvas, overlay, dec, prefs, isMobile = false, reduced = false, onPick = () => {} }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  if (!renderer.getContext()) throw new Error("WebGL を使えません");
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.setClearColor(0x04080f, 1);

  const ids = prefs.map((p) => p.id);
  const index = Object.fromEntries(ids.map((id, i) => [id, i]));
  const N = ids.length;
  // 地図の中心（はめ込みの枠も入れた全体の中心）
  const B = dec.box;
  const CX = (B[0] + B[2]) / 2, CY = (B[1] + B[3]) / 2;
  const toW = (x, y, out) => out.set(x - CX, 0, -(y - CY)); // 地図の座標 → ワールド（北が奥）

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 200);

  /* ── 県ごとの状態（uniform の配列） ── */
  const uState = { value: Array.from({ length: 47 }, () => new THREE.Vector4()) };
  const cur = prefs.map((p) => ({ lift: 0, glow: 0, has: p.count > 0 ? 1 : 0, dim: 0 }));
  const uTime = { value: 0 };

  /* ── 陸（押し出した形を全部まとめる） ── */
  const geos = [], lineGeos = [];
  const _v = new THREE.Vector3();
  prefs.forEach((p, i) => {
    const d = dec.prefs[p.id];
    if (!d) return;
    const shapes = [];
    const segs = [];
    for (const poly of d.polys) {
      const pts = (r) => { const a = []; for (let k = 0; k < r.length; k += 2) a.push(new THREE.Vector2(r[k] - CX, r[k + 1] - CY)); return a; };
      const shape = new THREE.Shape(pts(poly[0]));
      for (let k = 1; k < poly.length; k++) shape.holes.push(new THREE.Path(pts(poly[k])));
      shapes.push(shape);
      for (const r of poly) {
        for (let k = 0, j = r.length - 2; k < r.length; j = k, k += 2) {
          segs.push(r[j] - CX, H + 0.003, -(r[j + 1] - CY), r[k] - CX, H + 0.003, -(r[k + 1] - CY));
        }
      }
    }
    const g = new THREE.ExtrudeGeometry(shapes, { depth: H, bevelEnabled: false, curveSegments: 1 });
    g.rotateX(-Math.PI / 2); // (x, y, 厚み) → (x, 厚み, -y)
    g.deleteAttribute("uv");
    g.setAttribute("aPref", new THREE.Float32BufferAttribute(new Float32Array(g.attributes.position.count).fill(i), 1));
    geos.push(g.index ? g.toNonIndexed() : g);
    const lg = new THREE.BufferGeometry();
    lg.setAttribute("position", new THREE.Float32BufferAttribute(segs, 3));
    lg.setAttribute("aPref", new THREE.Float32BufferAttribute(new Float32Array(segs.length / 3).fill(i), 1));
    lineGeos.push(lg);
  });
  const landGeo = mergeGeometries(geos, false);
  const lineGeo = mergeGeometries(lineGeos, false);
  geos.forEach((g) => g.dispose());
  lineGeos.forEach((g) => g.dispose());
  const C = (hex) => new THREE.Color(hex);
  const landMat = new THREE.ShaderMaterial({
    vertexShader: LAND_VS, fragmentShader: LAND_FS,
    uniforms: { uState, uTime, uBase: { value: C(0x14294a) }, uHas: { value: C(0x2a8fb0) }, uHot: { value: C(0xbfeaff) }, uSide: { value: C(0x1f5d86) } },
  });
  const land = new THREE.Mesh(landGeo, landMat);
  scene.add(land);
  const lineMat = new THREE.ShaderMaterial({
    vertexShader: LINE_VS, fragmentShader: LINE_FS,
    uniforms: { uState, uLine: { value: C(0x5f9fcc) }, uHot: { value: C(0xd6f2ff) } },
  });
  const lines = new THREE.LineSegments(lineGeo, lineMat);
  scene.add(lines);

  /* ── はめ込み（沖縄・奄美）の枠 ── */
  const ib = dec.inset.box;
  const frameGeo = new THREE.BufferGeometry().setFromPoints([
    toW(ib[0], ib[1], new THREE.Vector3()), toW(ib[2], ib[1], new THREE.Vector3()),
    toW(ib[2], ib[3], new THREE.Vector3()), toW(ib[0], ib[3], new THREE.Vector3()),
  ]);
  const frameMat = new THREE.LineBasicMaterial({ color: 0x3f6f96, transparent: true, opacity: 0.6 });
  const insetFrame = new THREE.LineLoop(frameGeo, frameMat);
  insetFrame.position.y = 0.005;
  scene.add(insetFrame);

  /* ── 夜の海 ── */
  const seaGeo = new THREE.PlaneGeometry(90, 90, 1, 1);
  seaGeo.rotateX(-Math.PI / 2);
  const seaMat = new THREE.ShaderMaterial({
    vertexShader: SEA_VS, fragmentShader: SEA_FS, depthWrite: false,
    uniforms: { uTime, uDeep: { value: C(0x03070e) }, uGlow: { value: C(0x0f2a48) }, uCenter: { value: new THREE.Vector3() } },
  });
  const sea = new THREE.Mesh(seaGeo, seaMat);
  sea.position.y = -0.01;
  sea.renderOrder = -1;
  scene.add(sea);

  /* ── 星くず（地図の上をただよう光の粒） ── */
  const DUST = isMobile ? 500 : 1100;
  const dustPos = new Float32Array(DUST * 3), dustSeed = new Float32Array(DUST);
  {
    let s = 12345;
    const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
    for (let i = 0; i < DUST; i++) {
      dustPos[i * 3] = (rnd() - 0.5) * 34;
      dustPos[i * 3 + 1] = 0.4 + Math.pow(rnd(), 1.6) * 9;
      dustPos[i * 3 + 2] = (rnd() - 0.5) * 30;
      dustSeed[i] = rnd();
    }
  }
  const dustGeo = new THREE.BufferGeometry();
  dustGeo.setAttribute("position", new THREE.BufferAttribute(dustPos, 3));
  dustGeo.setAttribute("aSeed", new THREE.BufferAttribute(dustSeed, 1));
  const uPr = { value: 1 };
  const dustMat = new THREE.ShaderMaterial({
    vertexShader: DUST_VS, fragmentShader: DUST_FS, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    uniforms: { uTime, uPr, uTw: { value: reduced ? 0 : 1 }, uColor: { value: C(0xb8d8f6) } },
  });
  const dust = new THREE.Points(dustGeo, dustMat);
  scene.add(dust);

  /* ── 光のにじみ ── */
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), isMobile ? 0.5 : 0.6, 0.45, 0.32);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  /* ── ラベル（名前）とバッジ（記事の数）：HTML を地図の上に重ねる ── */
  const label = document.createElement("div");
  label.className = "lm-label";
  label.hidden = true;
  label.setAttribute("aria-hidden", "true");
  const labelIn = document.createElement("div"); // label は点の位置に置く 0×0 の箱。中身を上・中央にずらす
  labelIn.className = "lm-label-in";
  label.appendChild(labelIn);
  overlay.appendChild(label);
  const badges = [];
  prefs.forEach((p, i) => {
    if (!p.count) return;
    const b = document.createElement("span");
    b.className = "lm-badge";
    b.textContent = String(p.count);
    b.setAttribute("aria-hidden", "true");
    overlay.appendChild(b);
    badges.push({ i, el: b });
  });
  const insetLabel = document.createElement("span");
  insetLabel.className = "lm-inset-label";
  insetLabel.textContent = "沖縄・奄美（位置を移して表示）";
  insetLabel.setAttribute("aria-hidden", "true");
  overlay.appendChild(insetLabel);

  /* ── カメラ（見る点 T・距離 D・傾き・向き。ドラッグ・ホイール・ピンチで少し動かせる） ── */
  const T = new THREE.Vector3(), Tt = new THREE.Vector3();
  let D = 20, Dt = 20, tilt = 0.62, tiltT = 0.62, az = 0, azT = 0;
  let userAz = 0, userTilt = 0, zoom = 1, width = 1, height = 1, pr = 1;
  let selected = -1, hover = -1;
  let HOME_AZ = 0; // 横長の画面では少し回して、斜めに長い列島を大きく見せる（resize で決める）
  const HOME_TILT = isMobile ? 0.5 : 0.62, FOCUS_TILT = 0.74;

  // 画面に収める点（陸の外周を間引いたもの）：全体用と、県ごと（いちばん大きい陸地だけ）
  const allFit = [], prefFit = [];
  prefs.forEach((p) => {
    const d = dec.prefs[p.id], mine = [];
    let big = null, bigA = -1;
    for (const poly of d.polys) {
      const r = poly[0];
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (let k = 0; k < r.length; k += 2) { x0 = Math.min(x0, r[k]); x1 = Math.max(x1, r[k]); y0 = Math.min(y0, r[k + 1]); y1 = Math.max(y1, r[k + 1]); }
      if ((x1 - x0) * (y1 - y0) > bigA) { bigA = (x1 - x0) * (y1 - y0); big = r; }
      const step = Math.max(2, Math.floor(r.length / 2 / 12) * 2);
      for (let k = 0; k < r.length; k += step) allFit.push(toW(r[k], r[k + 1], new THREE.Vector3()));
    }
    const step = Math.max(2, Math.floor(big.length / 2 / 60) * 2);
    for (let k = 0; k < big.length; k += step) mine.push(toW(big[k], big[k + 1], new THREE.Vector3()));
    prefFit.push(mine);
  });

  function placeCamera(target, dist, tiltV, azV) {
    const el = Math.PI / 2 - tiltV; // 水平からの角度
    camera.position.set(
      target.x + Math.sin(azV) * Math.cos(el) * dist,
      target.y + Math.sin(el) * dist,
      target.z + Math.cos(azV) * Math.cos(el) * dist,
    );
    camera.lookAt(target);
    camera.updateMatrixWorld();
  }
  // 点の集まりが画面の mx×my（NDC）に収まる、見る点と距離（out に見る点を入れて距離を返す）。数回くり返して合わせる
  const _fr = new THREE.Vector3(), _ff = new THREE.Vector3();
  function fit(points, out, tiltV, azV, mx, my) {
    let d = 30;
    const t = Math.tan(THREE.MathUtils.degToRad(FOV / 2));
    for (let it = 0; it < 6; it++) {
      placeCamera(out, d, tiltV, azV);
      let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      for (const p of points) {
        _p.copy(p).project(camera);
        if (_p.x < x0) x0 = _p.x; if (_p.x > x1) x1 = _p.x;
        if (_p.y < y0) y0 = _p.y; if (_p.y > y1) y1 = _p.y;
      }
      _fr.set(Math.cos(azV), 0, -Math.sin(azV));   // 画面の右（地面の上で）
      _ff.set(-Math.sin(azV), 0, -Math.cos(azV));  // 画面の奥
      out.addScaledVector(_fr, ((x0 + x1) / 2) * t * d * camera.aspect).addScaledVector(_ff, (((y0 + y1) / 2) * t * d) / Math.cos(tiltV));
      d *= Math.max((x1 - x0) / 2 / mx, (y1 - y0) / 2 / my, 0.05);
    }
    return d;
  }
  let homeD = 20;
  function home() {
    toW((B[0] + B[2]) / 2, (B[1] + B[3]) / 2, Tt);
    tiltT = HOME_TILT;
    azT = HOME_AZ;
    Dt = homeD = fit(allFit, Tt, tiltT, azT, 0.95, 0.86);
  }
  function focus(i) {
    tiltT = FOCUS_TILT;
    azT = HOME_AZ * 0.5;
    const d = dec.prefs[ids[i]];
    toW(d.c[0], d.c[1], Tt);
    // 県がまわりの県と一緒に見える大きさ（小さい県でも寄りすぎない）
    Dt = clamp(fit(prefFit[i], Tt, tiltT, azT, 0.42, 0.4), 6, homeD * 0.75);
    toW(d.c[0], d.c[1], Tt); // 見る点は県の中心に戻す（ラベルが真ん中に来る）
  }

  function resize() {
    width = Math.max(1, canvas.clientWidth);
    height = Math.max(1, canvas.clientHeight);
    pr = Math.min(window.devicePixelRatio || 1, isMobile ? 1.5 : 1.75);
    renderer.setPixelRatio(pr);
    renderer.setSize(width, height, false);
    composer.setPixelRatio(pr);
    composer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    uPr.value = pr;
    HOME_AZ = width / height > 1.15 ? 0.36 : 0;
    if (selected >= 0) focus(selected); else home();
    invalidate();
  }

  /* ── ループ ── */
  const clock = new THREE.Clock();
  let raf = 0, paused = false, hidden = document.hidden, offscreen = false, disposed = false, time = 0, settleUntil = 0;
  const _p = new THREE.Vector3();

  function placeHtml(el, x, y, z, dy = 0) {
    _p.set(x, y, z).project(camera);
    const vis = _p.z < 1 && Math.abs(_p.x) < 1.1 && Math.abs(_p.y) < 1.1;
    el.style.visibility = vis ? "" : "hidden";
    if (vis) el.style.transform = `translate(${((_p.x + 1) / 2 * width).toFixed(1)}px, ${((1 - _p.y) / 2 * height + dy).toFixed(1)}px)`;
  }

  function frame() {
    raf = 0;
    if (disposed) return;
    const dt = Math.min(clock.getDelta(), 0.1);
    if (!reduced) time += dt;
    uTime.value = time;
    const k = reduced ? 1 : lerpK(dt, 3.2);
    T.lerp(Tt, k);
    D += (Dt * zoom - D) * k;
    tilt += (clamp(tiltT + userTilt, 0.25, 1.05) - tilt) * k;
    az += (azT + userAz - az) * k;
    const drift = reduced ? 0 : Math.sin(time * 0.13) * 0.035;
    placeCamera(T, D, tilt, az + drift);
    seaMat.uniforms.uCenter.value.copy(T);

    // 県の状態をなめらかに
    let moving = Math.abs(D - Dt * zoom) > 0.01 || T.distanceToSquared(Tt) > 1e-5;
    const kk = reduced ? 1 : lerpK(dt, 9);
    for (let i = 0; i < N; i++) {
      const c = cur[i];
      const on = i === hover || i === selected;
      const lt = (i === selected ? LIFT : i === hover ? LIFT * 0.7 : 0);
      const gt = on ? 1 : 0;
      const dm = selected >= 0 && !on ? 1 : 0;
      c.lift += (lt - c.lift) * kk;
      c.glow += (gt - c.glow) * kk;
      c.dim += (dm * 0.6 - c.dim) * kk;
      if (Math.abs(lt - c.lift) > 1e-3 || Math.abs(gt - c.glow) > 1e-3) moving = true;
      uState.value[i].set(c.lift, c.glow, c.has, c.dim);
    }

    // ラベルとバッジ
    for (const b of badges) {
      const d = dec.prefs[ids[b.i]];
      placeHtml(b.el, d.c[0] - CX, H + cur[b.i].lift + 0.02, -(d.c[1] - CY));
      b.el.classList.toggle("is-on", b.i === hover || b.i === selected);
    }
    const li = hover >= 0 ? hover : selected;
    if (li >= 0) {
      const d = dec.prefs[ids[li]];
      placeHtml(label, d.c[0] - CX, H + cur[li].lift + 0.02, -(d.c[1] - CY), -16);
    }
    placeHtml(insetLabel, ib[0] - CX, 0, -(ib[3] - CY));

    composer.render(dt);
    if (!reduced || moving || performance.now() < settleUntil) schedule();
  }
  const running = () => !paused && !hidden && !offscreen && !disposed;
  function schedule() { if (running() && !raf) raf = requestAnimationFrame(frame); }
  function invalidate() {
    settleUntil = performance.now() + 120;
    if (!raf) { clock.getDelta(); schedule(); } // 止まっていたあいだの時間は飛ばす
  }
  function stop() { cancelAnimationFrame(raf); raf = 0; }

  function setLabel(i) {
    if (i < 0) { label.hidden = true; return; }
    const p = prefs[i];
    labelIn.replaceChildren(Object.assign(document.createElement("b"), { textContent: p.name }),
      Object.assign(document.createElement("span"), { textContent: p.count ? `記事 ${p.count}件` : "まだ記事がありません" }));
    label.hidden = false;
  }
  function setHover(i) {
    if (i === hover) return;
    hover = i;
    setLabel(hover >= 0 ? hover : selected);
    canvas.style.cursor = i >= 0 ? "pointer" : "";
    invalidate();
  }

  /* ── 画面の点 → 地図の点 → 県 ── */
  const ray = new THREE.Raycaster(), _ndc = new THREE.Vector2(), _hit = new THREE.Vector3();
  const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -H);
  function pick(clientX, clientY, tolPx) {
    const r = canvas.getBoundingClientRect();
    _ndc.set(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(_ndc, camera);
    if (!ray.ray.intersectPlane(plane, _hit)) return -1;
    const worldPerPx = (2 * camera.position.distanceTo(_hit) * Math.tan(THREE.MathUtils.degToRad(FOV / 2))) / height;
    const id = hitTest(dec, _hit.x + CX, -_hit.z + CY, tolPx * worldPerPx);
    return id ? index[id] : -1;
  }

  /* ── 操作 ── */
  const pts = new Map();
  let down = null, pinch0 = 0, zoom0 = 1, hoverPending = null;
  function onDown(e) {
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pts.size === 1) down = { x: e.clientX, y: e.clientY, t: performance.now(), az: userAz, tilt: userTilt, moved: false, type: e.pointerType };
    if (pts.size === 2) {
      const [a, b] = [...pts.values()];
      pinch0 = Math.hypot(a.x - b.x, a.y - b.y);
      zoom0 = zoom;
      if (down) down.moved = true;
    }
  }
  function onMove(e) {
    if (pts.has(e.pointerId)) pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pts.size === 2 && pinch0 > 0) {
      const [a, b] = [...pts.values()];
      zoom = clamp(zoom0 * (pinch0 / Math.max(1, Math.hypot(a.x - b.x, a.y - b.y))), 0.45, 1.4);
      invalidate();
      return;
    }
    if (down && pts.size === 1) {
      const dx = e.clientX - down.x, dy = e.clientY - down.y;
      if (!down.moved && Math.hypot(dx, dy) > 8) {
        down.moved = true;
        if (e.pointerType !== "touch" || Math.abs(dx) > Math.abs(dy)) canvas.setPointerCapture(e.pointerId);
      }
      if (down.moved) {
        userAz = clamp(down.az - dx * 0.004, -0.6, 0.6);
        if (e.pointerType !== "touch") userTilt = clamp(down.tilt - dy * 0.003, -0.3, 0.3);
        invalidate();
      }
      return;
    }
    if (e.pointerType === "mouse") {
      // ホバー（1フレームに1回だけ調べる）
      if (!hoverPending) requestAnimationFrame(() => { const ev = hoverPending; hoverPending = null; if (ev) setHover(pick(ev.clientX, ev.clientY, 4)); });
      hoverPending = e;
    }
  }
  function onUp(e) {
    pts.delete(e.pointerId);
    if (pts.size < 2) pinch0 = 0;
    if (down && pts.size === 0) {
      const tap = !down.moved && performance.now() - down.t < 700;
      if (tap && e.type === "pointerup") {
        const i = pick(e.clientX, e.clientY, down.type === "touch" ? 22 : 6);
        if (i >= 0) onPick(ids[i]);
      }
      down = null;
    }
  }
  function onLeave() { if (!down) setHover(-1); }
  function onWheel(e) {
    // Ctrl（Mac は ⌘）＋ホイール・トラックパッドのピンチで拡大・縮小。ふつうのホイールはページのスクロールのまま
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    zoom = clamp(zoom * Math.exp(e.deltaY * 0.0012), 0.45, 1.4);
    invalidate();
  }
  canvas.addEventListener("pointerdown", onDown);
  canvas.addEventListener("pointermove", onMove);
  canvas.addEventListener("pointerup", onUp);
  canvas.addEventListener("pointercancel", onUp);
  canvas.addEventListener("pointerleave", onLeave);
  canvas.addEventListener("wheel", onWheel, { passive: false });

  function onVisibility() { hidden = document.hidden; if (hidden) stop(); else invalidate(); }
  document.addEventListener("visibilitychange", onVisibility);
  const ro = new ResizeObserver(() => resize());
  ro.observe(canvas);
  let io = null;
  if ("IntersectionObserver" in window) {
    io = new IntersectionObserver((es) => { offscreen = !es[es.length - 1].isIntersecting; if (offscreen) stop(); else invalidate(); });
    io.observe(canvas);
  }

  resize();
  T.copy(Tt); D = Dt; tilt = tiltT; az = azT;
  invalidate();

  return {
    // 県を選ぶ（null で全体に戻る）。instant = カメラを飛ばさずにすぐ合わせる（最初の表示など）
    select(id, instant = false) {
      const i = id && id in index ? index[id] : -1;
      selected = i;
      zoom = 1;
      userAz = 0;
      userTilt = 0;
      if (i >= 0) focus(i); else home();
      if (instant) { T.copy(Tt); D = Dt; tilt = tiltT; az = azT; }
      setLabel(hover >= 0 ? hover : selected);
      invalidate();
    },
    setPaused(b) { paused = !!b; if (paused) stop(); else invalidate(); },
    dispose() {
      disposed = true;
      stop();
      ro.disconnect();
      if (io) io.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      [landGeo, lineGeo, frameGeo, seaGeo, dustGeo].forEach((g) => g.dispose());
      [landMat, lineMat, frameMat, seaMat, dustMat].forEach((m) => m.dispose());
      composer.dispose();
      renderer.dispose();
      overlay.innerHTML = "";
    },
  };
}
