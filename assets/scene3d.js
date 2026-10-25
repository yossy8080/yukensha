/* 有権者 — トップの WebGL シーン（夜の海と、府省のエンブレム＝割れた石＋押し出した1文字）
   home.js から dynamic import される。three の読み込みに失敗したら home.js がフォールバックに切り替える。
   API: createScene({ canvas, chapters, glyphs, dprMax, isMobile }) -> { update(state), pick(x, y), setHover(i), setPaused(b), dispose() }
     state = { hero: 0..1, index: 章 (-1=前, n=後), progress: 0..1, anchor: {x, y, size} | null（CSS px）, end: 0..1 }
   公式ロゴは使わない。文字の字形は assets/glyphs.json（Shippori Mincho, OFL）。 */

import * as THREE from "three";
import { SVGLoader } from "three/addons/loaders/SVGLoader.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const SINK = -3.8;            // 沈んだときの高さ（海面下）
const STONE_D = 2.6;          // エンブレムの見かけの直径（ワールド単位, scale=1 のとき）

/* ── 小さな乱数・ノイズ ── */
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
const fbm = (x, y, z) => vnoise(x, y, z) * 0.55 + vnoise(x * 2.1, y * 2.1, z * 2.1) * 0.3 + vnoise(x * 4.3, y * 4.3, z * 4.3) * 0.15;

/* ── 割れた石のジオメトリ：変位させた多面体を、表面のボロノイ領域ごとの破片に分ける ──
   aEdge = 領域の境目までの近さ（0 で境目）。シェーダーで境目＝亀裂を光らせる。 */
function buildStone(seed, detail) {
  const r = rng(seed);
  const base = new THREE.IcosahedronGeometry(1, detail); // 非インデックス（三角形ごとに頂点）
  const p = base.attributes.position;
  const o = [r() * 50, r() * 50, r() * 50];
  const v = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i).normalize();
    const n = fbm(v.x * 1.6 + o[0], v.y * 1.6 + o[1], v.z * 1.6 + o[2]);
    const rad = 0.8 + 0.42 * n;
    p.setXYZ(i, v.x * rad * 1.0, v.y * rad * 1.16, v.z * rad * 0.7);
  }
  const seeds = [];
  const K = 7;
  for (let i = 0; i < K; i++) {
    seeds.push(new THREE.Vector3(r() * 2 - 1, r() * 2 - 1, r() * 2 - 1).normalize());
  }
  seeds[0].set(0.05, 0.1, 1).normalize(); // 正面に1つ置いて、文字の後ろに大きな割れ目ができるように
  const near2 = (d) => {
    let a = 9, b = 9, ai = 0;
    for (let i = 0; i < K; i++) {
      const dist = d.distanceTo(seeds[i]);
      if (dist < a) { b = a; a = dist; ai = i; } else if (dist < b) b = dist;
    }
    return [ai, b - a];
  };
  const cells = seeds.map(() => ({ pos: [], edge: [], center: new THREE.Vector3() }));
  const a = new THREE.Vector3(), c = new THREE.Vector3();
  for (let t = 0; t < p.count; t += 3) {
    c.set(0, 0, 0);
    for (let k = 0; k < 3; k++) c.add(a.fromBufferAttribute(p, t + k));
    const [cell] = near2(c.clone().normalize());
    const cl = cells[cell];
    cl.center.add(c);
    for (let k = 0; k < 3; k++) {
      a.fromBufferAttribute(p, t + k);
      cl.pos.push(a.x, a.y, a.z);
      cl.edge.push(near2(a.clone().normalize())[1]);
    }
  }
  base.dispose();
  return cells.filter((cl) => cl.pos.length).map((cl) => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(cl.pos, 3));
    g.setAttribute("aEdge", new THREE.Float32BufferAttribute(cl.edge, 1));
    g.computeVertexNormals();
    return { geometry: g, dir: cl.center.normalize() };
  });
}

