/* 有権者 — 地方ページ（local.html）の組み立て（ES module）
   1. data/prefectures.json（47都道府県）・data/prefmap.json（地図の形）・data/local_news.json（公開済みの地方の記事）を読む
      ?sample=1 のときだけ drafts/local_sample.json の見本の記事も足す（drafts/ は git に入らないので、公開サイトには出ない）
   2. 3D の日本地図（map3d.js）。WebGL2 が使えない・three の読み込みに失敗したときは SVG の平らな地図
   3. 県を選ぶと local.html?p=<県id>：地図がその県へ寄り、横（スマホは下）にその県の記事が新しい順に並ぶ
   4. 記事を押すと、国の記事と同じリーダー（hall.js、#a=<記事id>）で開く
   5. 下に 47都道府県の一覧（地方ごと。キーボード・読み上げ・WebGL なしでも使える） */

/* global Y */
import { initHall } from "./hall.js";
import { decodeMap, hitTest } from "./prefmap.js";

const html = document.documentElement;
const params = new URLSearchParams(location.search);
const SAMPLE = params.get("sample") === "1";
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const isMobile = matchMedia("(max-width: 720px)").matches || matchMedia("(pointer: coarse)").matches;
const REGIONS = ["北海道・東北", "関東", "中部", "近畿", "中国", "四国", "九州・沖縄"];
const BASE_TITLE = document.title;
const $ = (s, el = document) => el.querySelector(s);
const pageUrl = (id) => "local.html" + (id || SAMPLE ? "?" : "") + [id ? "p=" + encodeURIComponent(id) : "", SAMPLE ? "sample=1" : ""].filter(Boolean).join("&");

function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGL2RenderingContext && c.getContext("webgl2")); // three r170 は WebGL2 だけに対応
  } catch (e) { return false; }
}

