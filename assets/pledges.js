/* 有権者 — 公約チェッカー（pledges.html）の組み立てと演出（ES module）
   1. data/pledges.json から「政党の章」（3D の上に重なるカード）・テーマ×党の一覧・公約の詳細を作る
   2. 達成率はここで stage（段階 0〜4）から計算する（データに数値は書かない。式は scorePledges）
   3. 3D はトップと同じ仕組み（scene3d.js）。章＝政党。配色だけ PALETTES で変える（?v=a / b / c、既定 c（Royが11/9に選択））
   4. 公約の詳細は #p=<公約の id> で開くパネル（<dialog>）
   WebGL2 が使えない・動きを減らす設定のときは 3D なし（CSS の夜空と文字のエンブレム）で同じ内容を読める。 */

/* global Y */

/* ── 政党の3Dシンボル（仮）──
   models3d.js の物体のキー。党のシンボルが決まったら、ここだけ差し替える。公式ロゴ・党のマークは使わない。
   となりの章で同じ形にすると変形の途中で輪郭が消えるので、仮の形は党ごとに別にしている。 */
export const PARTY_MODEL = {
  ldp: "diet",
  chudo: "compass",
  ishin: "globe",
  dpfp: "book",
  sanseito: "bridge",
};
const DEFAULT_MODEL = "diet"; // 表にない党（あとで増えた党）

/* ── 段階（仕様書の段階表） ── */
export const STAGES = [
  { name: "動きなし", ruling: "記録なし", opp: "記録なし" },
  { name: "国会で求めた", ruling: "国会答弁・質問で公約を表明・推進した", opp: "国会質問・討論で公約の実現を求めた" },
  { name: "具体案を出した", ruling: "政府・党が具体案を出した（税制改正大綱・法案の閣議決定・予算案）", opp: "法案（議員立法）の提出・具体的な提言や申し入れの文書・予算の修正案" },
  { name: "決定に近づいた", ruling: "法案が国会で審議入り・一院を通過、制度の設計が決まった", opp: "与党・政府との合意文書、政府が検討を表明、法案が審議入り" },
  { name: "実現した", ruling: "法律の成立・予算の成立・制度の開始", opp: "公約と同じ内容が法律・予算・制度として実現（だれの提案でもよい）" },
];
const MAX_STAGE = 4;
const ENGAGED_MIN = 2; // 取り組み度：段階2「具体案を出した」以上に届いた公約の割合（法案提出・提言など、議席数に関係なくどの党でもできること）

/* ── 雰囲気の3案（3D の配色）。トップの濃紺の夜の海と「同じ世界の別の場所」に見える程度にとどめる ──
   中身は scene3d.js の palette（sea3d.js SEA_PALETTE / galaxy3d.js GALAXY_PALETTE / morph3d.js MORPH_PALETTE の一部を差し替え） */
