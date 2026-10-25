/* 有権者 — 新しいトップ（index.html）の組み立てと演出（ES module）
   1. news.json から「府省の章」を作る（記事が1件以上ある府省を sources.json の順に。0件の府省は最後に名前だけ）
   2. スクロール位置から「いまの章」と進み具合を計算し、背面の WebGL（scene3d.js）に渡す（スクロールの乗っ取りはしない）
   3. ページを貫く1本の光の線（SVG）をスクロールに合わせて描く／各章はピンボケから焦点が合って現れる
   4. エンブレム（3D はクリック判定に Raycaster、キーボードは透明ボタン）→ その府省の記事ビュー（hall.js）
   WebGL が使えない・three の読み込みに失敗・動きを減らす設定のときは、CSS の明朝文字のエンブレムで同じ操作ができる。 */

/* global Y */
import { initHall } from "./hall.js";

const html = document.documentElement;
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const isMobile = matchMedia("(max-width: 720px)").matches || matchMedia("(pointer: coarse)").matches;
const $ = (s, el = document) => el.querySelector(s);
const clamp01 = (v) => Math.max(0, Math.min(1, v));
const pad2 = (n) => String(n).padStart(2, "0");

/* ── ローディング：光のリングが 0→100 を数え、ロゴの位置へ縮んで畳まれる（1.5 秒以内） ── */
const loader = $("#loader");
const loaderStart = performance.now();
function finishLoader() {
  if (!loader) return Promise.resolve();
  if (reduced) { loader.remove(); return Promise.resolve(); }
  const num = $(".loader-num", loader);
  const ring = $(".loader-ring circle.on", loader);
  const total = 1050; // 数える時間（ms）
  return new Promise((resolve) => {
    const step = (t) => {
      const p = clamp01((t - loaderStart) / total);
      const e = 1 - Math.pow(1 - p, 3);
      if (num) num.textContent = String(Math.round(e * 100));
      if (ring) ring.style.strokeDashoffset = String(1 - e);
      if (p < 1) requestAnimationFrame(step);
      else fold().then(resolve);
    };
    requestAnimationFrame(step);
  });
}
function fold() {
  const box = $(".loader-box", loader);
  const logo = $(".site-logo");
  if (!box || !logo || !box.animate) { loader.remove(); return Promise.resolve(); }
  const a = box.getBoundingClientRect(), b = logo.getBoundingClientRect();
  const dx = b.left + b.width / 2 - (a.left + a.width / 2);
  const dy = b.top + b.height / 2 - (a.top + a.height / 2);
  const s = Math.max(0.06, b.height / a.height);
  const anim = box.animate(
    [{ transform: "none", opacity: 1 }, { transform: `translate(${dx}px, ${dy}px) scale(${s})`, opacity: 0.2 }],
    { duration: 380, easing: "cubic-bezier(.6,0,.3,1)", fill: "forwards" });
  loader.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 380, delay: 80, fill: "forwards" });
  return anim.finished.catch(() => {}).then(() => {
    loader.remove();
    logo.classList.add("is-arrived");
  });
}

/* ── 章の HTML ── */
function chapterHTML(s, i, n, items) {
  const latest = items.slice(0, 3).map((it) => `
      <li><time datetime="${Y.esc(it.date)}">${Y.fmtDate(it.date)}</time><a href="#a=${encodeURIComponent(it.id)}">${Y.esc(it.title)}</a></li>`).join("");
  const side = i % 2 ? "left" : "right";
  const id = Y.esc(s.id);
  return `
  <section class="chapter" id="ch-${id}" data-i="${i}" data-side="${side}" aria-labelledby="ch-${id}-title">
    <div class="ch-visual">
      <div class="ch-anchor">
        <button type="button" class="emblem-hit" data-m="${id}" aria-label="${Y.esc(s.name)}の記事をひらく">
          <span class="emblem-fallback" aria-hidden="true"><span>${Y.esc(s.emblem || s.name.slice(0, 1))}</span></span>
        </button>
      </div>
    </div>
    <div class="ch-text">
      <div class="ch-card reveal">
        <p class="ch-no"><b>${pad2(i + 1)}</b> / ${pad2(n)}</p>
        <h3 class="ch-name" id="ch-${id}-title">${Y.esc(s.name)}</h3>
        <p class="ch-count">記事 ${items.length}件${s.note ? `<span>${Y.esc(s.note)}</span>` : ""}</p>
        <ul class="ch-latest">${latest}</ul>
        <button type="button" class="ch-open" data-m="${id}">記事をひらく <span aria-hidden="true">→</span></button>
      </div>
    </div>
  </section>`;
}

