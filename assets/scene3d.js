/* 有権者 — トップの WebGL シーン（夜の海、天の川の帯、光の粒子でできた府省の物体）
   home.js から dynamic import される。three の読み込みに失敗したら home.js がフォールバックに切り替える。
   API: createScene({ canvas, chapters, dprMax, isMobile }) -> { update(state), pick(x, y), setHover(i), setPaused(b), dispose() }
     chapters = [{ id, name, model }]（model = models3d.js の物体のキー）
     state = { hero: 0..1, f: 章の位置（-1=ヒーロー, 0..n-1=各章, n=章の後。小数はあいだ）, anchor: {x, y, size}（CSS px）, end: 0..1 }
   物体は画面に貼り付いた1つだけ。スクロール（f）に合わせて、今の府省の形 → 次の府省の形へ粒子が流れながら変形する。
   動きはすべて「経過時間」と「スクロール位置」で決める（描いたフレームの数には比例しない）。 */

import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { buildModel, sampleModel } from "./models3d.js";
import { createBand, S0 } from "./band3d.js";
import { createMorph } from "./morph3d.js";
import { createSea } from "./sea3d.js";
import { createGalaxy } from "./galaxy3d.js";

const MODEL_SIZE = 2.6; // models3d.js の物体の最大の幅
const HOLD = 0.24;      // 章の中央の前後この割合は、形を止めて見せる
const NODE_STEP = 0.055; // 帯の上の、府省の節どうしの間隔（帯のパラメータ）

const clamp01 = (v) => Math.max(0, Math.min(1, v));
const smooth = (t) => t * t * (3 - 2 * t);

