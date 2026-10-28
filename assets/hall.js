/* 有権者 — 記事ビュー「Mirror Hall」とリーダー表示（ES module）
   府省の記事を、暗い水面の上の光るカードのリング（CSS 3D）で見せる。正面のカードを開くと読みやすいリーダーになる。
   API: initHall({ sources, news, srcMap, order, onToggle }) -> { openMinistry(id), openArticle(id), close() }
   URL: index.html#m=<府省id> でその府省、#a=<記事id> でその記事を直接開く（戻るボタンで閉じる）。 */

/* global Y */

const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
const pad2 = (n) => String(n).padStart(2, "0");
const mod = (a, n) => ((a % n) + n) % n;

export function initHall({ sources, news, srcMap, order = [], onToggle = () => {} }) {
  const sorted = [...news].sort(Y.byDateDesc);
  const byId = Object.fromEntries(sorted.map((n) => [n.id, n]));
  const has = (n, id) => n.ministry === id || (n.also || []).includes(id);
  const visibleIds = Y.visible(sources).map((s) => s.id);
  const numberOf = (id) => {
    const i = order.indexOf(id);
    return i >= 0 ? i + 1 : order.length + Math.max(0, visibleIds.filter((x) => !order.includes(x)).indexOf(id)) + 1;
  };

  /* ── DOM（初回だけ作る） ── */
  const root = document.createElement("div");
  root.className = "hall";
  root.id = "hall";
  root.hidden = true;
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-modal", "true");
  root.setAttribute("aria-labelledby", "hall-title");
  root.innerHTML = `
    <svg class="hall-defs" width="0" height="0" aria-hidden="true" focusable="false">
      <filter id="hall-ripple" x="-5%" y="-5%" width="110%" height="110%">
        <feTurbulence type="fractalNoise" baseFrequency="0.004 0.05" numOctaves="2" seed="3" result="n">
          <animate attributeName="baseFrequency" dur="14s" values="0.004 0.05;0.006 0.07;0.004 0.05" repeatCount="indefinite"/>
        </feTurbulence>
        <feDisplacementMap in="SourceGraphic" in2="n" scale="14" xChannelSelector="R" yChannelSelector="G"/>
      </filter>
    </svg>
    <div class="hall-sky" aria-hidden="true"></div>
    <header class="hall-top">
      <p class="hall-kicker">有権者 · 府省 Nº <span class="hall-no"></span></p>
      <h2 class="hall-title" id="hall-title" tabindex="-1"></h2>
      <p class="hall-count"></p>
    </header>
    <button type="button" class="hall-close" aria-label="閉じる"><span aria-hidden="true">×</span></button>
    <div class="hall-stage">
      <div class="hall-ring"></div>
      <div class="hall-water" aria-hidden="true"><div class="hall-reflect"></div></div>
    </div>
    <p class="hall-empty" hidden>まだ記事はありません。</p>
    <footer class="hall-foot">
      <button type="button" class="hall-nav hall-prev" aria-label="前のカード"><span aria-hidden="true">←</span></button>
      <p class="hall-counter" aria-hidden="true"><b class="hall-cur">01</b> / <span class="hall-total">01</span></p>
      <button type="button" class="hall-nav hall-next" aria-label="次のカード"><span aria-hidden="true">→</span></button>
      <div class="hall-dots"></div>
      <p class="hall-hint" aria-hidden="true">ドラッグで回転 · 正面のカードで記事をひらく</p>
    </footer>
    <p class="hall-live" aria-live="polite"></p>
    <section class="hall-reader" hidden aria-label="記事">
      <div class="hall-reader-bar">
        <button type="button" class="hall-back">← 一覧へ戻る</button>
        <span class="hall-reader-pos"></span>
        <div class="hall-reader-tools">
          <button type="button" class="hall-copy" aria-label="この記事へのリンクをコピー">リンクをコピー</button>
          <button type="button" class="hall-close hall-reader-close" aria-label="閉じる"><span aria-hidden="true">×</span></button>
        </div>
      </div>
      <div class="hall-reader-body"></div>
      <!-- 画面の下に固定。前・次がないときはそのボタンを隠し、府省の記事一覧はいつも真ん中 -->
      <nav class="hall-reader-nav" aria-label="記事の移動">
        <button type="button" class="hall-rprev" aria-label="前の記事"><span aria-hidden="true">← 前<span class="hall-rlong">の記事</span></span></button>
        <a class="hall-rlist" href="ministries.html"></a>
        <button type="button" class="hall-rnext" aria-label="次の記事"><span aria-hidden="true">次<span class="hall-rlong">の記事</span> →</span></button>
      </nav>
    </section>`;
  document.body.appendChild(root);
  const $ = (s) => root.querySelector(s);
  const stage = $(".hall-stage"), ring = $(".hall-ring"), reflect = $(".hall-reflect");
  const reader = $(".hall-reader"), readerBody = $(".hall-reader-body");
  const live = $(".hall-live");
  if (reduceMotion.matches || matchMedia("(max-width: 600px)").matches) $("animate")?.remove();

  /* ── 状態 ── */
  let ministry = null, list = [], cards = [], mirrors = [];
  let pos = 0, target = 0, step = 34, radius = 800, wrap = false, cardW = 560;
  let front = -1, readerIdx = -1, isOpen = false, lastFocus = null, inerted = [];
  let raf = 0, lastT = 0;

  function layoutParams() {
    const n = list.length;
    cardW = cards[0] ? cards[0].offsetWidth || 560 : 560;
    const gap = cardW * 0.08;
    if (n >= 6 && n <= 10) {
      // 6〜10枚：一周のリング
      wrap = true;
      step = 360 / n;
      radius = (cardW + gap) / (2 * Math.tan(Math.PI / n));
    } else {
      // 少ない・多いとき：角度を固定した弧（多いときは正面から遠いカードを隠す＝終わりのないリングのように回る）
      // （40° と 1.7 倍なら、隣のカードの縁が正面のカードより奥・外側に来て重ならない）
      wrap = false;
      step = 40;
      radius = cardW * 1.7;
    }
  }

  function relOf(j) {
    let rel = j - pos;
    if (wrap) rel = mod(rel + list.length / 2, list.length) - list.length / 2;
    return rel;
  }

  function render() {
    const n = list.length;
    for (let j = 0; j < n; j++) {
      const rel = relOf(j);
      const ang = rel * step;
      const hide = Math.abs(ang) > 105 || (!wrap && Math.abs(rel) > 4.5);
      const f = Math.max(0, Math.cos((ang * Math.PI) / 180));
      const tf = `translate(-50%, -50%) translateZ(${-radius}px) rotateY(${ang}deg) translateZ(${radius}px)`;
      for (const el of [cards[j], mirrors[j]]) {
        if (!el) continue;
        el.style.transform = tf;
        el.style.visibility = hide ? "hidden" : "visible";
        el.style.setProperty("--f", f.toFixed(3));
        el.style.zIndex = String(Math.round(f * 100));
      }
    }
    const fi = n ? mod(Math.round(target), n) : -1;
    if (fi !== front) setFront(fi);
  }

  function setFront(fi) {
    front = fi;
    cards.forEach((c, j) => {
      const on = j === fi;
      c.classList.toggle("is-front", on);
      c.setAttribute("aria-hidden", on ? "false" : "true");
      c.querySelectorAll("button, a").forEach((b) => (on ? b.removeAttribute("tabindex") : b.setAttribute("tabindex", "-1")));
    });
    mirrors.forEach((c, j) => c.classList.toggle("is-front", j === fi));
    const n = list.length;
    $(".hall-cur").textContent = pad2(fi + 1);
    $(".hall-total").textContent = pad2(n);
    root.querySelectorAll(".hall-dot").forEach((d, j) => d.setAttribute("aria-current", j === fi ? "true" : "false"));
    $(".hall-prev").disabled = !wrap && fi <= 0;
    $(".hall-next").disabled = !wrap && fi >= n - 1;
    if (isOpen && fi >= 0) live.textContent = `${fi + 1}件目／${n}件：${list[fi].title}`;
  }

  function tick(t) {
    raf = 0;
    const dt = Math.min((t - (lastT || t)) / 1000, 0.05);
    lastT = t;
    if (!dragging) {
      if (reduceMotion.matches) pos = target;
      else pos += (target - pos) * (1 - Math.exp(-dt * 9));
      if (Math.abs(target - pos) < 0.0005) pos = target;
    }
    render();
    if (isOpen && (dragging || pos !== target)) raf = requestAnimationFrame(tick);
  }
  function kick() {
    if (!raf && isOpen) { lastT = 0; raf = requestAnimationFrame(tick); }
  }

  function go(k) {
    const n = list.length;
    if (!n) return;
    target = Math.round(target) + k;
    if (!wrap) target = Math.max(0, Math.min(n - 1, target));
    kick();
  }
  function goTo(j) {
    const n = list.length;
    if (!n) return;
    if (wrap) target = Math.round(target) + (mod(j - Math.round(target) + n / 2, n) - n / 2);
    else target = j;
    kick();
  }

  /* ── カードを並べる ── */
  function cardHTML(it, j) {
    const tags = (it.tags || []).slice(0, 3).map((t) => `<span class="hall-tag">${Y.esc(t)}</span>`).join("");
    return `<article class="hall-card" data-i="${j}">
      <div class="hall-card-in">
        <p class="hall-card-meta"><time datetime="${Y.esc(it.date)}">${Y.fmtDate(it.date)}</time>${tags}</p>
        <h3 class="hall-card-title"><button type="button" class="hall-card-open">${Y.esc(it.title)}</button></h3>
        <p class="hall-card-summary">${Y.esc(it.summary)}</p>
        <p class="hall-card-more" aria-hidden="true">記事をよむ <span>→</span></p>
      </div>
    </article>`;
  }

  function buildHall(id, startIdx = 0) {
    ministry = id;
    list = sorted.filter((n) => has(n, id));
    const s = srcMap[id] || { name: id };
    $(".hall-no").textContent = pad2(numberOf(id));
    $(".hall-title").textContent = s.name;
    $(".hall-count").textContent = list.length ? `${list.length}件の記事` : "";
    $(".hall-empty").hidden = list.length > 0;
    root.classList.toggle("is-empty", !list.length);
    ring.innerHTML = list.map(cardHTML).join("");
    // 水面の映り込み（見た目だけ。読み上げ・フォーカス・用語の対象外）
    reflect.innerHTML = `<div class="hall-ring hall-ring-mirror" data-no-gloss>${list.map(cardHTML).join("")}</div>`;
    reflect.querySelectorAll("button").forEach((b) => { b.tabIndex = -1; });
    reflect.firstElementChild.inert = true;
    cards = [...ring.children];
    mirrors = [...reflect.firstElementChild.children];
    const dots = $(".hall-dots");
    dots.innerHTML = list.length > 1 && list.length <= 15
      ? list.map((_, j) => `<button type="button" class="hall-dot" data-i="${j}" aria-label="${list.length}件中${j + 1}件目へ"></button>`).join("")
      : "";
    root.classList.toggle("is-single", list.length <= 1);
    layoutParams();
    pos = target = Math.max(0, Math.min(list.length - 1, startIdx));
    front = -1;
    render();
    if (window.YG) window.YG.apply(ring).catch(() => {});
  }

  /* ── ドラッグ・ホイール ── */
  let dragging = false, down = null, suppressClick = false;
  stage.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || !list.length || e.target.closest(".gl-pop")) return;
    down = { x: e.clientX, y: e.clientY, startPos: pos, id: e.pointerId, samples: [[performance.now(), pos]] };
  });
  stage.addEventListener("pointermove", (e) => {
    if (!down || e.pointerId !== down.id) return;
    const dx = e.clientX - down.x;
    if (!dragging) {
      if (Math.abs(dx) < 6 || Math.abs(dx) < Math.abs(e.clientY - down.y)) return;
      dragging = true;
      stage.setPointerCapture(e.pointerId);
      stage.classList.add("is-dragging");
    }
    pos = down.startPos - dx / (cardW * 0.85);
    if (!wrap) pos = Math.max(-0.4, Math.min(list.length - 0.6, pos));
    const now = performance.now();
    down.samples.push([now, pos]);
    while (down.samples.length > 2 && now - down.samples[0][0] > 120) down.samples.shift();
    kick();
  });
  const endDrag = (e) => {
    if (!down || (e && e.pointerId !== down.id)) return;
    if (dragging) {
      const [t0, p0] = down.samples[0], now = performance.now();
      const v = now - t0 > 0 ? ((pos - p0) / (now - t0)) * 1000 : 0; // 枚/秒
      target = Math.round(pos + Math.max(-4, Math.min(4, v * 0.32))); // 慣性で少し先まで回して、最寄りのカードに止める
      if (!wrap) target = Math.max(0, Math.min(list.length - 1, target));
      dragging = false;
      suppressClick = true;
      setTimeout(() => { suppressClick = false; }, 0);
      stage.classList.remove("is-dragging");
      kick();
    }
    down = null;
  };
  stage.addEventListener("pointerup", endDrag);
  stage.addEventListener("pointercancel", endDrag);

  let wheelAt = 0, wheelAcc = 0;
  stage.addEventListener("wheel", (e) => {
    if (!list.length) return;
    e.preventDefault();
    const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
    wheelAcc += d;
    const now = performance.now();
    if (Math.abs(wheelAcc) > 30 && now - wheelAt > 320) {
      go(wheelAcc > 0 ? 1 : -1);
      wheelAt = now;
      wheelAcc = 0;
    }
    if (now - wheelAt > 600) wheelAcc = Math.sign(wheelAcc) * Math.min(Math.abs(wheelAcc), 30);
  }, { passive: false });

  ring.addEventListener("click", (e) => {
    if (suppressClick || e.target.closest(".term, .gl-pop, a")) return;
    const card = e.target.closest(".hall-card");
    if (!card) return;
    const j = Number(card.dataset.i);
    if (j === front) openReaderAt(j, true);
    else goTo(j);
  });

  $(".hall-prev").addEventListener("click", () => go(-1));
  $(".hall-next").addEventListener("click", () => go(1));
  $(".hall-dots").addEventListener("click", (e) => {
    const d = e.target.closest(".hall-dot");
    if (d) goTo(Number(d.dataset.i));
  });

  /* ── リーダー ── */
  function renderReader(j) {
    readerIdx = j;
    const it = list[j];
    readerBody.innerHTML = Y.article(it, srcMap);
    const h = readerBody.querySelector(".headline");
    if (h) h.tabIndex = -1;
    $(".hall-reader-pos").textContent = `${j + 1} / ${list.length}`;
    $(".hall-rprev").hidden = j <= 0;
    $(".hall-rnext").hidden = j >= list.length - 1;
    // 真ん中：この記事の府省の記事一覧（ministries.html?m=…）へ。ふつうのページ移動
    const s = srcMap[it.ministry];
    const a = $(".hall-rlist");
    a.href = "ministries.html?m=" + encodeURIComponent(it.ministry);
    // 2行になるときも「の記事一覧」は切らない
    a.innerHTML = `<span>${s ? `${Y.esc(s.name)}<span class="hall-nw">の記事一覧</span>` : "記事一覧"}</span>`;
    $(".hall-copy").textContent = "リンクをコピー";
    reader.scrollTop = 0;
    if (window.YG) window.YG.apply(readerBody).catch(() => {});
  }

  function showReader(j, animate) {
    if (j < 0 || j >= list.length) return;
    const wasHidden = reader.hidden;
    renderReader(j);
    if (j !== front) { pos = target = j; render(); }
    reader.hidden = false;
    root.classList.add("is-reading");
    if (animate && wasHidden && !reduceMotion.matches && cards[j] && reader.animate) {
      // 正面のカードの位置から全画面へ広がる
      const r = cards[j].getBoundingClientRect();
      const W = innerWidth, H = innerHeight;
      const from = `inset(${r.top}px ${W - r.right}px ${H - r.bottom}px ${r.left}px round 18px)`;
      reader.animate([{ clipPath: from, opacity: 0.6 }, { clipPath: "inset(0px 0px 0px 0px round 0px)", opacity: 1 }],
        { duration: 520, easing: "cubic-bezier(.2,.8,.2,1)" });
    }
    const h = readerBody.querySelector(".headline");
    if (h) h.focus({ preventScroll: true });
  }

  function hideReader() {
    if (reader.hidden) return;
    reader.hidden = true;
    root.classList.remove("is-reading");
    readerIdx = -1;
    if (window.YG) window.YG.close();
    const b = cards[front]?.querySelector(".hall-card-open");
    if (isOpen && b) b.focus({ preventScroll: true });
  }

  // 履歴の state: { yk: 1=一覧 / 2=リーダー, depth: このページで自分が push した段数（0 = ディープリンクで来た等） }
  const depthNow = () => (history.state && history.state.depth) || 0;

  function openReaderAt(j, animate) {
    const it = list[j];
    if (!it) return;
    history.pushState({ yk: 2, depth: depthNow() + 1 }, "", "#a=" + encodeURIComponent(it.id));
    showHall(ministry, j);
    showReader(j, animate);
  }

  $(".hall-back").addEventListener("click", backToHall);
  $(".hall-rprev").addEventListener("click", () => stepReader(-1));
  $(".hall-rnext").addEventListener("click", () => stepReader(1));
  $(".hall-copy").addEventListener("click", (e) => {
    const b = e.currentTarget;
    try {
      const p = navigator.clipboard && navigator.clipboard.writeText(location.href);
      if (p) p.then(() => { b.textContent = "コピーしました"; }, () => {});
    } catch (err) { /* コピーできない環境では何もしない */ }
  });

  function stepReader(k) {
    const j = readerIdx + k;
    if (j < 0 || j >= list.length) return;
    history.replaceState(history.state, "", "#a=" + encodeURIComponent(list[j].id));
    renderReader(j);
    pos = target = j;
    render();
    readerBody.querySelector(".headline")?.focus({ preventScroll: true });
  }

  function backToHall() {
    const st = history.state;
    // 一覧からリーダーを開いた（一つ前が一覧の履歴）なら戻る。ディープリンクで来たなら一覧に置き換える
    if (st && st.yk === 2 && st.depth >= 2) history.back();
    else {
      history.replaceState({ yk: 1, depth: Math.max(0, depthNow() - 1) }, "", "#m=" + encodeURIComponent(ministry));
      hideReader();
    }
  }

  /* ── 開く・閉じる ── */
  function lockPage(on) {
    const de = document.documentElement;
    if (on) {
      const sw = innerWidth - de.clientWidth;
      de.classList.add("hall-open");
      de.style.overflow = "hidden";
      if (sw > 0) de.style.paddingRight = sw + "px";
      inerted = [...document.body.children].filter((el) => el !== root && !el.inert && el.tagName !== "SCRIPT");
      inerted.forEach((el) => { el.inert = true; });
    } else {
      de.classList.remove("hall-open");
      de.style.overflow = "";
      de.style.paddingRight = "";
      inerted.forEach((el) => { el.inert = false; });
      inerted = [];
    }
  }

  function showHall(id, startIdx = 0) {
    if (ministry !== id || !isOpen) buildHall(id, startIdx);
    if (!isOpen) {
      isOpen = true;
      lastFocus = document.activeElement;
      root.hidden = false;
      lockPage(true);
      onToggle(true);
      requestAnimationFrame(() => {
        root.classList.add("is-in");
        layoutParams();
        render();
      });
      $(".hall-title").focus({ preventScroll: true });
      setFront(front);
    }
  }

  function closeAll() {
    if (!isOpen) return;
    hideReader();
    isOpen = false;
    root.classList.remove("is-in");
    root.hidden = true;
    cancelAnimationFrame(raf);
    raf = 0;
    lockPage(false);
    if (window.YG) window.YG.close();
    onToggle(false);
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus({ preventScroll: true });
  }

  function close() {
    if (!isOpen) return;
    const d = depthNow();
    if (d > 0) { history.go(-d); return; } // 自分が積んだ履歴の分だけ戻る → popstate で閉じる
    history.replaceState(null, "", location.pathname + location.search);
    closeAll();
  }

  root.querySelectorAll(".hall-close").forEach((b) => b.addEventListener("click", close));

  /* ── ルーター（URL ハッシュ） ── */
  function parseHash() {
    let h = location.hash.slice(1);
    try { h = decodeURIComponent(h); } catch (e) { return null; }
    if (h.startsWith("m=")) return { m: h.slice(2) };
    if (h.startsWith("a=")) return { a: h.slice(2) };
    return null;
  }

  function route() {
    const r = parseHash();
    if (r && r.m && srcMap[r.m]) {
      hideReader();
      const keep = isOpen && ministry === r.m;
      showHall(r.m, keep ? front : 0);
      if (keep) $(".hall-title").focus({ preventScroll: true });
      return;
    }
    if (r && r.a && byId[r.a]) {
      const it = byId[r.a];
      const mid = isOpen && ministry && has(it, ministry) ? ministry : it.ministry;
      const idx = sorted.filter((n) => has(n, mid)).indexOf(it);
      showHall(mid, idx);
      showReader(idx, false);
      return;
    }
    closeAll();
  }

  window.addEventListener("popstate", route);
  window.addEventListener("hashchange", route);

  // ページ内の #m= / #a= リンクは履歴に印をつけて開く（閉じるときに history.back() で戻れるように）
  document.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest && e.target.closest('a[href^="#m="], a[href^="#a="]');
    if (!a) return;
    e.preventDefault();
    const h = a.getAttribute("href");
    if (h.startsWith("#m=")) openMinistry(decodeURIComponent(h.slice(3)));
    else openArticle(decodeURIComponent(h.slice(3)));
  });

  /* ── キーボード ── */
  document.addEventListener("keydown", (e) => {
    if (!isOpen || e.defaultPrevented) return;
    if (e.key === "Escape") {
      e.preventDefault();
      if (!reader.hidden) backToHall();
      else close();
      return;
    }
    if (e.key === "Tab") return trapFocus(e);
    const inField = e.target.closest && e.target.closest("input, textarea, select");
    if (inField) return;
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      const k = e.key === "ArrowLeft" ? -1 : 1;
      if (!reader.hidden) stepReader(k);
      else go(k);
    }
  });

  function trapFocus(e) {
    const scope = reader.hidden ? root : reader;
    const items = [...scope.querySelectorAll('button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])')]
      .filter((el) => el.tabIndex >= 0 && el.getClientRects().length && !el.closest("[inert], [hidden], .hall-reflect, [aria-hidden='true']"));
    const pop = root.querySelector(".gl-pop:not([hidden])");
    if (pop) items.push(...[...pop.querySelectorAll("a[href], button")].filter((el) => !items.includes(el) && !el.closest("[hidden]")));
    if (!items.length) return;
    const first = items[0], last = items[items.length - 1];
    const inside = items.includes(document.activeElement);
    if (e.shiftKey && (document.activeElement === first || !inside)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && (document.activeElement === last || !inside)) { e.preventDefault(); first.focus(); }
  }

  window.addEventListener("resize", () => {
    if (!isOpen) return;
    layoutParams();
    render();
  });

  /* ── 外から呼ぶ API ── */
  function openMinistry(id) {
    if (!srcMap[id]) return;
    if (isOpen && ministry === id && reader.hidden) return;
    history.pushState({ yk: 1, depth: isOpen ? depthNow() + 1 : 1 }, "", "#m=" + encodeURIComponent(id));
    route();
  }
  function openArticle(id) {
    const it = byId[id];
    if (!it) return;
    if (isOpen && !reader.hidden) {
      history.replaceState(history.state, "", "#a=" + encodeURIComponent(id));
    } else {
      // 一覧を経由した履歴にしておくと「戻る」で一覧へ、もう一度で閉じる
      if (!isOpen) history.pushState({ yk: 1, depth: 1 }, "", "#m=" + encodeURIComponent(it.ministry));
      history.pushState({ yk: 2, depth: depthNow() + 1 }, "", "#a=" + encodeURIComponent(id));
    }
    route();
  }

  // 最初の表示：URL にハッシュがあれば開く
  if (parseHash()) route();

  return { openMinistry, openArticle, close };
}
