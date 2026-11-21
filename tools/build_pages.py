"""有権者：検索に載せるための静的なページを作る

使い方: python tools/build_pages.py
- a/<記事id>.html 記事ごとのページ（本文・この記事に出てくる言葉・関連する記事）と a/index.html 記事一覧
- m/<府省id>.html・m/index.html 府省ごとの記事一覧 / p/<県id>.html・p/index.html 都道府県ごとの記事一覧
- g/<用語>.html・g/index.html 用語集（data/glossary.json の語のうち、記事に出てくるものだけ。
  data/glossary_pages.json があれば説明文 intro と参考リンク refs も出す。無くてもよい）
- feed.xml（Atom・新しい記事 50件）と sitemap.xml（決まったページ + /a/ + 全記事 + m/ p/ g/）
- ministries.html・local.html の <!-- STATIC-LIST --> と pledges.html の <!-- STATIC-PLEDGES --> のあいだに、文字だけの一覧を入れる
- 公開をやめた記事・記事の無くなった府省・県・用語のページは消す。index.html は消さない
- 入力の JSON には書き込まない。確認ページ（tools/review_server.py）で公開・修正すると自動で呼ばれる
- 書くのは中身が変わったファイルだけ（git の差分が出ないように）。build() は変わったページの URL も返す（IndexNow 用）
"""
import datetime as dt
import html
import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import quote

