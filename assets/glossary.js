/* 有権者 — 用語ポップアップ（辞書のポップアップのように、難しい用語の簡単な意味を出す）
   データ: data/glossary.json [{term, aliases[], yomi, short, src_name, src_url}]（src_* は官邸・各府省・JAXA などの公式ページ。それ以外の項目は見ない）
   使い方: YG.apply(要素) … 要素の中の各 <article>（無ければ要素全体）ごとに、各用語の最初の1回を
           <button class="term"> で包む。何度呼んでも二重には包まない。
   API: window.YG = { load(url) -> Promise<entries>, apply(root) -> Promise, close() } */

(() => {
  if (window.YG) return;

  // 用語を探さない場所（リンク・見出し・日付・タグなど）
  const SKIP = "a, h1, h2, h3, h4, h5, h6, button, .term, script, style, time, .tags, .tag, .kicker, figcaption, [data-no-gloss], .gl-pop";
  const ASCII = /^[\x21-\x7e]+$/;
  const isWordChar = (c) => /[A-Za-z0-9]/.test(c || "");

  let loading = null;
  let byKey = {};          // 表記（term と aliases）→ エントリ
  let re = null;           // 全表記をまとめた正規表現（長い語が先）

  function load(url = "data/glossary.json") {
    if (loading) return loading;
    loading = fetch(url)
      .then((r) => (r.ok ? r.json() : []))
      .catch(() => [])
      .then((list) => {
        list = Array.isArray(list) ? list : [];
        byKey = {};
        for (const e of list) for (const k of [e.term, ...(e.aliases || [])]) if (k) byKey[k] = e;
        const keys = Object.keys(byKey).sort((a, b) => b.length - a.length);
        re = keys.length ? new RegExp(keys.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "g") : null;
        return list;
      });
    return loading;
  }

  function scopesOf(root) {
    if (root.matches("article")) return [root];
    const arts = root.querySelectorAll("article");
    return arts.length ? [...arts] : [root];
  }

  function makeTerm(entry, text) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "term";
    b.dataset.term = entry.term;
    b.setAttribute("aria-expanded", "false");
    b.setAttribute("aria-haspopup", "dialog");
    b.textContent = text;
    return b;
  }

  function applyScope(scope) {
    const used = new Set([...scope.querySelectorAll(".term")].map((b) => b.dataset.term));
    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, {
      acceptNode(n) {
        const p = n.parentElement;
        return n.nodeValue.trim() && p && !p.closest(SKIP) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    for (const node of nodes) {
      const text = node.nodeValue;
      let frag = null, last = 0, m;
      re.lastIndex = 0;
      while ((m = re.exec(text))) {
        const key = m[0], entry = byKey[key];
        // 英字略語は前後が英数字でないときだけ（例: "GDP"）
        if (ASCII.test(key) && (isWordChar(text[m.index - 1]) || isWordChar(text[m.index + key.length]))) {
          re.lastIndex = m.index + 1;
          continue;
        }
        if (used.has(entry.term)) continue;
        used.add(entry.term);
        frag = frag || document.createDocumentFragment();
        frag.append(text.slice(last, m.index), makeTerm(entry, key));
        last = m.index + key.length;
      }
      if (frag) {
        frag.append(text.slice(last));
        node.replaceWith(frag);
      }
    }
  }

  async function apply(root) {
    if (!root) return;
    await load();
    if (!re) return;
    for (const s of scopesOf(root)) applyScope(s);
  }

  /* ── ポップアップ ── */
  let pop = null, current = null, openedByKey = false;

  function ensurePop() {
    if (pop) return pop;
    pop = document.createElement("div");
    pop.className = "gl-pop";
    pop.id = "gl-pop";
    pop.hidden = true;
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-modal", "false");
    pop.setAttribute("aria-labelledby", "gl-pop-term");
    pop.innerHTML = `
      <span class="gl-grip" aria-hidden="true"></span>
      <p class="gl-head"><strong id="gl-pop-term" class="gl-term"></strong><span class="gl-yomi"></span></p>
      <p id="gl-pop-desc" class="gl-desc"></p>
      <p class="gl-src"><a target="_blank" rel="noopener">くわしく：<span class="gl-src-name"></span> <span aria-hidden="true">↗</span></a></p>
      <p class="gl-note">有権者編集部による簡単な説明</p>
      <button type="button" class="gl-close" aria-label="閉じる">×</button>`;
    pop.querySelector(".gl-close").addEventListener("click", () => close(true));
    pop.addEventListener("focusout", (e) => {
      const to = e.relatedTarget;
      if (to && !pop.contains(to) && to !== current) close(false);
    });
    return pop;
  }

  const isSheet = () => window.innerWidth <= 600;

  function position(btn) {
    pop.classList.toggle("is-sheet", isSheet());
    pop.style.left = pop.style.top = "";
    if (isSheet()) return;
    const rect = btn.getClientRects()[0] || btn.getBoundingClientRect();
    const w = pop.offsetWidth, h = pop.offsetHeight, m = 12, gap = 10;
    let top = rect.bottom + gap, below = true;
    if (top + h > innerHeight - m && rect.top - gap - h >= m) { top = rect.top - gap - h; below = false; }
    top = Math.max(m, Math.min(top, innerHeight - h - m));
    const left = Math.max(m, Math.min(rect.left + rect.width / 2 - w / 2, innerWidth - w - m));
    pop.style.left = left + "px";
    pop.style.top = top + "px";
    pop.style.setProperty("--arrow-x", Math.max(16, Math.min(rect.left + rect.width / 2 - left, w - 16)) + "px");
    pop.classList.toggle("is-above", !below);
  }

  async function open(btn, byKeyboard) {
    await load();
    const entry = byKey[btn.dataset.term];
    if (!entry) return;
    if (current && current !== btn) close(false);
    ensurePop();
    // 記事ビュー（モーダル）の中ならその中に置く（フォーカストラップの内側で操作できるように）
    const host = btn.closest('[role="dialog"]:not(.gl-pop)') || document.body;
    if (pop.parentNode !== host) host.appendChild(pop);
    pop.querySelector(".gl-term").textContent = entry.term;
    pop.querySelector(".gl-yomi").textContent = entry.yomi ? `（${entry.yomi}）` : "";
    pop.querySelector(".gl-desc").textContent = entry.short;
    const src = pop.querySelector(".gl-src"), srcUrl = entry.src_url || "";
    src.hidden = !srcUrl;
    if (srcUrl) {
      src.querySelector("a").href = srcUrl;
      src.querySelector(".gl-src-name").textContent = entry.src_name || "公式ページ";
    }
    pop.hidden = false;
    position(btn);
    current = btn;
    openedByKey = byKeyboard;
    btn.setAttribute("aria-expanded", "true");
    btn.setAttribute("aria-controls", "gl-pop");
    btn.setAttribute("aria-describedby", "gl-pop-desc");
    if (byKeyboard) pop.querySelector(srcUrl ? ".gl-src a" : ".gl-close").focus();
  }

  function close(returnFocus) {
    if (!pop || pop.hidden) return;
    pop.hidden = true;
    const btn = current;
    current = null;
    if (btn) {
      btn.setAttribute("aria-expanded", "false");
      btn.removeAttribute("aria-describedby");
      if (returnFocus && (openedByKey || pop.contains(document.activeElement))) btn.focus();
    }
  }

  // capture で拾う：カードの「記事をひらく」などより先に処理するため
  document.addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest(".term");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    if (current === btn) close(e.detail === 0);
    else open(btn, e.detail === 0);
  }, true);

  // 用語のボタンの上でドラッグを始めても、記事ビューの回転などは邪魔しない（pointerdown は止めない）
  document.addEventListener("pointerdown", (e) => {
    if (!current || pop.contains(e.target) || current.contains(e.target)) return;
    close(false);
  }, true);

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !pop || pop.hidden) return;
    e.preventDefault();
    e.stopPropagation();
    close(true);
  }, true);

  document.addEventListener("scroll", (e) => {
    if (current && !isSheet() && !(pop.contains(e.target))) close(false);
  }, true);
  window.addEventListener("resize", () => close(false));

  window.YG = { load, apply, close: () => close(false) };
})();
