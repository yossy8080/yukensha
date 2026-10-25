/* 有権者 — 夜の海と空（波打つ平面＋偽の反射、月、遠くの星）
   API: createSea(scene, isMobile) -> { update({ time, cam, dim, glow, glowPos, glowColor }), dispose() } */

import * as THREE from "three";

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
  float md = max(dot(R, uMoonDir), 0.0);
  col += uMoon * (pow(md, 900.0) * 0.4 + pow(md, 80.0) * 0.012);
  // 物体の光が水面に縦に揺れて映る
  vec3 L = normalize(uGlowPos - vWorld);
  float gd = max(dot(R, L), 0.0);
  float nearG = exp(-length(p - uGlowPos.xz) * 0.35);
  col += uGlowColor * uGlow * (pow(gd, 90.0) * 1.2 + pow(gd, 14.0) * 0.08 + nearG * 0.03);
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
  col += uMoon * (smoothstep(0.016, 0.012, r) * 1.4 + exp(-r * 22.0) * 0.22 + exp(-r * 5.0) * 0.04);
  gl_FragColor = vec4(col * uDim, 1.0);
}`;

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

export function createSea(scene, isMobile) {
  const col = (hex) => new THREE.Color(hex);
  const FOG = col(0x0b1a2e);

  const skyMat = new THREE.ShaderMaterial({
    vertexShader: SKY_VS, fragmentShader: SKY_FS, depthWrite: false,
    uniforms: {
      uHorizon: { value: FOG.clone() }, uTop: { value: col(0x04080f) }, uMoon: { value: col(0xd6ecff) },
      uMoonUv: { value: new THREE.Vector2(0.2, 0.36) }, uAspect: { value: 400 / 160 }, uDim: { value: 1 },
    },
  });
  const sky = new THREE.Mesh(new THREE.PlaneGeometry(400, 160), skyMat);
  sky.position.set(0, 78, -160);
  sky.renderOrder = -2;
  scene.add(sky);
  const moonWorld = new THREE.Vector3(-200 + 0.2 * 400, 78 - 80 + 0.36 * 160, -160);

  // 帯の外の、まばらな遠い星
  const starGeo = new THREE.BufferGeometry();
  {
    const r = rng(7), pts = [];
    for (let i = 0; i < (isMobile ? 260 : 520); i++) pts.push((r() - 0.5) * 380, 6 + Math.pow(r(), 0.7) * 90, -158);
    starGeo.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
  }
  const starMat = new THREE.PointsMaterial({ color: 0xb8cbe6, size: isMobile ? 1.2 : 1.5, sizeAttenuation: false, transparent: true, opacity: 0.5, depthWrite: false });
  const stars = new THREE.Points(starGeo, starMat);
  stars.renderOrder = -1;
  scene.add(stars);

  const seg = isMobile ? [110, 80] : [220, 150];
  const oceanGeo = new THREE.PlaneGeometry(160, 120, seg[0], seg[1]);
  oceanGeo.rotateX(-Math.PI / 2);
  const oceanMat = new THREE.ShaderMaterial({
    vertexShader: OCEAN_VS, fragmentShader: OCEAN_FS,
    uniforms: {
      uTime: { value: 0 }, uGlow: { value: 0 }, uFog: { value: 0.022 }, uDim: { value: 1 },
      uCam: { value: new THREE.Vector3() }, uDeep: { value: col(0x02060c) }, uSkyLow: { value: FOG.clone() },
      uSkyHigh: { value: col(0x050b16) }, uMoonDir: { value: moonWorld.clone().normalize() }, uMoon: { value: col(0xd6ecff) },
      uGlowPos: { value: new THREE.Vector3(0, 1.4, 0) }, uGlowColor: { value: col(0x9fcfff) }, uFogColor: { value: FOG.clone() },
    },
  });
  const ocean = new THREE.Mesh(oceanGeo, oceanMat);
  ocean.position.set(0, -0.6, -40);
  scene.add(ocean);

  return {
    update({ time, cam, dim, glow, glowPos }) {
      const u = oceanMat.uniforms;
      u.uTime.value = time;
      u.uCam.value.copy(cam);
      u.uDim.value = dim;
      u.uGlow.value = glow;
      if (glowPos) u.uGlowPos.value.copy(glowPos);
      skyMat.uniforms.uDim.value = dim;
      starMat.opacity = 0.5 * dim;
    },
    dispose() {
      [oceanGeo, starGeo, sky.geometry].forEach((g) => g.dispose());
      [oceanMat, skyMat, starMat].forEach((m) => m.dispose());
    },
  };
}