SITE = "https://yukensha.com"
OG_DEFAULT = SITE + "/assets/og-image.png"
FORM = "https://docs.google.com/forms/d/e/1FAIpQLSe30fi9qbWSkPtcU4dDkXgr1NCUvGQTBiDIa5CZJVfiiUH3nQ/viewform"
GOATCOUNTER = '<script data-goatcounter="https://yossy8080.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>'
ICON = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%2304080f'/%3E%3Ccircle cx='16' cy='16' r='9' fill='none' stroke='%238fd0ff' stroke-width='2'/%3E%3Ccircle cx='16' cy='16' r='2.6' fill='%23e8452c'/%3E%3C/svg%3E"
# sitemap.xml に必ず入れるページ（このあとに /a/ と記事のページを足す）
FIXED_PAGES = ["/", "/ministries.html", "/pledges.html", "/local.html", "/opinion.html", "/about.html", "/privacy.html"]
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
W3C = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?([+-]\d{2}:\d{2}|Z))?$")
DESC_MAX = 120
PUBLISHER = {"@type": "Organization", "name": "有権者", "url": SITE + "/"}


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def read_json(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def read_raw(p: Path) -> str:
    """改行を変えずに読む（手書きの HTML には CRLF の行が混ざっているものがある）。"""
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def write_if_changed(p: Path, text: str) -> bool:
    if p.exists() and read_raw(p) == text:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return True


class Out:
    """書いたファイルを覚えておく（IndexNow に送る「変わったページの URL」を作るため）。"""

    def __init__(self, root: Path):
        self.root, self.written, self.changed = root, 0, []

    def write(self, rel: str, text: str) -> bool:
        if write_if_changed(self.root / rel, text):
            self.written += 1
            self.changed.append(rel)
            return True
        return False

    def inject(self, rel: str, name: str, block: str) -> bool:
        """手書きの HTML の <!-- name:BEGIN --> と <!-- name:END --> のあいだだけを書きかえる（ほかの部分は1文字も変えない）。"""
        p = self.root / rel
        if not p.exists():
            return False
        t = read_raw(p)
        b, e = f"<!-- {name}:BEGIN -->", f"<!-- {name}:END -->"
        i, j = t.find(b), t.find(e)
        if i < 0 or j < i:
            return False
        nl = "\r\n" if t[i + len(b): i + len(b) + 2] == "\r\n" else "\n"
        return self.write(rel, t[: i + len(b)] + nl + block.replace("\n", nl) + nl + t[j:])


def page_url(rel: str) -> str:
    """ファイルのパス（a/index.html）→ 公開の URL（https://yukensha.com/a/）。日本語のファイル名は % で表す。"""
    rel = rel.replace("\\", "/")
    if rel == "index.html":
        return SITE + "/"
    if rel.endswith("/index.html"):
        rel = rel[: -len("index.html")]
    return SITE + "/" + quote(rel)


def photo_ok(p) -> bool:
    """app.js の photoOk と同じ：ライセンス確認済み、かつ（人物なし か 人物も確認済み）。"""
    return isinstance(p, dict) and bool(p.get("src")) and p.get("ok_license") is True and (p.get("people") is False or p.get("ok_people") is True)


def fmt_date(iso: str, year=True) -> str:
    """app.js の fmtDate と同じ形（11月9日（月））。year=True なら年も付ける。"""
    y, m, d = (int(x) for x in iso[:10].split("-"))
    w = "月火水木金土日"[dt.date(y, m, d).weekday()]
    return f"{y}年{m}月{d}日（{w}）" if year else f"{m}月{d}日（{w}）"


def lastmod(it) -> str:
    for k in ("updated_at", "published_at", "date"):
        v = str(it.get(k) or "")
        if W3C.match(v):
            return v
    return ""


def short_desc(s) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= DESC_MAX else s[: DESC_MAX - 1] + "…"


def json_ld(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1).replace("</", "<\\/")  # </script> で切れないように


def abs_url(path: str) -> str:
    return SITE + "/" + path.lstrip("/")


def sort_key(it):
    return (it.get("date", ""), it.get("published_at", ""), it["id"])


# ── 共通の部品（about.html と同じヘッダー・フッター。パスは / から） ──

def header(current="") -> str:
    def cur(k):
        return ' aria-current="page"' if k == current else ""
    return f"""<header class="site-header">
  <div class="site-header-inner">
    <a class="site-logo" href="/">有権者</a>
    <nav class="site-nav" aria-label="メニュー">
      <ul>
        <li><a href="/#stream"{cur("stream")}>府省</a></li>
        <li><a href="/#opinion">オピニオン</a></li>
        <li><a href="/#local"{cur("local")}>地方</a></li>
        <li><a href="/#pledges" aria-label="公約チェッカー">公約<span class="nav-long">チェッカー</span></a></li>
        <li><a href="/about.html" aria-label="このサイトについて"><span class="nav-long">このサイトについて</span><span class="nav-short">概要</span></a></li>
      </ul>
    </nav>
  </div>
</header>"""


FOOTER = f"""<footer>
  <div class="wrap">
    <p>有権者 — 要約はAI（Hermes）が下書きし、運営者が確認してから公開しています。誤りに気づいたら<a href="{FORM}" target="_blank" rel="noopener">お問い合わせフォーム</a>からお知らせください。</p>
    <p>各記事は、政府のウェブサイト（公共データ利用規約 PDL1.0 等）の情報をもとに、有権者が要約・加工して作成したものです。正確な内容は必ず出典をご確認ください。</p>
    <p class="footer-links"><a href="/about.html">このサイトについて</a> ・ <a href="/privacy.html">プライバシーポリシー</a> ・ <a href="/a/">記事一覧</a> ・ <a href="/g/">用語集</a> ・ <a href="{FORM}" target="_blank" rel="noopener">お問い合わせ</a></p>
  </div>
</footer>"""


def page(*, title, desc, canonical, og_type, og_image, ld, body, current="", glossary=False) -> str:
    lds = "".join(f'<script type="application/ld+json">\n{json_ld(x)}\n</script>\n' for x in ld)
    gl_css = '<link rel="stylesheet" href="/assets/glossary.css">\n' if glossary else ""
    # 用語ポップアップ：glossary.js の初期値は相対パス（data/glossary.json）なので、/ からのパスで先に読み込む
    gl_js = ('<script src="/assets/glossary.js"></script>\n'
             '<script>\nif (window.YG) YG.load("/data/glossary.json").then(() => YG.apply(document.querySelector("article.item"))).catch(() => {});\n</script>\n'
             if glossary else "")
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="有権者">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:image" content="{esc(og_image)}">
<meta property="og:locale" content="ja_JP">
<meta name="twitter:card" content="summary_large_image">
{lds}<link rel="alternate" type="application/atom+xml" title="有権者" href="/feed.xml">
<link rel="icon" href="{ICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=BIZ+UDPGothic:wght@400;700&family=Shippori+Mincho:wght@700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/style.css">
<link rel="stylesheet" href="/assets/article.css">
{gl_css}{GOATCOUNTER}
</head>
<body>
{header(current)}
<main class="wrap">
{body}
</main>
{FOOTER}
{gl_js}</body>
</html>
"""


# ── 記事の本文（app.js の Y.article と同じ並び・同じ文言） ──

def crumbs_ld(crumbs) -> dict:
    """パンくず [(名前, URL), …] の JSON-LD（BreadcrumbList）。"""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(crumbs)],
    }


def crumbs_nav(crumbs) -> str:
    """見えるパンくず（最後の1つ＝このページはリンクにしない）。"""
    lis = [f'<li><a href="{esc(u[len(SITE):] or "/")}">{esc(n)}</a></li>' for n, u in crumbs[:-1]]
    lis.append(f'<li aria-current="page">{esc(crumbs[-1][0])}</li>')
    return '<nav class="ap-crumbs" aria-label="現在地"><ol>' + "".join(lis) + "</ol></nav>"


def latest(items) -> str:
    """一覧の lastmod：載せている記事のうち、いちばん新しい更新日時。"""
    return max((lastmod(it) for it in items), default="", key=lambda s: s[:10] + s)


def photo_html(p, lazy=False) -> str:
    w, h = p.get("width"), p.get("height")
    size = f' width="{w}" height="{h}" style="aspect-ratio:{w}/{h}"' if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0 else ""
    link = f'（<a href="{esc(p["page_url"])}" target="_blank" rel="noopener">出典ページ ↗</a>）' if re.match(r"^https?://", str(p.get("page_url") or "")) else ""
    cap = esc(p.get("credit")) + link
    src = "/" + str(p["src"]).lstrip("/")
    return (f'<figure class="photo"><img src="{esc(src)}" alt="{esc(p.get("alt"))}"{' loading="lazy"' if lazy else ""} decoding="async"{size}>'
            + (f"<figcaption>{cap}</figcaption>" if cap else "") + "</figure>")


def source_line(it) -> str:
    return (f'<p class="source">出典：<a href="{esc(it.get("source_url"))}" target="_blank" rel="noopener">「{esc(it.get("source_title"))}」（{esc(it.get("site"))}）</a>'
            "をもとに有権者が要約して作成</p>")


def refs_line(it) -> str:
    refs = [r for r in it.get("refs") or [] if isinstance(r, dict) and r.get("url")]
    if not refs:
        return ""
    links = "、".join(f'<a href="{esc(r["url"])}" target="_blank" rel="noopener">「{esc(r.get("title"))}」（{esc(r.get("site"))}）</a>' for r in refs)
    return f'<p class="source source-refs">背景の説明：{links}を参考に有権者が作成</p>'


def explain_html(it) -> str:
    """背景の説明。問いを <h2> にする（「〇〇って？」で検索されたときに見出しとして読まれるように）。"""
    qa = [x for x in it.get("explain") or [] if isinstance(x, dict) and (x.get("q") or x.get("a"))]
    if not qa:
        return ""
    return ('<section class="explain" aria-label="背景の説明">'
            + "".join((f'<h2 class="explain-q">{esc(x["q"])}</h2>' if x.get("q") else "")
                      + (f'<p class="explain-a">{esc(x["a"])}</p>' if x.get("a") else "") for x in qa) + "</section>")


def quotes_html(it) -> str:
    qs = it.get("quotes") or []
    if not qs:
        return ""
    who = "・".join(esc(x) for x in (it.get("speaker"), it.get("scene")) if x)
    return ('<figure class="quotes">' + "".join(f"<blockquote>「{esc(q)}」</blockquote>" for q in qs)
            + (f"<figcaption>— {who}</figcaption>" if who else "") + "</figure>")


class Ctx:
    """府省・都道府県の名前と、一覧・3D ビューへのリンク。"""

    def __init__(self, sources, prefs):
        self.src = {s["id"]: s for s in sources}
        self.pref = {p["id"]: p for p in prefs}
        self.sources, self.prefs = sources, prefs
        self.m_pages, self.p_pages = set(), set()  # 一覧のページ（m/<id>.html・p/<id>.html）がある府省・都道府県

    def is_local(self, it):
        return "pref" in it

    def gid(self, it):
        return it["pref"] if self.is_local(it) else it.get("ministry")

    def ids(self, it):
        return [it["pref"], *(it.get("pref_also") or [])] if self.is_local(it) else [it.get("ministry"), *(it.get("also") or [])]

    def name(self, it, gid):
        t = self.pref if self.is_local(it) else self.src
        return (t.get(gid) or {}).get("name", "")

    def short(self, it):
        t = self.pref if self.is_local(it) else self.src
        g = t.get(self.gid(it)) or {}
        return g.get("name_short") or g.get("short") or g.get("name", "")

    def list_href(self, it, gid):
        # 静的な一覧のページ（m/・p/）があればそちら。無ければ今までの JS のページ
        if self.is_local(it):
            return f"/p/{gid}.html" if gid in self.p_pages else f"/local.html?p={gid}"
        return f"/m/{gid}.html" if gid in self.m_pages else f"/ministries.html?m={gid}"

    def labels(self, it) -> str:
        """記事の府省・都道府県の名前（一覧のページへのリンク）。"""
        out = []
        for x in self.ids(it):
            n = self.name(it, x)
            if n:
                out.append(f'<a class="kicker-ministry" href="{esc(self.list_href(it, x))}">{esc(n)}</a>')
        return '<span class="sep">・</span>'.join(out)

    def view_href(self, it):
        # 地方の記事は local.html のリーダー（トップの 3D は国の記事だけ）
        return f"/local.html?p={it['pref']}#a={it['id']}" if self.is_local(it) else f"/#a={it['id']}"


def words_html(words) -> str:
    """この記事に出てくる言葉（用語集のページがあるものだけ）。"""
    if not words:
        return ""
    return ('<section class="ap-sec ap-words" aria-labelledby="ap-words"><h2 class="ap-h2" id="ap-words">この記事に出てくる言葉</h2><ul class="g-terms">'
            + "".join(f'<li><a href="{esc(g_href(s))}">{esc(t)}</a></li>' for t, s in words) + "</ul></section>")


def related_html(related, ctx: Ctx) -> str:
    if not related:
        return ""
    lis = "".join(f'<li><a href="/a/{esc(r["id"])}.html">{esc(r.get("title"))}</a>'
                  f'<span class="ap-rel-meta"><time datetime="{esc(r["date"])}">{fmt_date(r["date"])}</time>・{esc(ctx.name(r, ctx.gid(r)))}</span></li>'
                  for r in related)
    return f'<section class="ap-sec ap-related" aria-labelledby="ap-related"><h2 class="ap-h2" id="ap-related">関連する記事</h2><ul class="ap-rel">{lis}</ul></section>'


def related_items(items, ctx: Ctx, terms_of, n=4) -> dict:
    """関連する記事：同じ用語 ×3 + 同じタグ ×2 + 同じ府省（県）×1。同点は新しい記事が先。その記事自身は入れない。"""
    info = {it["id"]: (set(terms_of[it["id"]]), set(it.get("tags") or []), (ctx.is_local(it), ctx.gid(it))) for it in items}
    newest = sorted(items, key=sort_key, reverse=True)
    out = {}
    for it in items:
        tm, tg, grp = info[it["id"]]
        scored = []
        for j, x in enumerate(newest):
            if x["id"] == it["id"]:
                continue
            xt, xg, xgrp = info[x["id"]]
            scored.append((-(3 * len(tm & xt) + 2 * len(tg & xg) + (grp == xgrp)), j, x))
        scored.sort(key=lambda s: (s[0], s[1]))
        out[it["id"]] = [x for _, _, x in scored[:n]]
    return out


def article_page(it, ctx: Ctx, newer, older, words=(), related=()) -> str:
    aid = it["id"]
    canonical = f"{SITE}/a/{aid}.html"
    gid = ctx.gid(it)
    gname = ctx.name(it, gid)
    photos = [p for p in it.get("photos") or [] if photo_ok(p)]
    og_image = abs_url(photos[0]["src"]) if photos else OG_DEFAULT
    title = f"{it.get('title', '')}｜有権者"
    desc = short_desc(it.get("summary"))

    news_ld = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": it.get("title", ""),
        "description": desc,
        "datePublished": it.get("published_at") or it.get("date"),
    }
    if it.get("updated_at"):
        news_ld["dateModified"] = it["updated_at"]
    news_ld.update({
        "image": [abs_url(p["src"]) for p in photos] or [OG_DEFAULT],
        "author": PUBLISHER,
        "publisher": PUBLISHER,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
    })
    crumbs = [("有権者", SITE + "/")]
    if gname:
        crumbs.append((gname, SITE + ctx.list_href(it, gid)))
    crumbs.append((it.get("title", ""), canonical))
    crumb_ld = crumbs_ld(crumbs)

    ph = [photo_html(p, lazy=i > 0) for i, p in enumerate(photos)]  # 1枚目は見出しのすぐ下なので先に読む
    pts = "".join(f"<li>{esc(p)}</li>" for p in it.get("points") or [])
    tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in it.get("tags") or [])
    ex = explain_html(it)
    date = str(it.get("date", ""))

    crumb_nav = ('<nav class="ap-crumbs" aria-label="現在地"><ol>'
                 '<li><a href="/">有権者</a></li>'
                 + (f'<li><a href="{esc(ctx.list_href(it, gid))}">{esc(gname)}</a></li>' if gname else "")
                 + '<li><a href="/a/">記事一覧</a></li></ol></nav>')

    def side(it2, label):
        if not it2:
            return ""
        return (f'<a class="ap-step" href="/a/{esc(it2["id"])}.html"><span class="ap-step-label">{label}</span>'
                f'<span class="ap-step-title">{esc(it2.get("title"))}</span></a>')

    steps = side(newer, "← 新しい記事") + side(older, "古い記事 →")
    body = f"""<div class="ap">
{crumb_nav}
<article class="item" id="{esc(aid)}">
  <p class="kicker"><time datetime="{esc(date)}">{fmt_date(date)}</time>{ctx.labels(it)}</p>
  <h1 class="headline">{esc(it.get("title"))}</h1>
  {ph[0] if ph else ""}
  <p class="summary">{esc(it.get("summary"))}</p>
  {ex}{quotes_html(it)}
  {(('<h2 class="points-label" data-no-gloss>今回のポイント</h2>' if ex else "") + f'<ul class="points">{pts}</ul>') if pts else ""}
  {"".join(ph[1:])}
  {source_line(it)}{refs_line(it)}
  {f'<p class="tags">{tags}</p>' if tags else ""}
</article>
{words_html(words)}
{related_html(related, ctx)}
<nav class="ap-links" aria-label="ほかの記事">
  <p class="ap-actions"><a class="ap-btn" href="{esc(ctx.view_href(it))}">3Dの記事ビューで読む</a>{f'<a class="ap-btn" href="{esc(ctx.list_href(it, gid))}">{esc(gname)}の記事一覧</a>' if gname else ""}<a class="ap-btn" href="/a/">すべての記事</a></p>
  {f'<div class="ap-steps">{steps}</div>' if steps else ""}
</nav>
</div>"""
    return page(title=title, desc=desc, canonical=canonical, og_type="article", og_image=og_image,
                ld=[news_ld, crumb_ld], body=body, current="local" if ctx.is_local(it) else "stream", glossary=True)


def index_page(items, ctx: Ctx) -> str:
    """記事一覧：新しい順・月ごと。リンクはふつうの <a>（クロールで全記事にたどり着けるように）。"""
    groups = []
    for it in items:
        ym = str(it.get("date", ""))[:7]
        if not groups or groups[-1][0] != ym:
            groups.append((ym, []))
        groups[-1][1].append(it)
    secs = []
    for ym, its in groups:
        y, m = ym.split("-")
        rows = "".join(
            f'\n  <li class="row"><time datetime="{esc(it["date"])}">{fmt_date(it["date"], year=False)}</time>'
            f'<span class="row-ministry">{esc(ctx.short(it))}</span><a href="/a/{esc(it["id"])}.html">{esc(it.get("title"))}</a></li>'
            for it in its)
        secs.append(f'<section class="ap-month" aria-labelledby="m-{ym}">\n<h2 class="section-title" id="m-{ym}">{int(y)}年{int(m)}月'
                    f'<small>{len(its)}件</small></h2>\n<ul class="rows">{rows}\n</ul>\n</section>')
    desc = "有権者に載せたすべての記事（官邸・各府省と都道府県の発表の要約）を、新しい順に月ごとに並べています。"
    body = (f'<h1 class="page-title">記事一覧</h1>\n<p class="lead">これまでに載せた記事 {len(items)}件を、新しい順に並べています。'
            '府省ごとに見るときは<a href="/m/">府省別の記事一覧</a>、都道府県は<a href="/p/">都道府県別の記事一覧</a>へ。</p>\n'
            + "\n".join(secs))
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "記事一覧｜有権者", "url": SITE + "/a/",
          "isPartOf": {"@type": "WebSite", "name": "有権者", "url": SITE + "/"}}
    crumbs = crumbs_ld([("有権者", SITE + "/"), ("記事一覧", SITE + "/a/")])
    return page(title="記事一覧｜有権者", desc=desc, canonical=SITE + "/a/", og_type="website", og_image=OG_DEFAULT, ld=[ld, crumbs], body=body)


# ── 府省ごと（m/）・都道府県ごと（p/）の一覧 ──

REGIONS = ["北海道・東北", "関東", "中部", "近畿", "中国", "四国", "九州・沖縄"]


def list_item(it, ctx: Ctx, h="h2", tags=True) -> str:
    """一覧の1件：日付・府省（県）・題名（記事のページへ）・要約・タグ。"""
    tg = "".join(f'<span class="tag">{esc(t)}</span>' for t in it.get("tags") or []) if tags else ""
    return (f'\n<li class="ml-item"><p class="kicker"><time datetime="{esc(it["date"])}">{fmt_date(it["date"])}</time>{ctx.labels(it)}</p>'
            f'<{h} class="ml-title"><a href="/a/{esc(it["id"])}.html">{esc(it.get("title"))}</a></{h}>'
            f'<p class="ml-sum">{esc(it.get("summary"))}</p>' + (f'<p class="tags">{tg}</p>' if tg else "") + "</li>")


def collection_ld(name, url, items) -> dict:
    return {"@context": "https://schema.org", "@type": "CollectionPage", "name": name, "url": url,
            "isPartOf": {"@type": "WebSite", "name": "有権者", "url": SITE + "/"},
            "mainEntity": {"@type": "ItemList", "numberOfItems": len(items),
                           "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": f"{SITE}/a/{it['id']}.html"}
                                               for i, it in enumerate(items)]}}


def group_page(kind, g, its, ctx: Ctx, home_url="", home_label="") -> str:
    """m/<府省id>.html・p/<県id>.html：その府省（県）の記事を新しい順にすべて。"""
    local = kind == "p"
    gid, name = g["id"], g["name"]
    canonical = f"{SITE}/{kind}/{gid}.html"
    title = f"{name}のニュース一覧（最新の発表をわかりやすく）｜有権者"
    desc = short_desc(f"{name}の発表をもとにした記事{len(its)}件を、新しい順に要約で紹介。最新：{its[0].get('title', '')}")
    if local:
        lead = f"{name}の公式発表をもとにした記事（{len(its)}件）を、新しい順に並べています。"
        views = f'<a class="ap-btn" href="/local.html?p={esc(gid)}">3Dの日本地図で見る</a>'
        up = ("地方", SITE + "/p/")
    else:
        what = g["note"] + "を、元の言葉の引用と要約で載せています" if g.get("note") else name + "の発表を要約しています"
        lead = f"{what}（{len(its)}件・新しい順）。"
        views = (f'<a class="ap-btn" href="/#m={esc(gid)}">3Dの記事ビューで見る</a>'
                 f'<a class="ap-btn" href="/ministries.html?m={esc(gid)}">府省別のページで見る</a>')
        up = ("府省別", SITE + "/m/")
    if home_url:
        lead += f'元の情報：<a href="{esc(home_url)}" target="_blank" rel="noopener">{esc(home_label)}</a>'
    crumbs = [("有権者", SITE + "/"), up, (name, canonical)]
    body = f"""<div class="ap">
{crumbs_nav(crumbs)}
<h1 class="page-title">{esc(name)}</h1>
<p class="lead">{lead}</p>
<p class="ap-actions">{views}<a class="ap-btn" href="{esc(up[1][len(SITE):])}">{"ほかの都道府県" if local else "ほかの府省"}</a></p>
<ol class="ml-list">{"".join(list_item(it, ctx) for it in its)}
</ol>
</div>"""
    return page(title=title, desc=desc, canonical=canonical, og_type="website", og_image=OG_DEFAULT,
                ld=[collection_ld(f"{name}のニュース一覧", canonical, its), crumbs_ld(crumbs)], body=body,
                current="local" if local else "stream")


def group_row(href, name, its) -> str:
    top = its[0]
    return (f'\n<li class="mg-item"><a class="mg-name" href="{esc(href)}">{esc(name)}<span class="count">{len(its)}件</span></a>'
            f'<span class="mg-latest">最新：<a href="/a/{esc(top["id"])}.html">{esc(top.get("title"))}</a>'
            f'（{fmt_date(top["date"], year=False)}）</span></li>')


def m_index_page(groups, ctx: Ctx) -> str:
    """m/index.html：府省の一覧（記事の数と、いちばん新しい記事）。"""
    canonical = SITE + "/m/"
    crumbs = [("有権者", SITE + "/"), ("府省別", canonical)]
    n = sum(1 for _ in {it["id"] for _, its in groups for it in its})
    rows = "".join(group_row(f"/m/{g['id']}.html", g["name"], its) for g, its in groups)
    body = f"""<div class="ap">
{crumbs_nav(crumbs)}
<h1 class="page-title">府省別の記事一覧</h1>
<p class="lead">官邸・各府省の発表をもとにした記事（{n}件）を、府省ごとにまとめています。1つの記事が2つ以上の府省に入ることがあります。</p>
<ul class="mg-list">{rows}
</ul>
</div>"""
    desc = short_desc(f"首相官邸・内閣府・各省など{len(groups)}の府省ごとに、発表をわかりやすく要約した記事の一覧です。")
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "府省別の記事一覧", "url": canonical,
          "isPartOf": {"@type": "WebSite", "name": "有権者", "url": SITE + "/"}}
    return page(title="府省別の記事一覧（官邸・各府省のニュース）｜有権者", desc=desc, canonical=canonical, og_type="website",
                og_image=OG_DEFAULT, ld=[ld, crumbs_ld(crumbs)], body=body, current="stream")


def region_blocks(ctx: Ctx, by_pref, h="h2", cls="section-title") -> str:
    """都道府県を地方ごとに。記事のある県だけリンク（記事の数つき）。"""
    out = []
    for r in REGIONS:
        lis = []
        for p in (x for x in ctx.prefs if x.get("region") == r):
            its = by_pref.get(p["id"])
            lis.append(f'<li><a href="/p/{esc(p["id"])}.html">{esc(p["name"])}<span class="count">{len(its)}件</span></a></li>' if its
                       else f'<li><span class="mg-none">{esc(p["name"])}</span></li>')
        out.append(f'<section class="mg-region"><{h} class="{cls}">{esc(r)}</{h}><ul class="mg-prefs">{"".join(lis)}</ul></section>')
    return "\n".join(out)


def p_index_page(by_pref, ctx: Ctx) -> str:
    """p/index.html：47都道府県（地方ごと）。記事のある県はリンク。"""
    canonical = SITE + "/p/"
    crumbs = [("有権者", SITE + "/"), ("地方", canonical)]
    n = len({it["id"] for its in by_pref.values() for it in its})
    body = f"""<div class="ap">
{crumbs_nav(crumbs)}
<h1 class="page-title">都道府県別の記事一覧</h1>
<p class="lead">都道府県の公式発表をもとにした記事（{n}件・{len(by_pref)}の都道府県）を、地方ごとに並べています。数字は記事の数です。</p>
<p class="ap-actions"><a class="ap-btn" href="/local.html">3Dの日本地図で選ぶ</a></p>
{region_blocks(ctx, by_pref)}
</div>"""
    desc = "47都道府県の公式発表をもとにした記事を、地方ごとに並べた一覧です。知事の会見・予算・条例などを、出典つきでわかりやすく要約しています。"
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "都道府県別の記事一覧", "url": canonical,
          "isPartOf": {"@type": "WebSite", "name": "有権者", "url": SITE + "/"}}
    return page(title="都道府県別の記事一覧（地方のニュース）｜有権者", desc=desc, canonical=canonical, og_type="website",
                og_image=OG_DEFAULT, ld=[ld, crumbs_ld(crumbs)], body=body, current="local")


def static_ministries(groups) -> str:
    """ministries.html に入れる、クロールできる府省の一覧（<!-- STATIC-LIST --> のあいだ）。"""
    lis = "".join(f'\n    <li><a href="/m/{esc(g["id"])}.html">{esc(g["name"])}<span class="count">{len(its)}件</span></a></li>' for g, its in groups)
    return (f'<section class="wrap static-list" aria-labelledby="static-list-title">\n  <h2 class="section-title" id="static-list-title">府省ごとの記事一覧'
            f'<small><a href="/m/">すべての府省</a></small></h2>\n  <ul class="ministry-list">{lis}\n  </ul>\n</section>')


def static_prefs(by_pref, ctx: Ctx) -> str:
    """local.html に入れる、記事のある都道府県の一覧（地方ごと）。"""
    secs = []
    for r in REGIONS:
        lis = "".join(f'<li><a href="/p/{esc(p["id"])}.html">{esc(p["name"])}<span class="count">{len(by_pref[p["id"]])}件</span></a></li>'
                      for p in ctx.prefs if p.get("region") == r and p["id"] in by_pref)
        if lis:
            secs.append(f'\n  <section class="mg-region"><h3>{esc(r)}</h3><ul class="ministry-list">{lis}</ul></section>')
    return (f'<section class="wrap static-list" aria-labelledby="static-list-title">\n  <h2 class="section-title" id="static-list-title">都道府県ごとの記事一覧'
            f'<small><a href="/p/">47都道府県</a></small></h2>{"".join(secs)}\n</section>')


# ── 用語集（g/）：glossary.js と同じ決まりで、記事に出てくる用語を探す ──

ASCII_KEY = re.compile(r"^[\x21-\x7e]+$")
WORD_CHAR = re.compile(r"[A-Za-z0-9]")
BAD_CHARS = re.compile(r'[\\/:*?"<>|#%&\s]')  # Windows のファイル名・URL に使えない文字
WIN_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def term_slug(term: str) -> str:
    """用語 → g/ のファイル名（.html の前）。英数字だけの語は小文字・空白はハイフン（JC-STAR → jc-star）、
    ほかはその語のまま（ファイル名・URL に使えない文字だけ消す）。重なったときの -2 は build の中でつける。"""
    term = str(term or "").strip()
    if re.fullmatch(r"[\x20-\x7e]+", term):
        s = re.sub(r"[^a-z0-9-]", "", re.sub(r"\s+", "-", term.lower()))
        s = re.sub(r"-{2,}", "-", s).strip("-")
        if s:
            return s
    return BAD_CHARS.sub("", term).rstrip(".") or "term"


def g_href(slug: str) -> str:
    return "/g/" + quote(slug) + ".html"


def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2  # JS の length と同じ数え方（長い語から先に探す順番をそろえる）


class Glossary:
    """data/glossary.json の用語。find(記事) で、その記事に出てくる用語（term）を出てくる順に返す。"""

    def __init__(self, entries):
        self.entries = [e for e in entries if isinstance(e, dict) and e.get("term")]
        self.by_key = {}
        for e in self.entries:
            for k in [e["term"], *(e.get("aliases") or [])]:
                if k:
                    self.by_key[k] = e
        keys = sorted(self.by_key, key=utf16_len, reverse=True)
        self.rx = re.compile("|".join(re.escape(k) for k in keys)) if keys else None

    def find_text(self, text: str, found: list):
        if not self.rx or not text:
            return
        pos = 0
        while True:
            m = self.rx.search(text, pos)
            if not m:
                return
            key = m.group(0)
            # 英字の略語は前後が英数字でないときだけ（glossary.js と同じ。例: "GDP"）
            if ASCII_KEY.match(key) and (WORD_CHAR.match(text[m.start() - 1] if m.start() else "")
                                         or WORD_CHAR.match(text[m.end()] if m.end() < len(text) else "")):
                pos = m.start() + 1
                continue
            t = self.by_key[key]["term"]
            if t not in found:
                found.append(t)
            pos = m.end()

    def find(self, it) -> list:
        found = []
        texts = [it.get("title"), it.get("summary")]
        for x in it.get("explain") or []:
            if isinstance(x, dict):
                texts += [x.get("q"), x.get("a")]
        texts += list(it.get("points") or []) + list(it.get("quotes") or [])
        for s in texts:
            if isinstance(s, str):
                self.find_text(s, found)
        return found


KANA_ROWS = [("あ行", "あいうえおぁぃぅぇぉゔ"), ("か行", "かきくけこがぎぐげごゕゖ"), ("さ行", "さしすせそざじずぜぞ"),
             ("た行", "たちつてとだぢづでどっ"), ("な行", "なにぬねの"), ("は行", "はひふへほばびぶべぼぱぴぷぺぽ"),
             ("ま行", "まみむめも"), ("や行", "やゆよゃゅょ"), ("ら行", "らりるれろ"), ("わ行", "わゐゑをんゎ")]
OTHER_ROW = "英数字"


def kana_row(yomi: str) -> str:
    c = (yomi or "").strip()[:1]
    if "ァ" <= c <= "ヶ":
        c = chr(ord(c) - 0x60)  # カタカナ → ひらがな
    for name, chars in KANA_ROWS:
        if c and c in chars:
            return name
    return OTHER_ROW


def cut(s, n=40) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def term_page(e, slug, its, related, extra, ctx: Ctx, slugs) -> str:
    """g/<slug>.html：用語の簡単な説明と、その用語が出てくる記事。"""
    term = e["term"]
    canonical = SITE + g_href(slug)
    title = f"{term}とは？意味と政府の最近の動き｜有権者"
    desc = short_desc(e.get("short") or f"{term}の簡単な説明")
    crumbs = [("有権者", SITE + "/"), ("用語集", SITE + "/g/"), (term, canonical)]
    parts = [crumbs_nav(crumbs), f'<h1 class="page-title">{esc(term)}とは</h1>']
    if e.get("yomi"):
        parts.append(f'<p class="g-yomi">よみ：{esc(e["yomi"])}</p>')
    aliases = [a for a in e.get("aliases") or [] if a and a != term]
    if aliases:
        parts.append(f'<p class="g-yomi">ほかの書き方：{esc("・".join(aliases))}</p>')
    if e.get("short"):
        parts.append(f'<p class="g-short">{esc(e["short"])}</p>')
    for para in extra.get("intro") or []:
        if isinstance(para, str) and para.strip():
            parts.append(f'<p class="g-intro">{esc(para)}</p>')
    links = []
    if re.match(r"^https?://", str(e.get("src_url") or "")):
        links.append(f'<a href="{esc(e["src_url"])}" target="_blank" rel="noopener">くわしく：{esc(e.get("src_name") or "公式ページ")} ↗</a>')
    for r in extra.get("refs") or []:
        if isinstance(r, dict) and re.match(r"^https?://", str(r.get("url") or "")):
            site = f"（{esc(r['site'])}）" if r.get("site") else ""
            links.append(f'<a href="{esc(r["url"])}" target="_blank" rel="noopener">「{esc(r.get("title") or r["url"])}」{site} ↗</a>')
    if links:
        parts.append('<ul class="g-src">' + "".join(f"<li>{x}</li>" for x in links) + "</ul>")
    parts.append('<p class="g-note">有権者編集部による簡単な説明</p>')
    parts.append(f'<section class="g-sec" aria-labelledby="g-articles"><h2 class="section-title" id="g-articles">{esc(term)}が出てくる記事（{len(its)}件）</h2>'
                 f'<ol class="ml-list">{"".join(list_item(it, ctx, h="h3", tags=False) for it in its)}\n</ol></section>')
    if related:
        parts.append('<section class="g-sec" aria-labelledby="g-related"><h2 class="section-title" id="g-related">関連する言葉</h2><ul class="g-terms">'
                     + "".join(f'<li><a href="{esc(g_href(slugs[t]))}">{esc(t)}</a></li>' for t in related) + "</ul></section>")
    parts.append('<p class="ap-actions"><a class="ap-btn" href="/g/">用語集のほかの言葉</a><a class="ap-btn" href="/a/">すべての記事</a></p>')
    ld = {"@context": "https://schema.org", "@type": "DefinedTerm", "name": term, "description": e.get("short", ""), "url": canonical,
          "inDefinedTermSet": SITE + "/g/"}
    if aliases:
        ld["alternateName"] = aliases
    body = '<div class="ap">\n' + "\n".join(parts) + "\n</div>"
    return page(title=title, desc=desc, canonical=canonical, og_type="article", og_image=OG_DEFAULT,
                ld=[ld, crumbs_ld(crumbs)], body=body)


def g_index_page(terms, by_term, slugs) -> str:
    """g/index.html：用語集（よみの最初の字で、あ行・か行…・英数字に分ける）。"""
    canonical = SITE + "/g/"
    crumbs = [("有権者", SITE + "/"), ("用語集", canonical)]
    rows = {}
    for e in terms:
        rows.setdefault(kana_row(e.get("yomi") or e["term"]), []).append(e)
    order = [n for n, _ in KANA_ROWS] + [OTHER_ROW]
    names = [n for n in order if n in rows]
    jump = "".join(f'<a href="#r-{i}">{esc(n)}</a>' for i, n in enumerate(order) if n in rows)
    secs = []
    for i, n in enumerate(order):
        if n not in rows:
            continue
        es = sorted(rows[n], key=lambda e: ((e.get("yomi") or e["term"]), e["term"]))
        lis = "".join(f'\n  <li><a href="{esc(g_href(slugs[e["term"]]))}">{esc(e["term"])}</a>'
                      f'<span class="g-count">{len(by_term[e["term"]])}件</span><span class="g-sum">{esc(cut(e.get("short")))}</span></li>' for e in es)
        secs.append(f'<section class="g-row" aria-labelledby="r-{i}"><h2 class="section-title" id="r-{i}">{esc(n)}<small>{len(es)}語</small></h2>'
                    f'<ul class="g-list">{lis}\n</ul></section>')
    body = f"""<div class="ap">
{crumbs_nav(crumbs)}
<h1 class="page-title">用語集</h1>
<p class="lead">記事に出てくる言葉（{len(terms)}語）の簡単な説明です。言葉を押すと、くわしい説明と、その言葉が出てくる記事の一覧がひらきます。数字は記事の数です。</p>
<nav class="chips g-jump" aria-label="行で選ぶ">{jump}</nav>
{chr(10).join(secs)}
</div>"""
    desc = short_desc(f"有権者の記事に出てくる政治・行政の言葉{len(terms)}語を、初めての人にもわかるように短く説明した用語集です。" + "・".join(names) + "で引けます。")
    ld = {"@context": "https://schema.org", "@type": "DefinedTermSet", "name": "有権者の用語集", "url": canonical,
          "hasDefinedTerm": [{"@type": "DefinedTerm", "name": e["term"], "url": SITE + g_href(slugs[e["term"]])} for e in terms]}
    return page(title="用語集（政治・行政の言葉をやさしく）｜有権者", desc=desc, canonical=canonical, og_type="website",
                og_image=OG_DEFAULT, ld=[ld, crumbs_ld(crumbs)], body=body)


def assign_slugs(terms) -> dict:
    """用語 → ファイル名。重なったら -2, -3 …（Windows は大文字・小文字を区別しないので小文字で比べる）。"""
    taken, out = {"index"}, {}
    for e in terms:
        base = term_slug(e["term"])
        s, n = base, 2
        while s.lower() in taken or s.lower() in WIN_RESERVED:
            s, n = f"{base}-{n}", n + 1
        taken.add(s.lower())
        out[e["term"]] = s
    return out


# ── 公約チェッカー（pledges.html）の文字だけの一覧：pledges.js と同じ言葉・同じ計算 ──

STAGE_NAMES = ["動きなし", "国会で求めた", "具体案を出した", "決定に近づいた", "実現した"]  # pledges.js の STAGES の name
MAX_STAGE = 4


def stage_of(p) -> int:
    try:
        v = float(p.get("stage") or 0)
    except (TypeError, ValueError):
        v = 0
    if v != v:  # NaN
        v = 0
    return max(0, min(MAX_STAGE, int(math.floor(v + 0.5))))  # JS の Math.round と同じ（0.5 は切り上げ）


def theme_rate(ps):
    if not ps:
        return None
    return int(math.floor(sum(stage_of(p) for p in ps) / len(ps) / MAX_STAGE * 100 + 0.5))


def fmt_day(iso) -> str:
    return fmt_date(iso) if re.match(r"^\d{4}-\d{2}-\d{2}$", str(iso or "")) else esc(iso)


def ext_link(url, label) -> str:
    """pledges.js の ext と同じ：http(s) の URL ならリンク、そうでなければ文字だけ（label はエスケープ済み）。"""
    return f'<a href="{esc(url)}" target="_blank" rel="noopener">{label}</a>' if re.match(r"^https?://", str(url or "")) else label


def static_pledges(data) -> str:
    """pledges.html の <!-- STATIC-PLEDGES --> のあいだ：テーマ（h2）→ 党（h3）→ 公約の文・段階・今の状況・出典・行動の記録。"""
    if not isinstance(data, dict):
        return ""
    themes = [t for t in data.get("themes") or [] if isinstance(t, dict)]
    parties = sorted([p for p in data.get("parties") or [] if isinstance(p, dict)], key=lambda p: -(p.get("seats_shugiin") or 0))
    el = data.get("election") or {}
    meta = f'対象：{ext_link(el.get("url"), esc(el.get("name") or ""))}' + (f'（{fmt_day(el["date"])}投開票）' if el.get("date") else "")
    if data.get("updated"):
        meta += f' ・ 更新 {fmt_day(data["updated"])}'
    secs = []
    for t in themes:
        blocks = []
        for p in parties:
            ps = [x for x in p.get("pledges") or [] if isinstance(x, dict) and x.get("theme") == t.get("id")]
            if not ps:
                continue
            items = []
            for pl in ps:
                st, src = stage_of(pl), pl.get("src") or {}
                acts = sorted([a for a in pl.get("actions") or [] if isinstance(a, dict)], key=lambda a: str(a.get("date")))
                tl = "".join(
                    f'<li><p class="pc-tl-head"><time datetime="{esc(a.get("date"))}">{fmt_day(a.get("date"))}</time><span class="pc-tl-type">{esc(a.get("type"))}</span>'
                    + (f'<span class="pc-tl-stage">段階{esc(a["stage"])}</span>' if isinstance(a.get("stage"), (int, float)) and not isinstance(a.get("stage"), bool) else "")
                    + f'</p><p class="pc-tl-text">{esc(a.get("text"))}</p>'
                    + (f'<p class="source">出典：{ext_link(a["src"].get("url"), "「" + esc(a["src"].get("title")) + "」" + ("（" + esc(a["src"]["site"]) + "）" if a["src"].get("site") else "") + " ↗")}</p>'
                       if isinstance(a.get("src"), dict) else "") + "</li>" for a in acts)
                items.append(
                    f'<li class="sp-pledge"><p class="sp-text">{esc(pl.get("text"))}</p>'
                    + (f'<blockquote class="pc-quote">「{esc(pl["quote"])}」</blockquote>' if pl.get("quote") else "")
                    + f'<p class="source">公約の出典：{ext_link(src.get("url"), "「" + esc(src.get("title")) + "」" + esc(src.get("page") or "") + " ↗")}</p>'
                    + f'<p class="pc-stage-now">段階 <b>{st}</b> / {MAX_STAGE}：{esc(STAGE_NAMES[st])}</p>'
                    + (f'<p class="pc-status"><span>今の状況</span>{esc(pl["status"])}</p>' if pl.get("status") else "")
                    + '<h4 class="pc-tl-title">行動の記録</h4>'
                    + (f'<ol class="pc-timeline">{tl}</ol>' if tl else '<p class="pc-empty">出典つきで確かめられた行動は、まだありません。</p>')
                    + "</li>")
            side = esc(p.get("side"))
            blocks.append(f'\n<section class="sp-party"><h3>{esc(p.get("name"))}<span class="sp-side">{side}</span></h3>'
                          f'<p class="sp-score">このテーマの達成率 <b>{theme_rate(ps)}%</b>（公約{len(ps)}件の段階の平均 ÷ 4）</p>'
                          f'<ol class="sp-list">{"".join(items)}</ol></section>')
        if blocks:
            secs.append(f'\n<section class="sp-theme"><h2>{esc(t.get("name"))}</h2>{"".join(blocks)}\n</section>')
    dummy = '<p class="pc-dummy-inline">ダミーデータです（実在の公約・行動ではありません）</p>' if data.get("_dummy") else ""
    return (f'<section class="pc-section static-pledges-wrap" aria-label="公約の一覧（文字だけ）">\n<details class="static-pledges">'
            f'<summary>公約の一覧（文字だけで見る）</summary>\n<div class="sp-body">\n<p class="sp-meta">{meta}</p>{dummy}'
            '\n<p class="sp-note">上の画面と同じ内容を、テーマごと・党ごとに文字だけで並べています（衆議院の議席が多い順）。段階の決め方は「達成率の決め方」のとおりです。</p>'
            f'{"".join(secs)}\n</div>\n</details>\n</section>')


FEED_MAX = 50


def rfc3339(it) -> str:
    """Atom の日時（秒まで・時差つき）。日付しかないときはその日の 0 時（日本時間）。"""
    for k in ("updated_at", "published_at"):
        v = str(it.get(k) or "")
        m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(:\d{2})?([+-]\d{2}:\d{2}|Z)$", v)
        if m:
            return m.group(1) + (m.group(2) or ":00") + m.group(3)
    return str(it.get("date", ""))[:10] + "T00:00:00+09:00"


def published3339(it) -> str:
    return rfc3339({"published_at": it.get("published_at"), "date": it.get("date")})


def feed(items, ctx: Ctx) -> str:
    """feed.xml（Atom 1.0）：国と地方の新しい記事 50件。id はページの URL（変わらない）。"""
    top = items[:FEED_MAX]
    updated = max((rfc3339(it) for it in top), default="2026-01-01T00:00:00+09:00")
    entries = []
    for it in top:
        url = f"{SITE}/a/{it['id']}.html"
        cat = ctx.name(it, ctx.gid(it))
        entries.append(f"""  <entry>
    <title>{esc(it.get("title"))}</title>
    <link rel="alternate" type="text/html" href="{esc(url)}"/>
    <id>{esc(url)}</id>
    <published>{published3339(it)}</published>
    <updated>{rfc3339(it)}</updated>
""" + (f'    <category term="{esc(cat)}"/>\n' if cat else "") + f"""    <summary>{esc(it.get("summary"))}</summary>
  </entry>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="ja">
  <title>有権者</title>
  <subtitle>官邸・各府省と都道府県の発表を、出典リンクつきで要約したニュース</subtitle>
  <link rel="alternate" type="text/html" href="{SITE}/"/>
  <link rel="self" type="application/atom+xml" href="{SITE}/feed.xml"/>
  <id>{SITE}/</id>
  <updated>{updated}</updated>
  <author><name>有権者</name><uri>{SITE}/</uri></author>
{chr(10).join(entries)}
</feed>
"""


def sitemap(items, extra=()) -> str:
    """決まったページ + /a/ + 全記事 + extra（[(パス, lastmod)]：/m/・/p/・/g/ とその中のページ）。"""
    urls = [f"  <url><loc>{SITE}{p}</loc></url>" for p in FIXED_PAGES]
    newest = latest(items)
    urls.append(f"  <url><loc>{SITE}/a/</loc>" + (f"<lastmod>{newest}</lastmod>" if newest else "") + "</url>")
    for it in items:
        lm = lastmod(it)
        urls.append(f"  <url><loc>{SITE}/a/{esc(it['id'])}.html</loc>" + (f"<lastmod>{esc(lm)}</lastmod>" if lm else "") + "</url>")
    for path, lm in extra:
        urls.append(f"  <url><loc>{esc(SITE + path)}</loc>" + (f"<lastmod>{esc(lm)}</lastmod>" if lm else "") + "</url>")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n"


def build(root) -> dict:
    """ページを作り直す。結果 {pages, written, deleted, skipped} を返す（skipped = ファイル名に使えない id）。"""
    root = Path(root)
    news = read_json(root / "data" / "news.json", [])
    local = read_json(root / "data" / "local_news.json", [])
    ctx = Ctx(read_json(root / "data" / "sources.json", []), read_json(root / "data" / "prefectures.json", []))
    for it in local:
        it.setdefault("pref", "")  # 地方の印（local_news.json の記事はどれも pref を持つはず）

    skipped, items, seen = [], [], set()
    for it in news + local:
        aid = str(it.get("id", ""))
        if not SAFE_ID.match(aid) or aid in seen or aid == "index" or not it.get("date"):
            skipped.append(aid)
            continue
        seen.add(aid)
        items.append(it)
    items.sort(key=sort_key, reverse=True)

    # 府省ごと・都道府県ごとの一覧（記事が1件以上あるところだけ。also・pref_also の記事も入れる）
    national = [it for it in items if not ctx.is_local(it)]
    m_groups = []
    for s in ctx.sources:
        if s.get("hidden"):
            continue
        its = [it for it in national if s["id"] in ctx.ids(it)]
        if its and SAFE_ID.match(s["id"]):
            m_groups.append((s, its))
    by_pref = {}
    for p in ctx.prefs:
        its = [it for it in items if ctx.is_local(it) and p["id"] in ctx.ids(it)]
        if its and SAFE_ID.match(p["id"]):
            by_pref[p["id"]] = its
    ctx.m_pages = {s["id"] for s, _ in m_groups}
    ctx.p_pages = set(by_pref)
    pref_home = {s.get("id"): s.get("home") for s in read_json(root / "data" / "pref_sources.json", []) if isinstance(s, dict)}

    # 用語：記事ごとに出てくる用語。1件以上の記事に出てくる用語だけ g/ のページを作る
    gl = Glossary(read_json(root / "data" / "glossary.json", []))
    gp = read_json(root / "data" / "glossary_pages.json", {})  # 任意（Hermes があとで足す説明文）
    gp = gp if isinstance(gp, dict) else {}
    terms_of = {it["id"]: gl.find(it) for it in items}
    by_term = {}
    for it in items:
        for t in terms_of[it["id"]]:
            by_term.setdefault(t, []).append(it)
    g_terms = [e for e in gl.entries if e["term"] in by_term]
    g_terms = list({e["term"]: e for e in g_terms}.values())  # 同じ term が2回あっても1ページ
    slugs = assign_slugs(g_terms)
    g_order = {e["term"]: i for i, e in enumerate(g_terms)}
    related = related_items(items, ctx, terms_of)

    # 前・次：同じ府省（地方は同じ県）の中で日付順
    by_group = {}
    for it in items:
        by_group.setdefault((ctx.is_local(it), ctx.gid(it)), []).append(it)

    o = Out(root)
    (root / "a").mkdir(exist_ok=True)
    keep = {"a": {"index.html"}, "m": {"index.html"}, "p": {"index.html"}, "g": {"index.html"}}
    for grp in by_group.values():
        for i, it in enumerate(grp):  # grp は新しい順
            newer = grp[i - 1] if i > 0 else None
            older = grp[i + 1] if i + 1 < len(grp) else None
            words = [(t, slugs[t]) for t in terms_of[it["id"]] if t in slugs]
            o.write(f"a/{it['id']}.html", article_page(it, ctx, newer, older, words, related[it["id"]]))
            keep["a"].add(f"{it['id']}.html")

    for e in g_terms:
        t = e["term"]
        co = {}
        for it in by_term[t]:
            for u in terms_of[it["id"]]:
                if u != t and u in slugs:
                    co[u] = co.get(u, 0) + 1
        related = sorted(co, key=lambda u: (-co[u], g_order[u]))[:8]
        extra = gp.get(t) if isinstance(gp.get(t), dict) else {}
        o.write(f"g/{slugs[t]}.html", term_page(e, slugs[t], by_term[t], related, extra, ctx, slugs))
        keep["g"].add(f"{slugs[t]}.html")
    o.write("g/index.html", g_index_page(g_terms, by_term, slugs))
    o.write("a/index.html", index_page(items, ctx))

    for s, its in m_groups:
        o.write(f"m/{s['id']}.html", group_page("m", s, its, ctx, s.get("home", ""), s.get("site", "")))
        keep["m"].add(f"{s['id']}.html")
    o.write("m/index.html", m_index_page(m_groups, ctx))
    for pid, its in by_pref.items():
        p = ctx.pref[pid]
        home = pref_home.get(pid) or ""
        o.write(f"p/{pid}.html", group_page("p", p, its, ctx, home, f"{p['name']}の公式ホームページ ↗" if home else ""))
        keep["p"].add(f"{pid}.html")
    o.write("p/index.html", p_index_page(by_pref, ctx))
    o.inject("ministries.html", "STATIC-LIST", static_ministries(m_groups))
    o.inject("local.html", "STATIC-LIST", static_prefs(by_pref, ctx))
    pledges = read_json(root / "data" / "pledges.json", None)
    if pledges is not None:
        o.inject("pledges.html", "STATIC-PLEDGES", static_pledges(pledges))

    # もう無い記事・府省・県のページは消す（index.html は残す）
    deleted, removed = [], []
    for d, names in keep.items():
        for f in sorted((root / d).glob("*.html")):
            if f.name not in names:
                f.unlink()
                removed.append(f"{d}/{f.name}")
                if d == "a":
                    deleted.append(f.name)
    extra = [("/m/", latest(national))] + [(f"/m/{s['id']}.html", latest(its)) for s, its in m_groups]
    extra += [("/p/", latest([it for its in by_pref.values() for it in its]))] + [(f"/p/{pid}.html", latest(its)) for pid, its in by_pref.items()]
    extra += [("/g/", latest([it for its in by_term.values() for it in its]))] + [(g_href(slugs[e["term"]]), latest(by_term[e["term"]])) for e in g_terms]
    o.write("sitemap.xml", sitemap(items, extra))
    o.write("feed.xml", feed(items, ctx))
    urls = [page_url(r) for r in o.changed + removed if r.endswith(".html")]
    return {"pages": len(items), "written": o.written, "deleted": deleted, "removed": removed, "skipped": skipped,
            "changed": o.changed, "urls": urls,
            "counts": {"a": len(keep["a"]) - 1, "m": len(m_groups), "p": len(by_pref), "g": len(g_terms)},
            "terms": {aid: [slugs[t] for t in ts if t in slugs] for aid, ts in terms_of.items()}}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    r = build(Path(__file__).resolve().parent.parent)
    c = r["counts"]
    print(f"記事ページ {r['pages']}件・府省 {c['m']}・都道府県 {c['p']}・用語 {c['g']}（書きかえ {r['written']}ファイル）")
    if r["deleted"]:
        print("消したページ（公開をやめた記事）:", ", ".join(r["deleted"]))
    if r["skipped"]:
        print("飛ばした記事（id がファイル名に使えない・重複・日付なし）:", ", ".join(r["skipped"]))