async function main() {
  const [prefs, rawMap, srcList, published] = await Promise.all([
    Y.load("data/prefectures.json"),
    Y.load("data/prefmap.json"),
    Y.load("data/pref_sources.json").catch(() => []),
    Y.load("data/local_news.json").catch(() => []),
  ]);
  const prefMap = Object.fromEntries(prefs.map((p) => [p.id, p]));
  const homeOf = Object.fromEntries(srcList.map((s) => [s.id, s.home]));
  const ok = (n) => n && n.id && n.date && n.title && prefMap[n.pref];
  let items = (Array.isArray(published) ? published : []).filter(ok);
  if (SAMPLE) {
    const sample = await Y.load("drafts/local_sample.json").catch(() => []);
    items = items.concat((Array.isArray(sample) ? sample : []).filter(ok));
    $("#lm-sample").hidden = false;
  }
  items.sort(Y.byDateDesc);
  const has = (n, id) => n.pref === id || (n.pref_also || []).includes(id);
  const itemsOf = (id) => items.filter((n) => has(n, id));
  const count = Object.fromEntries(prefs.map((p) => [p.id, itemsOf(p.id).length]));
  const total = items.length;

  /* ── 記事のリーダー（国の記事と同じ hall.js） ── */
  let map = null, current = undefined, svg = null;
  const hall = initHall({
    sources: prefs, news: items, srcMap: prefMap,
    group: { key: "pref", also: "pref_also", label: "地方", number: (id) => Number(prefMap[id]?.code) || 0, listHref: pageUrl, current: () => current },
    onToggle: (open) => { if (map) map.setPaused(open); },
  });

  /* ── 一覧（地方ごと） ── */
  $("#lm-regions").innerHTML = REGIONS.map((r) => {
    const ps = prefs.filter((p) => p.region === r);
    return `<div class="lm-region"><h3>${Y.esc(r)}</h3><ul>${ps.map((p) => `
      <li><a href="${Y.esc(pageUrl(p.id))}" data-p="${Y.esc(p.id)}" class="${count[p.id] ? "has" : ""}">${Y.esc(p.name)}<span class="lm-n">${count[p.id] ? count[p.id] : ""}</span><span class="vh">（記事${count[p.id]}件）</span></a></li>`).join("")}</ul></div>`;
  }).join("");
  $("#lm-total").textContent = total ? `記事 ${total}件 · ${prefs.filter((p) => count[p.id]).length}の都道府県` : "記事はまだありません";

  /* ── 選んだ県のパネル ── */
  const panel = $("#lm-panel"), live = $("#lm-live");
  function cardHTML(it) {
    return `<li><a class="lm-card" href="#a=${encodeURIComponent(it.id)}">
      <time datetime="${Y.esc(it.date)}">${Y.fmtDate(it.date)}</time>
      <span class="lm-card-title">${Y.esc(it.title)}</span>
      <span class="lm-card-sum">${Y.esc(it.summary)}</span>
    </a></li>`;
  }
  function renderPanel(id) {
    if (!id) {
      const top = prefs.filter((p) => count[p.id]).sort((a, b) => count[b.id] - count[a.id]);
      panel.innerHTML = `
        <p class="lm-p-kicker">47都道府県</p>
        <h2 class="lm-p-name" id="lm-p-name" tabindex="-1">都道府県を選んでください</h2>
        <p class="lm-p-lead">地図の県を押すか、下の一覧から選べます。光っている県に記事があります。</p>
        ${top.length ? `<ul class="lm-chips">${top.map((p) => `<li><a href="${Y.esc(pageUrl(p.id))}" data-p="${Y.esc(p.id)}">${Y.esc(p.name)}<span class="lm-n">${count[p.id]}</span></a></li>`).join("")}</ul>`
          : `<p class="lm-empty">まだ記事がありません。これから少しずつ増やします。</p>`}`;
      return;
    }
    const p = prefMap[id], list = itemsOf(id), home = homeOf[id];
    panel.innerHTML = `
      <p class="lm-p-kicker">${Y.esc(p.region)} · Nº ${Y.esc(p.code)}</p>
      <h2 class="lm-p-name" id="lm-p-name" tabindex="-1">${Y.esc(p.name)}</h2>
      <p class="lm-p-count">${list.length ? `記事 ${list.length}件 · 新しい順` : ""}</p>
      ${list.length ? `<ol class="lm-cards">${list.map(cardHTML).join("")}</ol>` : `<p class="lm-empty">まだ記事がありません</p>`}
      <p class="lm-p-foot">
        ${home ? `<a href="${Y.esc(home)}" target="_blank" rel="noopener">${Y.esc(p.name)}の公式ホームページ <span aria-hidden="true">↗</span></a>` : ""}
        <a href="${Y.esc(pageUrl(null))}" data-p="">全国の地図に戻る</a>
      </p>`;
  }

  /* ── 県を選ぶ（URL・地図・パネル・一覧をそろえる） ── */
  function select(id, { push = false, instant = false, focus = false } = {}) {
    id = id && prefMap[id] ? id : null;
    if (id === current) {
      if (focus) $("#lm-p-name")?.focus({ preventScroll: true });
      return;
    }
    if (push) history.pushState({ lp: id }, "", pageUrl(id));
    current = id;
    renderPanel(id);
    document.querySelectorAll("#lm-regions a[data-p]").forEach((a) => a.toggleAttribute("aria-current", a.dataset.p === id));
    if (map) map.select(id, instant);
    if (svg) svg.select(id);
    const p = id && prefMap[id];
    document.title = p ? `${p.name}のニュース — 有権者 地方` : BASE_TITLE;
    const canon = $('link[rel="canonical"]');
    if (canon) canon.href = "https://yossy8080.github.io/yukensha/" + (id ? "local.html?p=" + id : "local.html");
    html.classList.toggle("lm-has-sel", !!id);
    if (p) live.textContent = `${p.name}：${count[id] ? `記事${count[id]}件` : "まだ記事がありません"}`;
    if (focus) $("#lm-p-name")?.focus({ preventScroll: true });
  }
  function pick(id, fromList) {
    select(id, { push: true, focus: fromList });
    // スマホ・一覧から選んだときは、記事の並ぶところまで動かす（スマホで地図から選んだときは、地図が県へ寄るのを見せてから）
    if (fromList || isMobile) {
      const target = isMobile ? panel : $("#lm-main");
      setTimeout(() => {
        const r = target.getBoundingClientRect();
        if (r.top < 0 || r.top > innerHeight * 0.75) target.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
      }, !fromList && !reduced ? 700 : 0);
    }
  }

  document.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest && e.target.closest("a[data-p]");
    if (a) {
      e.preventDefault();
      pick(a.dataset.p || null, !!a.closest("#lm-regions, #lm-panel"));
      return;
    }
    // リーダーの下の「〇〇の記事一覧」：いま選んでいる県なら、リーダーを閉じるだけ
    const rl = e.target.closest && e.target.closest(".hall-rlist");
    if (rl && rl.href === new URL(pageUrl(current), location.href).href) {
      e.preventDefault();
      hall.close();
    }
  });
  addEventListener("popstate", () => {
    if (location.hash) return; // 記事のリーダーの履歴（hall.js が扱う）
    select(new URLSearchParams(location.search).get("p"), {});
  });

  const first = params.get("p");
  select(first, { instant: true });
  if (first && !prefMap[first]) history.replaceState(history.state, "", pageUrl(null) + location.hash);

  /* ── 地図 ── */
  const dec = decodeMap(rawMap);
  const mapPrefs = prefs.map((p) => ({ id: p.id, name: p.name, count: count[p.id] }));
  const stage = $("#lm-stage");
  let usedGL = false;
  if (webglAvailable()) {
    try {
      const mod = await import("./map3d.js");
      map = mod.createMap({
        canvas: $("#lm-canvas"), overlay: $("#lm-overlay"), dec, prefs: mapPrefs, isMobile, reduced,
        onPick: (id) => pick(id, false),
      });
      usedGL = true;
      if (current) map.select(current, true);
    } catch (e) {
      map = null;
    }
  }
  if (!usedGL) {
    svg = buildSvg(dec, mapPrefs, (id) => pick(id, false));
    svg.select(current);
  }
  stage.classList.add(usedGL ? "is-gl" : "is-svg");
  stage.classList.remove("is-loading");
}