export const PALETTES = {
  a: {
    name: "夜明け前",
    theme: "#05080f",
    palette: {
      clear: 0x05080f,
      sea: { fog: 0x1a1c2c, top: 0x05080f, skyHigh: 0x080b18, glow: 0xffd9a0, stars: 0xe6d3b0, dawn: 0x3a1c0c, dawnH: 0.1, moon: 0xffe9c8 },
      galaxy: {
        starWarm: [1.0, 0.78, 0.48], starViolet: [1.0, 0.86, 0.66], starBase: [0.98, 0.9, 0.74], starJitter: [0.02, 0.06, 0.12],
        nebula: [[0.95, 0.6, 0.38], [1.0, 0.78, 0.45], [0.62, 0.5, 0.82]],
        glowOuter: [0.5, 0.42, 0.62], glowCore: [1.0, 0.82, 0.55], glowAccent: [1.0, 0.62, 0.42],
        nodeAhead: [1.0, 0.9, 0.72], nodeBehind: [1.0, 0.7, 0.4],
      },
      morph: { violet: [1.0, 0.8, 0.6], amber: [1.0, 0.76, 0.44], base: [0.94, 0.9, 0.84], jitter: [0.06, 0.06, 0.1], bandTint: [1.0, 0.88, 0.7], line: 0xffd8a8, surf: 0xffc98a },
    },
  },
  b: {
    name: "紫の星雲",
    theme: "#06050f",
    palette: {
      clear: 0x06050f,
      sea: { fog: 0x160f2c, top: 0x06050f, skyHigh: 0x0a0716, glow: 0xd8c4ff, stars: 0xe4e8f6, moon: 0xeef0ff, dawn: 0x12061c, dawnH: 0.16 },
      galaxy: {
        starWarm: [0.92, 0.94, 1.0], starViolet: [0.86, 0.8, 1.0], starBase: [0.88, 0.92, 1.0], starJitter: [0.1, 0.06, 0],
        nebula: [[0.72, 0.32, 0.95], [0.95, 0.36, 0.72], [0.5, 0.38, 1.0]],
        glowOuter: [0.5, 0.3, 0.88], glowCore: [0.96, 0.84, 1.0], glowAccent: [0.95, 0.4, 0.78], glowGain: 0.17,
        nodeAhead: [0.9, 0.92, 1.0], nodeBehind: [0.92, 0.6, 1.0],
      },
      morph: { violet: [0.86, 0.7, 1.0], amber: [1.0, 0.72, 0.9], base: [0.86, 0.88, 1.0], bandTint: [0.88, 0.8, 1.0], line: 0xd4c0ff, surf: 0xb89cff },
    },
  },
  c: {
    name: "オーロラ",
    theme: "#030a0e",
    palette: {
      clear: 0x030a0e,
      sea: { fog: 0x08202a, top: 0x030a0e, skyHigh: 0x041016, glow: 0x9ff5d8, stars: 0xc8e6e0, moon: 0xd8fff2, dawn: 0x04201c, dawnH: 0.14 },
      galaxy: {
        starWarm: [0.8, 1.0, 0.9], starViolet: [0.7, 0.9, 1.0], starBase: [0.84, 0.94, 0.96], starJitter: [0.1, 0.06, 0.04],
        nebula: [[0.2, 0.85, 0.62], [0.3, 0.75, 0.9], [0.15, 0.95, 0.5]],
        glowOuter: [0.12, 0.62, 0.6], glowCore: [0.62, 1.0, 0.82], glowAccent: [0.2, 0.95, 0.5], glowGain: 0.18, wave: 0.16,
        nodeAhead: [0.78, 1.0, 0.94], nodeBehind: [0.4, 1.0, 0.7],
      },
      morph: { violet: [0.6, 0.95, 1.0], amber: [0.62, 1.0, 0.78], base: [0.82, 0.96, 0.96], jitter: [0.08, 0.04, 0.04], bandTint: [0.7, 1.0, 0.9], line: 0xa8ffe0, surf: 0x7ee8c8 },
    },
  },
};
export const DEFAULT_VARIANT = "c";
export function variantOf(search) {
  const v = new URLSearchParams(search || "").get("v");
  return v && Object.prototype.hasOwnProperty.call(PALETTES, v) ? v : DEFAULT_VARIANT;
}

/* ── 達成率の計算（仕様書の式） ──
   達成率 = 段階の平均 ÷ 4 × 100、取り組み度 = 段階 ENGAGED_MIN 以上の割合、実現度 = 段階 4 の割合（すべて %・四捨五入） */
