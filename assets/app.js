/* 有権者 — 共通スクリプト
   データ: data/sources.json（府省の一覧）, data/news.json（公開済みの記事）
   記事の形: {id, date, ministry, also[], featured, tags[], title, summary, points[], source_url, source_title, site} */

const Y = (() => {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function load(path) {
    const r = await fetch(path, { cache: "no-store" });
    if (!r.ok) throw new Error(path + " を読み込めませんでした");
    return r.json();
  }

  function fmtDate(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    const w = "日月火水木金土"[new Date(y, m - 1, d).getDay()];
    return `${m}月${d}日（${w}）`;
  }

  function byDateDesc(a, b) {
    return b.date.localeCompare(a.date) || (b.featured === true) - (a.featured === true);
  }

  function sourceLine(it) {
    return `<p class="source">出典：<a href="${esc(it.source_url)}" target="_blank" rel="noopener">「${esc(it.source_title)}」（${esc(it.site)}）</a>をもとに有権者が要約して作成</p>`;
  }

  function ministryLabel(it, srcMap) {
    const ids = [it.ministry, ...(it.also || [])];
    return ids.map((id) => {
      const s = srcMap[id];
      return s ? `<a class="kicker-ministry" href="ministries.html?m=${esc(id)}">${esc(s.name)}</a>` : "";
    }).join("<span class='sep'>・</span>");
  }

  // 発言の引用（総理・官房長官の発言）
  function quotes(it) {
    if (!(it.quotes || []).length) return "";
    const who = [it.speaker, it.scene].filter(Boolean).map(esc).join("・");
    return `<figure class="quotes">${it.quotes.map((q) => `<blockquote>「${esc(q)}」</blockquote>`).join("")}${who ? `<figcaption>— ${who}</figcaption>` : ""}</figure>`;
  }

  // 1件の記事（大きい表示）
  function article(it, srcMap) {
    const pts = (it.points || []).map((p) => `<li>${esc(p)}</li>`).join("");
    const tags = (it.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("");
    return `
      <article class="item" id="${esc(it.id)}">
        <p class="kicker"><time datetime="${esc(it.date)}">${fmtDate(it.date)}</time>${ministryLabel(it, srcMap)}</p>
        <h3 class="headline">${esc(it.title)}</h3>
        <p class="summary">${esc(it.summary)}</p>
        ${quotes(it)}
        ${pts ? `<ul class="points">${pts}</ul>` : ""}
        ${sourceLine(it)}
        ${tags ? `<p class="tags">${tags}</p>` : ""}
      </article>`;
  }

  // 1行の記事（一覧用）
  function row(it, srcMap) {
    return `
      <li class="row">
        <time datetime="${esc(it.date)}">${fmtDate(it.date)}</time>
        <span class="row-ministry">${esc(srcMap[it.ministry]?.short || "")}</span>
        <a href="ministries.html?m=${esc(it.ministry)}#${esc(it.id)}">${esc(it.title)}</a>
      </li>`;
  }

  function empty(msg) {
    return `<p class="empty">${esc(msg)}</p>`;
  }

  function markNav() {
    const page = location.pathname.split("/").pop() || "index.html";
    document.querySelectorAll(".nav a").forEach((a) => {
      if (a.getAttribute("href") === page) a.setAttribute("aria-current", "page");
    });
    const today = new Date();
    const el = document.querySelector("[data-today]");
    if (el) el.textContent = `${today.getFullYear()}年${today.getMonth() + 1}月${today.getDate()}日`;
  }

  const visible = (sources) => sources.filter((s) => !s.hidden);

  // オピニオン（今週の論点など）
  function opinion(p, byId, srcMap) {
    const topics = (p.topics || []).map((t, i) => {
      const rel = (t.article_ids || []).map((id) => byId[id]).filter(Boolean)
        .map((n) => `<li><time>${fmtDate(n.date)}</time> <a href="ministries.html?m=${esc(n.ministry)}#${esc(n.id)}">${esc(n.title)}</a> <span class="row-ministry">${esc(srcMap[n.ministry]?.short || "")}</span></li>`).join("");
      return `<section class="topic"><h4><span class="topic-n">${i + 1}</span>${esc(t.name)}${t.count ? `<small>関連の発表 ${esc(t.count)}件</small>` : ""}</h4>
        <p>${esc(t.summary || "")}</p>${rel ? `<ul class="topic-rel">${rel}</ul>` : ""}</section>`;
    }).join("");
    const body = (p.body || []).map((x) => `<p>${esc(x)}</p>`).join("");
    return `<article class="item opinion" id="${esc(p.id)}">
      <p class="kicker"><span class="kicker-ministry">${esc(p.kind || "オピニオン")}</span><time datetime="${esc(p.date)}">${fmtDate(p.date)}</time>${p.period ? `<span>対象：${esc(p.period)}</span>` : ""}</p>
      <h3 class="headline">${esc(p.title)}</h3>
      ${p.lead ? `<p class="summary">${esc(p.lead)}</p>` : ""}
      ${topics}
      ${body ? `<div class="op-body"><h4>編集部メモ</h4>${body}</div>` : ""}
      <p class="source">${esc(p.author || "有権者編集部")}</p>
    </article>`;
  }

  return { esc, load, fmtDate, byDateDesc, article, row, empty, markNav, quotes, visible, opinion };
})();

document.addEventListener("DOMContentLoaded", Y.markNav);