/* ── 亀裂が光る石のマテリアル（MeshStandardMaterial を onBeforeCompile で拡張） ── */
function makeStoneMaterial() {
  const m = new THREE.MeshStandardMaterial({
    color: 0x1a2230, roughness: 0.9, metalness: 0.06, flatShading: true, side: THREE.DoubleSide,
  });
  m.userData.uCrack = { value: new THREE.Color(0, 0, 0) };
  m.onBeforeCompile = (sh) => {
    sh.uniforms.uCrack = m.userData.uCrack;
    sh.vertexShader = "attribute float aEdge;\nvarying float vEdge;\n" +
      sh.vertexShader.replace("#include <begin_vertex>", "#include <begin_vertex>\n  vEdge = aEdge;");
    sh.fragmentShader = "uniform vec3 uCrack;\nvarying float vEdge;\n" +
      sh.fragmentShader.replace("#include <emissivemap_fragment>",
        "#include <emissivemap_fragment>\n  totalEmissiveRadiance += uCrack * (smoothstep(0.075, 0.0, vEdge) + 0.12 * smoothstep(0.28, 0.0, vEdge));");
  };
  m.customProgramCacheKey = () => "yk-stone-crack";
  return m;
}

/* ── 夜の海（波打つ平面＋偽の反射） ── */
const OCEAN_VS = /* glsl */`
uniform float uTime;
varying vec3 vWorld;
float w(vec2 p, vec2 d, float f, float s, float a) { return sin(dot(p, d) * f + uTime * s) * a; }
void main() {
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vec2 p = wp.xz;
  wp.y += w(p, vec2(0.96, 0.28), 0.42, 0.55, 0.07) + w(p, vec2(-0.37, 0.93), 0.77, 0.8, 0.04)
        + w(p, vec2(0.76, -0.65), 1.6, 1.25, 0.016);
  vWorld = wp.xyz;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;
const OCEAN_FS = /* glsl */`
uniform float uTime, uGlow, uFog, uDim;
uniform vec3 uCam, uDeep, uSkyLow, uSkyHigh, uMoonDir, uMoon, uGlowPos, uGlowColor, uFogColor;
varying vec3 vWorld;
vec2 g(vec2 p, vec2 d, float f, float s, float a) { return d * (cos(dot(p, d) * f + uTime * s) * a * f); }
void main() {
  vec2 p = vWorld.xz;
  // 波の傾き（頂点の波＋細かいさざ波）から法線を作る
  vec2 grad = g(p, vec2(0.96, 0.28), 0.42, 0.55, 0.07) + g(p, vec2(-0.37, 0.93), 0.77, 0.8, 0.04)
            + g(p, vec2(0.76, -0.65), 1.6, 1.25, 0.016)
            + g(p, normalize(vec2(0.2, 1.0)), 3.7, 2.1, 0.008) + g(p, normalize(vec2(-0.9, 0.4)), 6.3, 2.9, 0.004)
            + g(p, normalize(vec2(0.6, 0.8)), 11.0, 3.7, 0.0018);
  vec3 N = normalize(vec3(-grad.x, 1.0, -grad.y));
  vec3 V = normalize(uCam - vWorld);
  float fres = 0.02 + 0.98 * pow(1.0 - max(dot(N, V), 0.0), 5.0);
  vec3 R = reflect(-V, N);
  vec3 sky = mix(uSkyLow, uSkyHigh, clamp(R.y * 1.6, 0.0, 1.0));
  vec3 col = mix(uDeep, sky, fres);
  // 月の光の帯
  float md = max(dot(R, uMoonDir), 0.0);
  col += uMoon * (pow(md, 700.0) * 1.1 + pow(md, 80.0) * 0.025);
  // エンブレムの光が水面に縦に揺れて映る
  vec3 L = normalize(uGlowPos - vWorld);
  float gd = max(dot(R, L), 0.0);
  float nearG = exp(-length(p - uGlowPos.xz) * 0.35);
  col += uGlowColor * uGlow * (pow(gd, 90.0) * 1.5 + pow(gd, 14.0) * 0.1 + nearG * 0.03);
  // 霧で水平線を溶かす
  float d = length(uCam - vWorld);
  float f = 1.0 - exp(-pow(d * uFog, 2.0));
  col = mix(col, uFogColor, f) * uDim;
  gl_FragColor = vec4(col, 1.0);
}`;
const SKY_VS = /* glsl */`
varying vec2 vUv;
void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const SKY_FS = /* glsl */`
uniform vec3 uHorizon, uTop, uMoon;
uniform vec2 uMoonUv;
uniform float uAspect, uDim;
varying vec2 vUv;
void main() {
  vec3 col = mix(uHorizon, uTop, smoothstep(0.0, 0.55, vUv.y));
  vec2 d = (vUv - uMoonUv) * vec2(uAspect, 1.0);
  float r = length(d);
  col += uMoon * (smoothstep(0.016, 0.012, r) * 1.6 + exp(-r * 22.0) * 0.28 + exp(-r * 5.0) * 0.05);
  gl_FragColor = vec4(col * uDim, 1.0);
}`;