const stageOf = (p) => Math.max(0, Math.min(MAX_STAGE, Math.round(Number(p && p.stage) || 0)));
export function scorePledges(list) {
  const ps = (list || []).filter(Boolean);
  if (!ps.length) return null;
  const st = ps.map(stageOf);
  const sum = st.reduce((a, b) => a + b, 0);
  return {
    n: ps.length,
    rate: Math.round((sum / ps.length / MAX_STAGE) * 100),
    engaged: Math.round((st.filter((s) => s >= ENGAGED_MIN).length / ps.length) * 100),
    realized: Math.round((st.filter((s) => s >= MAX_STAGE).length / ps.length) * 100),
    stages: st,
  };
}
// 党ごとの集計：{ all, themes: { テーマid: score|null } }
export function partyStats(party, themes) {
  const ps = party.pledges || [];
  const out = { all: scorePledges(ps), themes: {} };
  for (const t of themes) out.themes[t.id] = scorePledges(ps.filter((p) => p.theme === t.id));
  return out;
}

/* ── ここから画面 ── */
const $ = (s, el = document) => el.querySelector(s);
const clamp01 = (v) => Math.max(0, Math.min(1, v));
const pad2 = (n) => String(n).padStart(2, "0");
const esc = (s) => Y.esc(s);
const ext = (url, label) => /^https?:\/\//.test(url || "") ? `<a href="${esc(url)}" target="_blank" rel="noopener">${label}</a>` : label;
const pctOr = (s, key) => (s ? `${s[key]}%` : "—");
const pct = (s) => (s ? `${s.rate}%` : "—");

// 数値の横の棒（色だけで伝えないよう、数値の文字を必ず並べる。棒そのものは読み上げない）
function bar(v) {
  return `<span class="pc-bar" aria-hidden="true"><i style="width:${Math.max(0, Math.min(100, v))}%"></i></span>`;
}

function fmtDay(iso) {
  return /^\d{4}-\d{2}-\d{2}$/.test(iso || "") ? `${Number(iso.slice(0, 4))}年${Y.fmtDate(iso)}` : esc(iso);
}

function sideBadge(p) {
  return `<span class="pc-side" data-side="${p.side === "与党" ? "ruling" : "opp"}">${esc(p.side)}</span>`;
}

/* 党の章（3D の上に重なるカード） */
function chapterHTML(p, i, n, st, themes) {
  const id = esc(p.id);
  const rows = themes.map((t) => {
    const s = st.themes[t.id];
    const first = (p.pledges || []).find((x) => x.theme === t.id);
    const inner = `<span class="pc-tname">${esc(t.name)}</span>${bar(s ? s.rate : 0)}<span class="pc-val">${pct(s)}</span>`;
    return `<li>${first ? `<a href="#p=${encodeURIComponent(first.id)}" aria-label="${esc(p.name)}・${esc(t.name)}：達成率 ${pct(s)}。公約の詳細をひらく">${inner}</a>` : `<span class="pc-row-none">${inner}</span>`}</li>`;
  }).join("");
  const a = st.all;
  return `
  <section class="chapter" id="party-${id}" data-i="${i}" aria-labelledby="party-${id}-title">
    <div class="ch-visual">
      <div class="ch-anchor">
        <div class="emblem-hit" aria-hidden="true"><span class="emblem-fallback"><span>${esc((p.short || p.name).slice(0, 1))}</span></span></div>
      </div>
    </div>
    <div class="ch-text">
      <div class="ch-card pc-card reveal">
        <p class="ch-no"><b>${pad2(i + 1)}</b> / ${pad2(n)}</p>
        <h3 class="ch-name" id="party-${id}-title">${esc(p.name)}</h3>
        <p class="pc-meta">${sideBadge(p)}<span>衆議院 ${esc(p.seats_shugiin)}議席</span>${p.side_note ? `<span class="pc-note">${esc(p.side_note)}</span>` : ""}</p>
        <dl class="pc-scores">
          <div class="pc-score-main"><dt>全体の達成率</dt><dd>${pct(a)}</dd></div>
          <div><dt>取り組み度</dt><dd>${pctOr(a, "engaged")}</dd></div>
          <div><dt>実現度</dt><dd>${pctOr(a, "realized")}</dd></div>
        </dl>
        <p class="pc-count">公約 ${a ? a.n : 0}件をもとに計算</p>
        <ul class="pc-themes" aria-label="テーマごとの達成率">${rows}</ul>
        <p class="pc-man">${p.manifesto ? `公約の出典：${ext(p.manifesto.url, `「${esc(p.manifesto.title)}」 ↗`)}` : ""}</p>
      </div>
    </div>
  </section>`;
}