export function createScene({ canvas, chapters, dprMax = 1.75, isMobile = false }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" });
  if (!renderer.getContext()) throw new Error("WebGL を使えません");
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.setClearColor(0x04080f, 1);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 400);
  const sea = createSea(scene, isMobile);
  const band = createBand();
  const COUNT = isMobile ? 5000 : 10000;
  const morph = createMorph({ count: COUNT, band });
  scene.add(morph.object);
  const galaxy = createGalaxy({ band, isMobile, nodes: chapters.length });
  scene.add(galaxy.object);

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), isMobile ? 0.5 : 0.62, 0.5, 0.62);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  /* ── 府省の形（点の並び）は必要になったときに作ってキャッシュ ── */
  const shapes = new Map();
  function shapeOf(i) {
    const key = (chapters[i] && chapters[i].model) || "compass";
    if (!shapes.has(key)) {
      const model = buildModel(key);
      let seed = 0;
      for (const c of key) seed = (seed * 31 + c.charCodeAt(0)) >>> 0;
      shapes.set(key, { model, pts: sampleModel(model, COUNT, seed) });
    }
    return shapes.get(key);
  }
  // 次に使いそうな形を、手が空いたときに用意しておく
  const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 120));
  let prepIdx = 0;
  function prepare() {
    if (prepIdx >= chapters.length || disposed) return;
    shapeOf(prepIdx++);
    idle(prepare);
  }

  /* ── 状態 ── */
  const state = { hero: 1, f: -1, anchor: null, end: 0 };
  let fS = -1, heroS = 1, endS = 0, hoverS = 0, hoverIndex = -1, curIndex = -1;
  let ms = { a: 0, b: 0, p: 0.5 };
  const pointer = new THREE.Vector2(), pointerS = new THREE.Vector2();
  const center = new THREE.Vector3(0, 1.45, 0), centerT = new THREE.Vector3();
  let scale = 0.8, scaleT = 0.8, width = 1, height = 1, pr = 1;

  function resize() {
    width = Math.max(1, canvas.clientWidth || window.innerWidth);
    height = Math.max(1, canvas.clientHeight || window.innerHeight);
    pr = Math.min(window.devicePixelRatio || 1, dprMax);
    renderer.setPixelRatio(pr);
    renderer.setSize(width, height, false);
    composer.setPixelRatio(pr);
    composer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  // f（章の位置）→ どの形からどの形へ、どこまで進んだか（p = 0 今の形, 0.5 帯の中, 1 次の形）
  function morphState(f) {
    const n = chapters.length;
    if (!n || f <= -1) return { a: 0, b: 0, p: 0.5 };
    const i = Math.floor(f);
    const p = smooth(clamp01((f - i - HOLD) / (1 - 2 * HOLD)));
    if (i < 0) return { a: 0, b: 0, p: 0.5 + 0.5 * p };      // ヒーロー → 最初の府省：帯から集まる
    if (i >= n) return { a: n - 1, b: n - 1, p: 0.5 };
    if (i === n - 1) return { a: i, b: i, p: 0.5 * p };     // 最後の府省 → 帯へ戻る
    return { a: i, b: i + 1, p };
  }

  // カメラの構図：ヒーロー（低く、水平線と天の川）→ 府省の流れ（物体が主役）
  const HERO_POS = new THREE.Vector3(0, 0.75, 10.5), HERO_LOOK = new THREE.Vector3(0, 2.4, -20);
  const STREAM_POS = new THREE.Vector3(0, 1.75, 8.5), STREAM_LOOK = new THREE.Vector3(0, 1.45, 0);
  const camPos = new THREE.Vector3(), camLook = new THREE.Vector3();
  const _ndc = new THREE.Vector3(), _dir = new THREE.Vector3();
  function screenToWorld(x, y, out) {
    _ndc.set((x / width) * 2 - 1, -(y / height) * 2 + 1, 0.5).unproject(camera);
    _dir.copy(_ndc).sub(camera.position).normalize();
    const t = -camera.position.z / _dir.z;
    return out.copy(camera.position).addScaledVector(_dir, t);
  }

  const rot = new THREE.Matrix4(), _e = new THREE.Euler();

  /* ── ループ ── */
  const clock = new THREE.Clock();
  let raf = 0, paused = false, offscreen = false, hidden = document.hidden, disposed = false;
  let time = 0, lastFrameAt = 0, lastUpdateAt = 0, fallbackT = 0;
  const lerpK = (dt, speed) => 1 - Math.exp(-dt * speed);

  function frame() {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
    if (disposed) return;
    const now = performance.now();
    // 経過時間で進める。描画が長く止まっていた（タブの切り替えなど）ときは、スクロール位置にすぐ合わせる
    const dt = Math.min(clock.getDelta(), 0.5);
    const long = now - lastFrameAt > 700;
    lastFrameAt = now;
    time += dt;
    const k = long ? 1 : lerpK(dt, 6);
    fS += (state.f - fS) * k;
    heroS += (state.hero - heroS) * (long ? 1 : lerpK(dt, 4));
    endS += (state.end - endS) * (long ? 1 : lerpK(dt, 3));
    pointerS.lerp(pointer, lerpK(dt, 2.5));

    const h = smooth(clamp01(heroS));
    camPos.lerpVectors(STREAM_POS, HERO_POS, h);
    camLook.lerpVectors(STREAM_LOOK, HERO_LOOK, h);
    if (!isMobile) { camPos.x += pointerS.x * 0.3; camPos.y += pointerS.y * 0.15; }
    camera.position.copy(camPos);
    camera.lookAt(camLook);
    camera.updateMatrixWorld();

    // 物体の置き場所（home.js から渡された画面上の位置 → ワールド）
    if (state.anchor) {
      screenToWorld(state.anchor.x, state.anchor.y, centerT);
      const dist = camera.position.distanceTo(centerT);
      const worldPerPx = (2 * dist * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))) / height;
      scaleT = THREE.MathUtils.clamp((state.anchor.size * 0.82 * worldPerPx) / MODEL_SIZE, 0.3, 2.4);
    }
    const ka = long ? 1 : lerpK(dt, 8);
    center.lerp(centerT, ka);
    scale += (scaleT - scale) * ka;
    band.setAnchor(center, isMobile);

    // 形の組み合わせと進み具合
    const n = chapters.length;
    ms = morphState(fS);
    if (n) morph.setShapes(shapeOf(ms.a), shapeOf(ms.b));
    curIndex = !n ? -1 : ms.p < 0.2 ? ms.a : ms.p > 0.8 ? ms.b : -1;
    if (ms.a === ms.b && ms.p > 0.2 && ms.p < 0.8) curIndex = -1;
    hoverS += ((curIndex >= 0 && curIndex === hoverIndex ? 1 : 0) - hoverS) * lerpK(dt, 8);

    // ゆっくり左右に振れながら、いつもカメラの方を向く（上下も：スマホのように画面の上に置いても下から見上げてつぶれないように）
    const dx = camera.position.x - center.x, dz = camera.position.z - center.z;
    const face = Math.atan2(dx, dz);
    const tilt = Math.atan2(center.y - camera.position.y, Math.hypot(dx, dz));
    // スマホは物体が画面の真ん中に来て真正面になりやすいので、PC と同じように少し斜め上から見せて奥行きを出す
    const bias = isMobile ? [0.16, 0.38] : [0, 0];
    _e.set(tilt + bias[0] + 0.05 + Math.sin(time * 0.21) * 0.05 - pointerS.y * 0.08,
      face + bias[1] + Math.sin(time * 0.27) * (isMobile ? 0.22 : 0.34) + pointerS.x * 0.16, 0, "YXZ");
    rot.makeRotationFromEuler(_e);
    const settled = clamp01(1 - 5 * Math.min(ms.p, 1 - ms.p)); // 1 = 形が落ち着いている
    const flow = fS * NODE_STEP;
    morph.update({
      p: ms.p, time, center, scale, rot, hover: hoverS, pr, size: isMobile ? 2.6 : 2.2,
      flow: fS * 0.6 + time * 0.012, bright: 1 - endS * 0.85,
    });
    morph.uniforms.uS0.value = S0;
    galaxy.update({ time, flow: flow + time * 0.0015, f: fS, step: NODE_STEP, s0: S0, pr, settled, center, radius: scale * 1.3, dim: 1 - endS * 0.5 });

    const dim = 1 - endS * 0.45;
    sea.update({ time, cam: camera.position, dim, glow: settled * 0.3 * (1 + hoverS * 0.6) * (1 - endS), glowPos: center });

    composer.render(dt);
    schedule();
  }

  function running() { return !paused && !offscreen && !hidden && !disposed; }
  function schedule() {
    if (!running()) return;
    if (!raf) raf = requestAnimationFrame(frame);
    // 保険：rAF が間引かれる環境でも、スクロールの直後 3 秒間はタイマーで描き直す（変形の途中で止まらないように）
    clearTimeout(fallbackT);
    if (performance.now() - lastUpdateAt < 3000) {
      fallbackT = setTimeout(() => { if (running() && performance.now() - lastFrameAt > 300) frame(); }, 350);
    }
  }
  function stop() { cancelAnimationFrame(raf); raf = 0; clearTimeout(fallbackT); }
  function resume() { if (!running()) return; clock.getDelta(); frame(); }
  function onVisibility() {
    hidden = document.hidden;
    if (hidden) stop(); else resume();
  }
  function onPointer(e) {
    pointer.set((e.clientX / width) * 2 - 1, -((e.clientY / height) * 2 - 1));
  }

  resize();
  window.addEventListener("resize", resize);
  document.addEventListener("visibilitychange", onVisibility);
  if (!isMobile) window.addEventListener("pointermove", onPointer, { passive: true });
  // 画面外（display:none など）になったら止める
  let io = null;
  if ("IntersectionObserver" in window) {
    io = new IntersectionObserver((es) => {
      offscreen = !es[es.length - 1].isIntersecting;
      if (offscreen) stop(); else resume();
    });
    io.observe(canvas);
  }
  idle(prepare);
  schedule();

  const raycaster = new THREE.Raycaster();
  const _pick = new THREE.Vector2();

  return {
    update(s) {
      if (!s) return;
      if (typeof s.hero === "number") state.hero = s.hero;
      if (typeof s.f === "number") state.f = s.f;
      if (typeof s.end === "number") state.end = s.end;
      if (s.anchor) state.anchor = s.anchor;
      lastUpdateAt = performance.now();
      // rAF がしばらく来ていない（描画が止められている）ときは、その場で1枚描く
      if (running()) { if (lastUpdateAt - lastFrameAt > 400) frame(); else schedule(); }
    },
    // 画面上の点が物体に当たっていれば、その章の番号（当たらなければ -1）
    pick(x, y) {
      if (curIndex < 0) return -1;
      _pick.set((x / width) * 2 - 1, -(y / height) * 2 + 1);
      raycaster.setFromCamera(_pick, camera);
      return morph.pick(raycaster, ms.p < 0.5 ? 0 : 1) ? curIndex : -1;
    },
    current() { return curIndex; },
    setHover(i) { hoverIndex = i; },
    setPaused(b) {
      paused = !!b;
      if (paused) stop(); else resume();
    },
    dispose() {
      disposed = true;
      stop();
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pointermove", onPointer);
      if (io) io.disconnect();
      morph.dispose();
      galaxy.dispose();
      sea.dispose();
      for (const s of shapes.values()) { s.model.merged.dispose(); s.model.edges.dispose(); }
      composer.dispose();
      renderer.dispose();
    },
  };
}
