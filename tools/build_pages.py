"""有権者：記事ごとのページ（a/<記事id>.html）・記事一覧（a/index.html）・sitemap.xml を作る

使い方: python tools/build_pages.py
- data/news.json（国）と data/local_news.json（地方）の記事を1件ずつ、本文の入った静的な HTML にする（Google に1件ずつ載るように）
- 公開をやめた記事のページ（a/ にあって、もう JSON に無い id）は消す。a/index.html は消さない
- sitemap.xml を作り直す（決まったページ + /a/ + 全記事）
- 入力の JSON には書き込まない。確認ページ（tools/review_server.py）で公開・修正すると自動で呼ばれる
- 書くのは中身が変わったファイルだけ（git の差分が出ないように）
"""
import datetime as dt
import html
import json
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


def photo_html(p) -> str:
    w, h = p.get("width"), p.get("height")
    size = f' width="{w}" height="{h}" style="aspect-ratio:{w}/{h}"' if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0 else ""
    link = f'（<a href="{esc(p["page_url"])}" target="_blank" rel="noopener">出典ページ ↗</a>）' if re.match(r"^https?://", str(p.get("page_url") or "")) else ""
    cap = esc(p.get("credit")) + link
    src = "/" + str(p["src"]).lstrip("/")
    return (f'<figure class="photo"><img src="{esc(src)}" alt="{esc(p.get("alt"))}" decoding="async"{size}>'
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
    qa = [x for x in it.get("explain") or [] if isinstance(x, dict) and (x.get("q") or x.get("a"))]
    if not qa:
        return ""
    return '<section class="explain" aria-label="背景の説明"><dl>' + "".join(f"<dt>{esc(x.get('q'))}</dt><dd>{esc(x.get('a'))}</dd>" for x in qa) + "</dl></section>"


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

    ph = [photo_html(p) for p in photos]
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
  {(('<p class="points-label" data-no-gloss>今回のポイント</p>' if ex else "") + f'<ul class="points">{pts}</ul>') if pts else ""}
  {"".join(ph[1:])}
  {source_line(it)}{refs_line(it)}
  {f'<p class="tags">{tags}</p>' if tags else ""}
</article>
{words_html(words)}
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
    return page(title="記事一覧｜有権者", desc=desc, canonical=SITE + "/a/", og_type="website", og_image=OG_DEFAULT, ld=[ld], body=body)


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


def sitemap(items) -> str:
    urls = [f"  <url><loc>{SITE}{p}</loc></url>" for p in FIXED_PAGES]
    newest = max((lastmod(it) for it in items), default="", key=lambda s: s[:10] + s)
    urls.append(f"  <url><loc>{SITE}/a/</loc>" + (f"<lastmod>{newest}</lastmod>" if newest else "") + "</url>")
    for it in items:
        lm = lastmod(it)
        urls.append(f"  <url><loc>{SITE}/a/{esc(it['id'])}.html</loc>" + (f"<lastmod>{esc(lm)}</lastmod>" if lm else "") + "</url>")
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
            o.write(f"a/{it['id']}.html", article_page(it, ctx, newer, older, words))
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

    # もう無い記事・府省・県のページは消す（index.html は残す）
    deleted, removed = [], []
    for d, names in keep.items():
        for f in sorted((root / d).glob("*.html")):
            if f.name not in names:
                f.unlink()
                removed.append(f"{d}/{f.name}")
                if d == "a":
                    deleted.append(f.name)
    o.write("sitemap.xml", sitemap(items))
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
    print(f"記事ページ {r['pages']}件（書きかえ {r['written']}ファイル）")
    if r["deleted"]:
        print("消したページ（公開をやめた記事）:", ", ".join(r["deleted"]))
    if r["skipped"]:
        print("飛ばした記事（id がファイル名に使えない・重複・日付なし）:", ", ".join(r["skipped"]))