/* テーマ×党の表（PC）と、党ごとの縦積み（スマホ） */
function cellLink(p, t, s) {
  const first = (p.pledges || []).find((x) => x.theme === t.id);
  if (!first || !s) return `<span class="pc-cell pc-cell-none">公約なし</span>`;
  return `<a class="pc-cell" href="#p=${encodeURIComponent(first.id)}" aria-label="${esc(p.name)}・${esc(t.name)}：達成率 ${s.rate}%、公約${s.n}件。詳細をひらく">
    <span class="pc-pct">${s.rate}%</span>${bar(s.rate)}<span class="pc-n">公約${s.n}件・段階 ${s.stages.join("・")}</span></a>`;
}
function compareHTML(parties, stats, themes) {
  const head = parties.map((p) => `<th scope="col"><span class="pc-th-name">${esc(p.short || p.name)}</span>${sideBadge(p)}</th>`).join("");
  const body = themes.map((t) => `<tr><th scope="row">${esc(t.name)}</th>${parties.map((p) => `<td>${cellLink(p, t, stats[p.id].themes[t.id])}</td>`).join("")}</tr>`).join("");
  const all = parties.map((p) => {
    const a = stats[p.id].all;
    return `<td><span class="pc-total">${pct(a)}</span><span class="pc-sub">取り組み度 ${pctOr(a, "engaged")}<br>実現度 ${pctOr(a, "realized")}</span></td>`;
  }).join("");
  const table = `<div class="pc-table-wrap"><table class="pc-table">
    <caption class="pc-vh">テーマ×党の達成率。セルを押すと、その党・テーマの公約の詳細がひらきます。</caption>
    <thead><tr><th scope="col">テーマ</th>${head}</tr></thead>
    <tbody>${body}</tbody>
    <tfoot><tr><th scope="row">全体</th>${all}</tr></tfoot>
  </table></div>`;
  const stack = parties.map((p) => {
    const st = stats[p.id], a = st.all;
    const rows = themes.map((t) => `<li><span class="pc-stack-t">${esc(t.name)}</span>${cellLink(p, t, st.themes[t.id])}</li>`).join("");
    return `<section class="pc-stack-party" aria-labelledby="stack-${esc(p.id)}">
      <h3 id="stack-${esc(p.id)}">${esc(p.name)} ${sideBadge(p)}</h3>
      <p class="pc-stack-all">全体 <b>${pct(a)}</b> ・取り組み度 ${pctOr(a, "engaged")} ・実現度 ${pctOr(a, "realized")}</p>
      <ul>${rows}</ul></section>`;
  }).join("");
  return table + `<div class="pc-stack">${stack}</div>`;
}

/* 段階のステップ表示（0〜4。今の段階に「現在」の文字をつける＝色だけに頼らない） */
function stepsHTML(stage) {
  const items = STAGES.map((s, k) => {
    const cls = k < stage ? "is-done" : k === stage ? "is-now" : "";
    const mark = k < stage ? "済" : k === stage ? "現在" : "";
    return `<li class="${cls}"${k === stage ? ` aria-current="step"` : ""}><span class="pc-step-n">${k}</span><span class="pc-step-name">${esc(s.name)}</span>${mark ? `<span class="pc-step-mark">${mark}</span>` : ""}</li>`;
  }).join("");
  return `<p class="pc-stage-now">段階 <b>${stage}</b> / ${MAX_STAGE}：${esc(STAGES[stage].name)}</p><ol class="pc-steps" aria-label="段階（0〜4）">${items}</ol>`;
}