/* ── 光の流れ（ページ全長を貫く1本の線） ── */
const flow = { svg: null, glow: null, core: null, spark: null, len: 0, samples: [] };
function buildFlow(chapterEls) {
  const svg = $("#flow");
  if (!svg) return;
  const main = $("main");
  const W = main.clientWidth, H = main.scrollHeight;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.style.height = H + "px";
  const mr = main.getBoundingClientRect();
  const top = mr.top + scrollY;
  const yOf = (el) => el.getBoundingClientRect().top - mr.top; // main の中での位置
  const pts = [];
  const hero = $("#hero");
  pts.push([W / 2, yOf(hero) + hero.offsetHeight * 0.74]);
  const head = $(".stream-head");
  if (head) pts.push([W / 2, yOf(head) + head.offsetHeight * 0.5]);
  const side = Math.max(10, W * 0.06);
  for (const ch of chapterEls) {
    const r = $(".ch-anchor", ch).getBoundingClientRect();
    const cx = r.left + r.width / 2 - mr.left;
    // エンブレムが止まる高さ（章の頭からほぼ画面中央）で、ページ中央側の縁に流れ込む（文字の上は横切らない）
    // スマホはエンブレムの下に章の文章が重なるので、左の余白を通す
    const x = isMobile ? side : cx + Math.sign(W / 2 - cx) * r.width * 0.36;
    pts.push([x, yOf(ch) + Math.min(ch.offsetHeight * 0.5, innerHeight * (isMobile ? 0.3 : 0.5))]);
  }
  // 後半の見出しは中央に大きく置くので、線は左の余白を通す
  document.querySelectorAll(".later").forEach((sec) => pts.push([side, yOf(sec) + sec.offsetHeight * 0.5]));
  pts.push([side, H - 2]);
  // 縦向きの接線でつなぐ滑らかな曲線
  let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let k = 1; k < pts.length; k++) {
    const [x0, y0] = pts[k - 1], [x1, y1] = pts[k];
    const my = (y1 - y0) * 0.5;
    d += ` C${x0.toFixed(1)},${(y0 + my).toFixed(1)} ${x1.toFixed(1)},${(y1 - my).toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}`;
  }
  flow.glow = $(".flow-glow", svg);
  flow.core = $(".flow-core", svg);
  flow.spark = $(".flow-spark", svg);
  flow.glow.setAttribute("d", d);
  flow.core.setAttribute("d", d);
  flow.len = flow.core.getTotalLength();
  flow.samples = [];
  for (let k = 0; k <= 240; k++) {
    const L = (k / 240) * flow.len;
    flow.samples.push([L, flow.core.getPointAtLength(L).y]);
  }
  for (const p of [flow.glow, flow.core]) p.style.strokeDasharray = `${flow.len} ${flow.len}`;
  flow.svg = svg;
  flow.top = top;
}
function drawFlow() {
  if (!flow.svg || !flow.len) return;
  const y = scrollY + innerHeight * 0.62 - flow.top;
  const s = flow.samples;
  let L = 0;
  if (y >= s[s.length - 1][1]) L = flow.len;
  else {
    for (let k = 1; k < s.length; k++) {
      if (s[k][1] >= y) {
        const [l0, y0] = s[k - 1], [l1, y1] = s[k];
        L = l0 + (l1 - l0) * clamp01((y - y0) / Math.max(1e-3, y1 - y0));
        break;
      }
    }
  }
  const off = String(flow.len - L);
  flow.glow.style.strokeDashoffset = off;
  flow.core.style.strokeDashoffset = off;
  if (L > 2 && L < flow.len - 2) {
    const p = flow.core.getPointAtLength(L);
    flow.spark.setAttribute("cx", p.x.toFixed(1));
    flow.spark.setAttribute("cy", p.y.toFixed(1));
    flow.spark.style.opacity = "1";
  } else flow.spark.style.opacity = "0";
}

/* ── ピンボケから焦点が合って現れる ── */
function setupReveal() {
  const els = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window)) { els.forEach((el) => el.classList.add("is-in")); return; }
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) { e.target.classList.add("is-in"); io.unobserve(e.target); }
  }, { rootMargin: "0px 0px -12% 0px", threshold: 0.15 });
  els.forEach((el) => io.observe(el));
}

function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch (e) { return false; }
}