/* WebGL が使えないときの平らな地図（SVG）。読み上げには一覧を使ってもらうので、地図そのものは aria-hidden */
function buildSvg(dec, prefs, onPick) {
  const host = $("#lm-svg");
  const b = dec.box, pad = 0.2;
  const ring = (r) => {
    let d = "";
    for (let i = 0; i < r.length; i += 2) d += (i ? "L" : "M") + r[i].toFixed(2) + " " + (-r[i + 1]).toFixed(2);
    return d + "Z";
  };
  const ib = dec.inset.box;
  host.innerHTML = `<svg viewBox="${(b[0] - pad).toFixed(2)} ${(-b[3] - pad).toFixed(2)} ${(b[2] - b[0] + pad * 2).toFixed(2)} ${(b[3] - b[1] + pad * 2).toFixed(2)}" aria-hidden="true" focusable="false">
    <rect class="lm-svg-inset" x="${ib[0]}" y="${-ib[3]}" width="${ib[2] - ib[0]}" height="${ib[3] - ib[1]}"/>
    ${prefs.map((p) => `<path data-p="${p.id}" class="${p.count ? "has" : ""}" d="${dec.prefs[p.id].polys.map((poly) => poly.map(ring).join("")).join("")}"><title>${Y.esc(p.name)}（${p.count ? `記事${p.count}件` : "まだ記事がありません"}）</title></path>`).join("")}
  </svg>`;
  const el = host.firstElementChild;
  el.addEventListener("click", (e) => {
    let id = e.target.closest("path")?.dataset.p;
    if (!id) {
      // 小さい県・島は、近くを押しても選べるように
      const pt = el.createSVGPoint();
      pt.x = e.clientX; pt.y = e.clientY;
      const q = pt.matrixTransform(el.getScreenCTM().inverse());
      const perPx = (b[2] - b[0]) / el.getBoundingClientRect().width;
      id = hitTest(dec, q.x, -q.y, 20 * perPx);
    }
    if (id) onPick(id);
  });
  return {
    select(id) { el.querySelectorAll("path").forEach((p) => p.classList.toggle("is-sel", p.dataset.p === id)); },
  };
}

main().catch((e) => {
  const panel = $("#lm-panel");
  if (panel) panel.innerHTML = Y.empty(e.message);
  $("#lm-stage")?.classList.remove("is-loading");
});