function pledgeHTML(pl, selected) {
  const stage = stageOf(pl);
  const src = pl.src || {};
  const acts = (pl.actions || []).slice().sort((a, b) => String(a.date).localeCompare(String(b.date)));
  const timeline = acts.length ? `<ol class="pc-timeline">${acts.map((a) => `
      <li>
        <p class="pc-tl-head"><time datetime="${esc(a.date)}">${fmtDay(a.date)}</time><span class="pc-tl-type">${esc(a.type)}</span>${Number.isFinite(Number(a.stage)) ? `<span class="pc-tl-stage">段階${esc(a.stage)}</span>` : ""}</p>
        <p class="pc-tl-text">${esc(a.text)}</p>
        ${a.src ? `<p class="source">出典：${ext(a.src.url, `「${esc(a.src.title)}」${a.src.site ? `（${esc(a.src.site)}）` : ""} ↗`)}</p>` : ""}
      </li>`).join("")}</ol>` : `<p class="pc-empty">出典つきで確かめられた行動は、まだありません。</p>`;
  return `
    <article class="pc-pledge${selected ? " is-selected" : ""}" id="pl-${esc(pl.id)}">
      <h3 class="pc-pledge-title">${esc(pl.text)}</h3>
      ${pl.quote ? `<blockquote class="pc-quote">「${esc(pl.quote)}」</blockquote>` : ""}
      <p class="source">公約の出典：${ext(src.url, `「${esc(src.title)}」${src.page ? `${esc(src.page)}` : ""} ↗`)}</p>
      ${stepsHTML(stage)}
      ${pl.status ? `<p class="pc-status"><span>今の状況</span>${esc(pl.status)}</p>` : ""}
      <h4 class="pc-tl-title">行動の記録</h4>
      ${timeline}
    </article>`;
}

/* 公約の詳細パネル（#p=<id>） */
function setupDetail(data, onToggle) {
  const dlg = $("#pc-detail"), body = $("#pc-detail-body");
  const byId = {};
  for (const p of data.parties) for (const pl of p.pledges || []) byId[pl.id] = { party: p, pledge: pl };
  const themeName = Object.fromEntries(data.themes.map((t) => [t.id, t.name]));
  let lastFocus = null;

  function idFromHash() {
    const m = /^#p=(.+)$/.exec(location.hash);
    if (!m) return "";
    try { return decodeURIComponent(m[1]); } catch (e) { return m[1]; } // 壊れた URL でもページ全体は止めない
  }
  function open(id) {
    const hit = byId[id];
    if (!hit) { close(); return false; } // 知らない id：前の公約を出したままにしない
    const { party, pledge } = hit;
    const group = party.pledges.filter((x) => x.theme === pledge.theme);
    const s = scorePledges(group);
    body.innerHTML = `
      <p class="pc-d-kicker">${esc(party.name)} ${sideBadge(party)}<span>・</span>${esc(themeName[pledge.theme] || pledge.theme)}</p>
      <h2 class="pc-d-title" id="pc-detail-title">${esc(party.short || party.name)}の「${esc(themeName[pledge.theme] || "")}」の公約</h2>
      <p class="pc-d-score">このテーマの達成率 <b>${pct(s)}</b>（公約${s ? s.n : 0}件の段階の平均 ÷ 4）</p>
      ${data._dummy ? `<p class="pc-dummy-inline">ダミーデータです（実在の公約・行動ではありません）</p>` : ""}
      ${group.map((x) => pledgeHTML(x, x.id === id && group.length > 1)).join("")}`;
    if (!dlg.open) {
      lastFocus = document.activeElement;
      if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
      html.classList.add("pc-detail-open");
      onToggle(true);
    }
    body.scrollTop = 0;
    const target = $(`#pl-${CSS.escape(id)}`, body);
    if (target && group.length > 1 && group[0].id !== id) target.scrollIntoView({ block: "start" });
    $(".pc-close", dlg).focus();
    return true;
  }
  function close() {
    if (dlg.open) { if (dlg.close) dlg.close(); else dlg.removeAttribute("open"); }
  }
  dlg.addEventListener("close", () => {
    html.classList.remove("pc-detail-open");
    onToggle(false);
    if (/^#p=/.test(location.hash)) history.replaceState(null, "", location.pathname + location.search);
    if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true });
  });
  $(".pc-close", dlg).addEventListener("click", close);
  dlg.addEventListener("click", (e) => { if (e.target === dlg) close(); }); // 外側（背景）を押したら閉じる
  const sync = () => { const id = idFromHash(); if (id) open(id); else close(); };
  addEventListener("hashchange", sync);
  sync();
}