/* ── 組み立て ── */
async function main() {
  const glyphsP = Y.load("assets/glyphs.json").catch(() => ({}));
  const [sources, news] = await Promise.all([Y.load("data/sources.json"), Y.load("data/news.json")]);
  const srcMap = Object.fromEntries(sources.map((s) => [s.id, s]));
  news.sort(Y.byDateDesc);
  const has = (n, id) => n.ministry === id || (n.also || []).includes(id);
  const itemsOf = (id) => news.filter((n) => has(n, id));
  const visible = Y.visible(sources);
  const chapters = visible.filter((s) => itemsOf(s.id).length);
  const quiet = visible.filter((s) => !itemsOf(s.id).length);

  // ヒーロー：最新の featured 記事を1件
  const top = news.find((n) => n.featured) || news[0];
  const latest = $("#hero-latest");
  if (top && latest) {
    latest.innerHTML = `<span class="hero-latest-label">最新</span><a href="#a=${encodeURIComponent(top.id)}">${Y.esc(top.title)}</a><span class="hero-latest-m">${Y.esc(srcMap[top.ministry]?.name || "")}</span>`;
    latest.hidden = false;
  }

  // 府省の章
  $("#stream-meta").textContent = `${chapters.length}の府省 · ${news.length}件の記事`;
  const box = $("#chapters");
  box.innerHTML = chapters.map((s, i) => chapterHTML(s, i, chapters.length, itemsOf(s.id))).join("");
  if (quiet.length) {
    $("#quiet").hidden = false;
    $("#quiet-list").innerHTML = quiet.map((s) => `<li>${Y.esc(s.name)}</li>`).join("");
  }
  const chapterEls = [...box.querySelectorAll(".chapter")];

  // 記事ビュー（Mirror Hall）
  let scene = null;
  const hall = initHall({
    sources, news, srcMap, order: chapters.map((s) => s.id),
    onToggle: (open) => { if (scene) scene.setPaused(open); },
  });
  document.addEventListener("click", (e) => {
    const b = e.target.closest && e.target.closest("[data-m]");
    if (b && (b.classList.contains("emblem-hit") || b.classList.contains("ch-open"))) hall.openMinistry(b.dataset.m);
  });

  setupReveal();

  /* スクロール → WebGL の状態 */
  const hero = $("#hero"), stream = $("#stream");
  function computeState() {
    const vh = innerHeight, mid = vh * 0.5;
    const hr = hero.getBoundingClientRect();
    const st = { hero: clamp01(hr.bottom / Math.max(1, hr.height)), index: -1, progress: 0, anchor: null, end: 0 };
    if (chapterEls.length) {
      const first = chapterEls[0].getBoundingClientRect();
      const last = chapterEls[chapterEls.length - 1].getBoundingClientRect();
      if (mid < first.top) st.index = -1;
      else if (mid > last.bottom) st.index = chapterEls.length;
      else {
        for (let i = 0; i < chapterEls.length; i++) {
          const r = chapterEls[i].getBoundingClientRect();
          if (mid >= r.top && mid <= r.bottom) {
            st.index = i;
            st.progress = clamp01((mid - r.top) / r.height);
            const a = $(".ch-anchor", chapterEls[i]).getBoundingClientRect();
            st.anchor = { x: a.left + a.width / 2, y: a.top + a.height / 2, size: a.width * 0.82 };
            break;
          }
        }
      }
    }
    const sb = stream.getBoundingClientRect().bottom;
    st.end = clamp01((mid - sb) / vh);
    return st;
  }

  let ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      ticking = false;
      if (scene) scene.update(computeState());
      drawFlow();
    });
  }
  addEventListener("scroll", onScroll, { passive: true });

  let resizeT = 0;
  const relayout = () => { buildFlow(chapterEls); onScroll(); };
  addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(relayout, 150); });
  relayout();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(relayout);
  addEventListener("load", relayout);

  // ローディングを終える（データの用意ができたら。最大 1.5 秒）
  const loaded = finishLoader();

  /* WebGL（使えなければフォールバックのまま） */
  if (!reduced && webglAvailable()) {
    try {
      const [mod, glyphs] = await Promise.all([import("./scene3d.js"), glyphsP]);
      scene = mod.createScene({
        canvas: $("#scene"),
        chapters: chapters.map((s) => ({ id: s.id, name: s.name, emblem: s.emblem || s.name.slice(0, 1) })),
        glyphs,
        dprMax: isMobile ? 1.5 : 2,
        isMobile,
      });
      html.classList.add("webgl");
      html.classList.remove("no-webgl");
      scene.update(computeState());
      setupPicking(scene, chapters, hall);
    } catch (e) {
      scene = null;
      html.classList.add("no-webgl");
    }
  } else {
    html.classList.add("no-webgl");
  }
  await loaded;
}

/* 3D のエンブレムをホバー・クリック（Raycaster）。文字や操作部品の上では何もしない */
function setupPicking(scene, chapters, hall) {
  const blocked = (t) => t.closest && t.closest("a, button, input, .ch-card, .site-header, .hero-inner, .later, footer, .hall");
  let hover = -1, pending = null;
  addEventListener("pointermove", (e) => {
    if (e.pointerType === "touch") return;
    pending = e;
    requestAnimationFrame(() => {
      if (!pending) return;
      const ev = pending;
      pending = null;
      const i = blocked(ev.target) || html.classList.contains("hall-open") ? -1 : scene.pick(ev.clientX, ev.clientY);
      if (i !== hover) {
        hover = i;
        scene.setHover(i);
        html.classList.toggle("emblem-hover", i >= 0);
      }
    });
  }, { passive: true });
  addEventListener("click", (e) => {
    if (e.defaultPrevented || blocked(e.target) || html.classList.contains("hall-open")) return;
    const i = scene.pick(e.clientX, e.clientY);
    if (i >= 0 && chapters[i]) hall.openMinistry(chapters[i].id);
  });
  // キーボードで透明ボタンにフォーカスしたときも光らせる
  document.addEventListener("focusin", (e) => {
    const b = e.target.closest && e.target.closest(".emblem-hit");
    const i = b ? Number(b.closest(".chapter").dataset.i) : -1;
    if (b || hover >= 0) { hover = i; scene.setHover(i); }
  });
}

main().catch((e) => {
  const box = $("#chapters");
  if (box) box.innerHTML = Y.empty(e.message);
  html.classList.add("no-webgl");
  if (loader) loader.remove();
});