export function createScene({ canvas, chapters, glyphs, dprMax = 2, isMobile = false }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: !isMobile, powerPreference: "high-performance" });
  if (!renderer.getContext()) throw new Error("WebGL を使えません");
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.setClearColor(0x04080f, 1);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 260);

  // 文字の金属の映り込み用の環境マップ（石には使わない：石は暗いまま、亀裂の光だけが目立つように）
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  pmrem.dispose();

  const col = (hex) => new THREE.Color(hex);
  const FOG = col(0x0b1a2e);

  /* 空（遠くの板）と星 */
  const skyMat = new THREE.ShaderMaterial({
    vertexShader: SKY_VS, fragmentShader: SKY_FS, depthWrite: false,
    uniforms: {
      uHorizon: { value: FOG.clone() }, uTop: { value: col(0x04080f) }, uMoon: { value: col(0xd6ecff) },
      uMoonUv: { value: new THREE.Vector2(0.36, 0.42) }, uAspect: { value: 400 / 160 }, uDim: { value: 1 },
    },
  });
  const sky = new THREE.Mesh(new THREE.PlaneGeometry(400, 160), skyMat);
  sky.position.set(0, 78, -120);
  scene.add(sky);
  // 月のワールド座標（空の板の上の uMoonUv の位置）。水面の光の帯の向きに使う
  const moonWorld = new THREE.Vector3(-200 + 0.36 * 400, 78 - 80 + 0.42 * 160, -120);

  const starGeo = new THREE.BufferGeometry();
  {
    const r = rng(7), pts = [];
    for (let i = 0; i < (isMobile ? 260 : 520); i++) pts.push((r() - 0.5) * 380, 6 + Math.pow(r(), 0.7) * 90, -118);
    starGeo.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
  }
  const starMat = new THREE.PointsMaterial({ color: 0xb8cbe6, size: isMobile ? 1.2 : 1.5, sizeAttenuation: false, transparent: true, opacity: 0.55, depthWrite: false });
  scene.add(new THREE.Points(starGeo, starMat));

  /* 海 */
  const seg = isMobile ? [110, 80] : [220, 150];
  const oceanGeo = new THREE.PlaneGeometry(160, 120, seg[0], seg[1]);
  oceanGeo.rotateX(-Math.PI / 2);
  const oceanMat = new THREE.ShaderMaterial({
    vertexShader: OCEAN_VS, fragmentShader: OCEAN_FS,
    uniforms: {
      uTime: { value: 0 }, uGlow: { value: 0 }, uFog: { value: 0.022 }, uDim: { value: 1 },
      uCam: { value: new THREE.Vector3() }, uDeep: { value: col(0x02060c) }, uSkyLow: { value: FOG.clone() },
      uSkyHigh: { value: col(0x050b16) }, uMoonDir: { value: moonWorld.clone().normalize() }, uMoon: { value: col(0xd6ecff) },
      uGlowPos: { value: new THREE.Vector3(0, 1.4, 0) }, uGlowColor: { value: col(0x8fd0ff) }, uFogColor: { value: FOG.clone() },
    },
  });
  const ocean = new THREE.Mesh(oceanGeo, oceanMat);
  ocean.position.set(0, 0, -40);
  scene.add(ocean);

  /* ライト */
  scene.add(new THREE.AmbientLight(0x22344f, 0.8));
  const moonLight = new THREE.DirectionalLight(0xbcd6f5, 1.4);
  moonLight.position.set(-6, 10, 6);
  scene.add(moonLight);
  const glowLight = new THREE.PointLight(0x8fd0ff, 0, 9, 1.6);
  scene.add(glowLight);

  /* 後処理（弱めのブルーム） */
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), isMobile ? 0.45 : 0.55, 0.42, 0.88);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  /* ── エンブレム（必要な章だけ作ってキャッシュ） ── */
  const stoneVariants = [];
  const stoneVariant = (i) => {
    const k = i % 3;
    if (!stoneVariants[k]) stoneVariants[k] = buildStone(1013 + k * 7919, isMobile ? 2 : 3);
    return stoneVariants[k];
  };
  const coreGeo = new THREE.IcosahedronGeometry(1, 2);
  const shardGeos = [new THREE.TetrahedronGeometry(1, 0), new THREE.OctahedronGeometry(1, 0)];
  const glyphFace = new THREE.MeshStandardMaterial({ color: 0xc4d2e2, metalness: 0.72, roughness: 0.32, envMap: envTex, envMapIntensity: 0.4 });
  const glyphGeoCache = new Map();
  const svgLoader = new SVGLoader();

  function glyphGeometry(ch) {
    if (glyphGeoCache.has(ch)) return glyphGeoCache.get(ch);
    let geo = null;
    const g = glyphs && glyphs[ch];
    if (g && g.d) {
      try {
        const data = svgLoader.parse(`<svg xmlns="http://www.w3.org/2000/svg"><path d="${g.d}"/></svg>`);
        const shapes = data.paths.flatMap((p) => SVGLoader.createShapes(p));
        if (shapes.length) {
          geo = new THREE.ExtrudeGeometry(shapes, {
            depth: 150, bevelEnabled: true, bevelThickness: 16, bevelSize: 9, bevelSegments: isMobile ? 1 : 2,
            curveSegments: isMobile ? 4 : 7,
          });
          // 字形は y が下向き。X 軸まわりに 180° 回すと y が上向きになり、面の向き（巻き順）も崩れない
          geo.rotateX(Math.PI);
          geo.computeBoundingBox();
          const bb = geo.boundingBox, c = new THREE.Vector3();
          bb.getCenter(c);
          geo.translate(-c.x, -c.y, -c.z);
          const s = 1.34 / Math.max(bb.max.x - bb.min.x, bb.max.y - bb.min.y);
          geo.scale(s, s, s);
          geo.computeBoundingSphere();
        }
      } catch (e) {
        geo = null;
      }
    }
    glyphGeoCache.set(ch, geo);
    return geo;
  }

  function glowColorFor(i) {
    // 冷たい青を基調に、章ごとに色相をほんの少しずらす（青緑〜藍）
    const h = 0.535 + ((i * 0.37) % 1) * 0.08;
    return new THREE.Color().setHSL(h, 0.85, 0.72);
  }

  const emblems = new Map();
  function getEmblem(i) {
    if (emblems.has(i)) return emblems.get(i);
    const ch = chapters[i];
    const color = glowColorFor(i);
    const root = new THREE.Group();
    root.userData.index = i;
    const stoneMat = makeStoneMaterial();
    const pieces = stoneVariant(i).map(({ geometry, dir }) => {
      const m = new THREE.Mesh(geometry, stoneMat);
      m.userData.dir = dir;
      m.userData.index = i;
      root.add(m);
      return m;
    });
    const coreMat = new THREE.MeshBasicMaterial({ color: color.clone() });
    const core = new THREE.Mesh(coreGeo, coreMat);
    core.scale.set(0.66, 0.78, 0.44);
    core.userData.index = i;
    root.add(core);
    const r = rng(31 + i * 17);
    const shards = [];
    for (let k = 0; k < 6; k++) {
      const m = new THREE.Mesh(shardGeos[k % 2], stoneMat);
      const s = 0.06 + r() * 0.12;
      m.scale.setScalar(s);
      m.userData = { a: r() * Math.PI * 2, rad: 1.45 + r() * 0.5, y: (r() - 0.5) * 1.6, sp: 0.15 + r() * 0.25, index: i };
      root.add(m);
      shards.push(m);
    }
    let glyphSide = null;
    const geo = glyphGeometry(ch.emblem);
    if (geo) {
      glyphSide = new THREE.MeshStandardMaterial({ color: 0x0c1420, metalness: 0.3, roughness: 0.5, emissive: color.clone(), emissiveIntensity: 1.4 });
      const glyph = new THREE.Mesh(geo, [glyphFace, glyphSide]);
      glyph.position.z = 0.78; // 石の正面に少し埋めて浮かせる（回転しても石からずれて見えにくい）
      glyph.userData.index = i;
      root.add(glyph);
    }
    // 石の破片と核だけを入れる入れ物。府省ごとに向きを少し変える（同じ形の使い回しが目立たないように。文字は傾けない）
    const stoneGroup = new THREE.Group();
    pieces.forEach((m) => stoneGroup.add(m));
    stoneGroup.add(core);
    stoneGroup.rotation.z = (r() - 0.5) * 0.5;
    stoneGroup.rotation.y = (r() - 0.5) * 0.6;
    root.add(stoneGroup);
    root.visible = false;
    const e = {
      i, root, stoneGroup, pieces, coreMat, shards, glyphSide, stoneMat, color,
      sink: SINK, hover: 0, spin: 0, baseRot: (i % 2 ? -1 : 1) * 0.12, vis: 0, want: 0, from: 0, at: 0,
    };
    scene.add(root);
    emblems.set(i, e);
    return e;
  }

  function disposeEmblem(e) {
    scene.remove(e.root);
    e.stoneMat.dispose();
    e.coreMat.dispose();
    if (e.glyphSide) e.glyphSide.dispose();
    emblems.delete(e.i);
  }

  /* ── 状態 ── */
  const state = { hero: 1, index: -1, progress: 0, anchor: null, end: 0 };
  let hoverIndex = -1;
  const slot = new THREE.Vector3(0, 1.45, 0);
  const slotTarget = new THREE.Vector3(0, 1.45, 0);
  let slotScale = 1, slotScaleTarget = 1;
  const pointer = new THREE.Vector2(0, 0), pointerS = new THREE.Vector2(0, 0);
  let heroS = 1, endS = 0;
  const camPos = new THREE.Vector3(), camLook = new THREE.Vector3();
  let width = 1, height = 1;

  function resize() {
    width = Math.max(1, canvas.clientWidth || window.innerWidth);
    height = Math.max(1, canvas.clientHeight || window.innerHeight);
    const pr = Math.min(window.devicePixelRatio || 1, dprMax);
    renderer.setPixelRatio(pr);
    renderer.setSize(width, height, false);
    composer.setPixelRatio(pr);
    composer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  // カメラの構図：ヒーロー（低く、水平線が見える）→ ストリーム（エンブレムが主役）
  const HERO_POS = new THREE.Vector3(0, 0.75, 10.5), HERO_LOOK = new THREE.Vector3(0, 1.6, -20);
  const STREAM_POS = new THREE.Vector3(0, 1.75, 8.5), STREAM_LOOK = new THREE.Vector3(0, 1.35, 0);

  const _ndc = new THREE.Vector3(), _dir = new THREE.Vector3();
  // 画面上の点（CSS px）を、z=0 の面の上のワールド座標に変換
  function screenToWorld(x, y, out) {
    _ndc.set((x / width) * 2 - 1, -(y / height) * 2 + 1, 0.5).unproject(camera);
    _dir.copy(_ndc).sub(camera.position).normalize();
    const t = -camera.position.z / _dir.z;
    return out.copy(camera.position).addScaledVector(_dir, t);
  }

  /* ── ループ ── */
  const clock = new THREE.Clock();
  let raf = 0, paused = false, time = 0, lastFrameAt = 0;
  const lerpK = (dt, speed) => 1 - Math.exp(-dt * speed);
  const RISE_MS = 1200, SINK_MS = 900;

  function frame() {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
    // 描画がまばらな環境（裏のタブ・自動操作のブラウザなど）でも追いつけるよう、経過時間を大きめまで使う
    const dt = Math.min(clock.getDelta(), 0.5);
    const now = performance.now();
    lastFrameAt = now;
    time += Math.min(dt, 0.1);

    heroS += (state.hero - heroS) * lerpK(dt, 4);
    endS += (state.end - endS) * lerpK(dt, 3);
    pointerS.lerp(pointer, lerpK(dt, 2.5));

    // カメラ
    const h = heroS * heroS * (3 - 2 * heroS);
    camPos.lerpVectors(STREAM_POS, HERO_POS, h);
    camLook.lerpVectors(STREAM_LOOK, HERO_LOOK, h);
    if (!isMobile) { camPos.x += pointerS.x * 0.35; camPos.y += pointerS.y * 0.18; }
    camera.position.copy(camPos);
    camera.lookAt(camLook);
    camera.updateMatrixWorld();

    // エンブレムの置き場所（home.js から渡された画面上の位置 → ワールド）
    if (state.anchor && h < 0.98) {
      screenToWorld(state.anchor.x, state.anchor.y, slotTarget);
      const dist = camera.position.distanceTo(slotTarget);
      const worldPerPx = (2 * dist * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))) / height;
      slotScaleTarget = THREE.MathUtils.clamp((state.anchor.size * worldPerPx) / STONE_D, 0.35, 2.4);
    } else {
      slotTarget.set(isMobile ? 0 : 1.6, 1.45, 0);
      slotScaleTarget = 1;
    }
    // スマホはエンブレムの置き場所がスクロールと一緒に動くので、速めに追いかける
    slot.lerp(slotTarget, lerpK(dt, isMobile ? 14 : 5));
    slotScale += (slotScaleTarget - slotScale) * lerpK(dt, 5);

    // 今の章と前後の章だけ用意し、遠い章は片づける
    const n = chapters.length;
    const idx = state.index;
    if (idx >= 0 && idx < n) {
      getEmblem(idx);
      if (idx + 1 < n) glyphGeometry(chapters[idx + 1].emblem);
    }
    let best = null;
    for (const e of emblems.values()) {
      const active = e.i === idx;
      // 浮上・沈下は「何フレーム描いたか」ではなく「切り替わってからの時間」で決める
      // （フレームが少ない環境でも、1.2 秒たてば必ず浮き上がっている）
      const want = active ? 1 : 0;
      if (want !== e.want) { e.from = e.vis; e.want = want; e.at = now; }
      const p = THREE.MathUtils.clamp((now - e.at) / (want ? RISE_MS : SINK_MS), 0, 1);
      const ease = want ? 1 - Math.pow(1 - p, 3) : p * p * (3 - 2 * p);
      e.vis = e.from + (want - e.from) * ease;
      e.sink = SINK * (1 - e.vis);
      e.hover += ((e.i === hoverIndex ? 1 : 0) - e.hover) * lerpK(dt, 6);
      if (!active) e.spin += Math.min(dt, 0.1) * 1.6 * (1 - e.vis * 0.5); // 沈みながら回る
      e.root.visible = e.vis > 0.04;
      if (!e.root.visible && !active && Math.abs(e.i - idx) > 1) { disposeEmblem(e); continue; }

      const float = Math.sin(time * 0.7 + e.i) * 0.07;
      // 沈みきったとき、どの高さに置かれていても石の上端まで海面下に入るよう深さを合わせる
      const depth = (slot.y + 1.7 * slotScale + 0.3) / -SINK;
      e.root.position.set(slot.x, slot.y + float + e.sink * depth, slot.z);
      e.root.scale.setScalar(slotScale);
      const prog = active ? state.progress - 0.5 : 0;
      // 画面の端にあっても文字が石の正面に見えるよう、まずカメラの方を向かせる
      const face = Math.atan2(camera.position.x - slot.x, camera.position.z - slot.z);
      e.root.rotation.y = face + e.baseRot + prog * 0.3 + Math.sin(time * 0.23 + e.i) * 0.08 + pointerS.x * 0.14 + e.spin;
      e.root.rotation.x = -0.06 + Math.sin(time * 0.31 + e.i * 2) * 0.04 - pointerS.y * 0.1 + (1 - e.vis) * 0.5;
      e.stoneGroup.rotation.x = Math.sin(time * 0.17 + e.i) * 0.05;

      // 割れ目：浮いている間はわずかに開き、沈むときは大きく崩れる
      const gap = 0.045 + Math.sin(time * 0.9 + e.i) * 0.012 + e.hover * 0.05 + (1 - e.vis) * 0.5;
      for (const m of e.pieces) m.position.copy(m.userData.dir).multiplyScalar(gap);
      for (const s of e.shards) {
        const u = s.userData;
        const a = u.a + time * u.sp;
        s.position.set(Math.cos(a) * u.rad, u.y + Math.sin(time * 0.6 + u.a) * 0.08, Math.sin(a) * u.rad * 0.6);
        s.rotation.set(time * u.sp * 1.3, time * u.sp, 0);
      }
      const pulse = 0.85 + Math.sin(time * 1.3 + e.i) * 0.15;
      const glow = (1.2 + e.hover * 1.4) * pulse * (0.4 + 0.6 * e.vis);
      e.stoneMat.userData.uCrack.value.copy(e.color).multiplyScalar(glow * 1.6);
      e.coreMat.color.copy(e.color).multiplyScalar(1.45 + e.hover * 1.4);
      if (e.glyphSide) e.glyphSide.emissiveIntensity = 0.75 + e.hover * 1.0;
      if (!best || e.vis > best.vis) best = e;
    }

    // 水面への映り込みとエンブレムの光
    const u = oceanMat.uniforms;
    if (best && best.root.visible) {
      u.uGlowPos.value.copy(best.root.position);
      u.uGlowColor.value.copy(best.color);
      u.uGlow.value = best.vis * (1 + best.hover * 0.8) * (1 - endS);
      glowLight.position.set(best.root.position.x + 0.4, best.root.position.y + 0.6, best.root.position.z + 2.2);
      glowLight.color.copy(best.color);
      glowLight.intensity = best.vis * (4.5 + best.hover * 4) * Math.sqrt(slotScale);
    } else {
      u.uGlow.value *= 0.9;
      glowLight.intensity *= 0.9;
    }
    u.uTime.value = time;
    u.uCam.value.copy(camera.position);
    const dim = 1 - endS * 0.45;
    u.uDim.value = dim;
    skyMat.uniforms.uDim.value = dim;
    starMat.opacity = 0.55 * dim;

    composer.render(dt);
    schedule();
  }

  // 非表示のタブでは requestAnimationFrame 自体をブラウザが止めるので、ここでは document.hidden を見ない
  // （document.hidden の判定に頼ると、自動操作のブラウザなどで一度も描かれないことがある）
  let fallbackT = 0, lastUpdateAt = 0;
  function schedule() {
    if (paused) return;
    if (!raf) raf = requestAnimationFrame(frame);
    // 保険：スクロールなどで状態が変わってから 3 秒間は、rAF が来なくてもタイマーで描き直す（浮上の途中で止まらないように）
    clearTimeout(fallbackT);
    if (performance.now() - lastUpdateAt < 3000) {
      fallbackT = setTimeout(() => { if (!paused && performance.now() - lastFrameAt > 300) frame(); }, 350);
    }
  }
  function onVisibility() {
    if (!document.hidden) { clock.getDelta(); schedule(); }
  }
  function onPointer(e) {
    pointer.set((e.clientX / width) * 2 - 1, -((e.clientY / height) * 2 - 1));
  }

  resize();
  window.addEventListener("resize", resize);
  document.addEventListener("visibilitychange", onVisibility);
  if (!isMobile) window.addEventListener("pointermove", onPointer, { passive: true });
  schedule();

  const raycaster = new THREE.Raycaster();
  const _pick = new THREE.Vector2();

  return {
    update(s) {
      if (!s) return;
      if (typeof s.hero === "number") state.hero = s.hero;
      if (typeof s.index === "number") state.index = s.index;
      if (typeof s.progress === "number") state.progress = s.progress;
      if (typeof s.end === "number") state.end = s.end;
      state.anchor = s.anchor || null;
      lastUpdateAt = performance.now();
      // rAF がしばらく来ていない（描画が止められている）ときは、その場で1枚描く
      if (!paused) { if (lastUpdateAt - lastFrameAt > 400) frame(); else schedule(); }
    },
    pick(x, y) {
      const targets = [];
      for (const e of emblems.values()) if (e.root.visible && e.vis > 0.6) targets.push(e.root);
      if (!targets.length) return -1;
      _pick.set((x / width) * 2 - 1, -(y / height) * 2 + 1);
      raycaster.setFromCamera(_pick, camera);
      const hit = raycaster.intersectObjects(targets, true)[0];
      return hit ? hit.object.userData.index ?? -1 : -1;
    },
    setHover(i) { hoverIndex = i; },
    setPaused(b) {
      paused = !!b;
      if (paused) { cancelAnimationFrame(raf); raf = 0; clearTimeout(fallbackT); }
      else { clock.getDelta(); schedule(); }
    },
    dispose() {
      cancelAnimationFrame(raf);
      clearTimeout(fallbackT);
      raf = 0;
      paused = true;
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pointermove", onPointer);
      for (const e of [...emblems.values()]) disposeEmblem(e);
      for (const v of stoneVariants) if (v) v.forEach((p) => p.geometry.dispose());
      for (const g of glyphGeoCache.values()) if (g) g.dispose();
      [coreGeo, ...shardGeos, oceanGeo, starGeo, sky.geometry].forEach((g) => g.dispose());
      [glyphFace, oceanMat, skyMat, starMat].forEach((m) => m.dispose());
      envTex.dispose();
      composer.dispose();
      renderer.dispose();
    },
  };
}