/* ── ピンボケから焦点が合って現れる（トップと同じ） ── */
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
    return !!(window.WebGL2RenderingContext && c.getContext("webgl2")); // three r170 は WebGL2 だけに対応
  } catch (e) { return false; }
}

let html;

async function main() {
  html = document.documentElement;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const isMobile = matchMedia("(max-width: 720px)").matches || matchMedia("(pointer: coarse)").matches;
  const v = variantOf(location.search);
  html.dataset.v = v;
  const tc = $('meta[name="theme-color"]');
  if (tc) tc.setAttribute("content", PALETTES[v].theme);

  const data = await Y.load("data/pledges.json");
  const themes = data.themes || [];
  const parties = (data.parties || []).slice().sort((a, b) => (b.seats_shugiin || 0) - (a.seats_shugiin || 0)); // 議席の多い順
  const stats = Object.fromEntries(parties.map((p) => [p.id, partyStats(p, themes)]));

  // 対象の選挙・更新日
  const el = data.election || {};
  $("#pc-election").innerHTML = `対象：${ext(el.url, esc(el.name || ""))}${el.date ? `（${fmtDay(el.date)}投開票）` : ""}${data.updated ? ` ・ 更新 ${fmtDay(data.updated)}` : ""}`;

  // ダミーデータの注意と、配色の試作の切り替え
  if (data._dummy) {
    const box = $("#pc-dummy");
    const links = Object.entries(PALETTES).map(([k, p]) => `<a href="?v=${k}"${k === v ? ` aria-current="true"` : ""}>${k}「${esc(p.name)}」</a>`).join("");
    box.innerHTML = `<p><b>画面の試作用のダミーデータです。</b>実在の政党の公約・行動ではありません（党名・議席数・与党/野党の区分だけ実際のもの）。</p><p class="pc-variants">配色の試作：${links}</p>`;
    box.hidden = false;
  }

  // 党の章
  $("#parties-meta").textContent = `${parties.length}党 · ${themes.length}テーマ · 公約${parties.reduce((n, p) => n + (p.pledges || []).length, 0)}件`;
  const box = $("#chapters");
  box.innerHTML = parties.map((p, i) => chapterHTML(p, i, parties.length, stats[p.id], themes)).join("");
  const chapterEls = [...box.querySelectorAll(".chapter")];

  // 一覧・比較
  $("#compare-body").innerHTML = compareHTML(parties, stats, themes);

  // 達成率の決め方（段階表）
  $("#method-stages").innerHTML = STAGES.map((s, k) => `<tr><th scope="row"><span class="pc-step-n">${k}</span></th><td data-label="名前"><b>${esc(s.name)}</b></td><td data-label="与党の例">${esc(s.ruling)}</td><td data-label="野党の例">${esc(s.opp)}</td></tr>`).join("");

  let scene = null;
  setupDetail(data, (open) => { if (scene) scene.setPaused(open); });
  setupReveal();

  /* スクロール → WebGL の状態（トップ home.js と同じ考え方） */
  const hero = $("#hero"), stream = $("#parties");
  let knots = [], stage = null;
  function measure() {
    const pageY = (e) => e.getBoundingClientRect().top + scrollY;
    const vh = innerHeight;
    const header = $(".site-header");
    const hh = header ? header.offsetHeight : 0;
    const vis = chapterEls[0] && $(".ch-visual", chapterEls[0]);
    const anc = chapterEls[0] && $(".ch-anchor", chapterEls[0]);
    const size = anc ? anc.offsetWidth : Math.min(innerWidth, vh) * 0.5;
    if (isMobile) stage = { x: innerWidth / 2, y: hh + vh * 0.03 + size / 2, size: size * 0.95 };
    else {
      const r = vis ? vis.getBoundingClientRect() : { left: innerWidth / 2, width: innerWidth / 2 };
      stage = { x: r.left + r.width / 2, y: vh / 2 + hh / 2, size: size * 0.95 };
    }
    const k = [[pageY(hero) + hero.offsetHeight / 2 - vh / 2, -1]];
    chapterEls.forEach((ch, i) => {
      if (isMobile) {
        const card = $(".ch-card", ch), top = pageY(card), bottom = top + card.offsetHeight;
        k.push([top - vh * 0.86, i - 0.24]);
        k.push([bottom - stage.y, i + 0.24]);
      } else k.push([pageY(ch) + ch.offsetHeight / 2 - vh / 2, i]);
    });
    const [ly, lf] = k[k.length - 1];
    k.push([ly + vh * 0.8, Math.floor(lf) + 1]);
    for (let j = 1; j < k.length; j++) k[j][0] = Math.max(k[j][0], k[j - 1][0] + 1);
    knots = k;
  }
  function computeState() {
    const vh = innerHeight;
    const hr = hero.getBoundingClientRect();
    const st = { hero: clamp01(hr.bottom / Math.max(1, hr.height)), f: -1, anchor: stage, end: 0 };
    const y = scrollY, k = knots;
    if (k.length > 1) {
      if (y <= k[0][0]) st.f = k[0][1];
      else if (y >= k[k.length - 1][0]) st.f = k[k.length - 1][1];
      else {
        for (let j = 1; j < k.length; j++) {
          if (y <= k[j][0]) { st.f = k[j - 1][1] + (k[j][1] - k[j - 1][1]) * clamp01((y - k[j - 1][0]) / (k[j][0] - k[j - 1][0])); break; }
        }
      }
    }
    st.end = clamp01((vh * 0.5 - stream.getBoundingClientRect().bottom) / vh); // 党の章のあと（表・説明）は 3D を暗くして文字を読みやすく
    return st;
  }
  const onScroll = () => { if (scene) scene.update(computeState()); };
  addEventListener("scroll", onScroll, { passive: true });
  let resizeT = 0;
  const relayout = () => { measure(); onScroll(); };
  addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(relayout, 150); });
  relayout();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(relayout);
  addEventListener("load", relayout);

  /* WebGL（使えない・動きを減らす設定なら 3D なし） */
  if (!reduced && webglAvailable()) {
    try {
      const mod = await import("./scene3d.js");
      scene = mod.createScene({
        canvas: $("#scene"),
        chapters: parties.map((p) => ({ id: p.id, name: p.name, model: PARTY_MODEL[p.id] || DEFAULT_MODEL })),
        dprMax: isMobile ? 1.5 : 1.75,
        isMobile,
        palette: PALETTES[v].palette,
      });
      html.classList.add("webgl");
      html.classList.remove("no-webgl");
      relayout();
      if (html.classList.contains("pc-detail-open")) scene.setPaused(true);
    } catch (e) {
      scene = null;
      html.classList.add("no-webgl");
    }
  } else {
    html.classList.add("no-webgl");
  }
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
  main().catch((e) => {
    const box = document.querySelector("#chapters");
    if (box) box.innerHTML = Y.empty(e.message);
    document.documentElement.classList.add("no-webgl");
  });
}
