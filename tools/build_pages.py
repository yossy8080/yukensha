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


def write_if_changed(p: Path, text: str) -> bool:
    if p.exists() and p.read_text(encoding="utf-8") == text:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return True


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
    <a class="site-logo" href="/index.html">有権者</a>
    <nav class="site-nav" aria-label="メニュー">
      <ul>
        <li><a href="/index.html#stream"{cur("stream")}>府省</a></li>
        <li><a href="/index.html#opinion">オピニオン</a></li>
        <li><a href="/index.html#local"{cur("local")}>地方</a></li>
        <li><a href="/index.html#pledges" aria-label="公約チェッカー">公約<span class="nav-long">チェッカー</span></a></li>
        <li><a href="/about.html" aria-label="このサイトについて"><span class="nav-long">このサイトについて</span><span class="nav-short">概要</span></a></li>
      </ul>
    </nav>
  </div>
</header>"""


FOOTER = f"""<footer>
  <div class="wrap">
    <p>有権者 — 要約はAI（Hermes）が下書きし、運営者が確認してから公開しています。誤りに気づいたら<a href="{FORM}" target="_blank" rel="noopener">お問い合わせフォーム</a>からお知らせください。</p>
    <p>各記事は、政府のウェブサイト（公共データ利用規約 PDL1.0 等）の情報をもとに、有権者が要約・加工して作成したものです。正確な内容は必ず出典をご確認ください。</p>
    <p class="footer-links"><a href="/about.html">このサイトについて</a> ・ <a href="/privacy.html">プライバシーポリシー</a> ・ <a href="/a/">記事一覧</a> ・ <a href="{FORM}" target="_blank" rel="noopener">お問い合わせ</a></p>
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
{lds}<link rel="icon" href="{ICON}">
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
        return f"/local.html?p={gid}" if self.is_local(it) else f"/ministries.html?m={gid}"

    def view_href(self, it):
        # 地方の記事は local.html のリーダー（トップの 3D は国の記事だけ）
        return f"/local.html?p={it['pref']}#a={it['id']}" if self.is_local(it) else f"/#a={it['id']}"


def article_page(it, ctx: Ctx, newer, older) -> str:
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
    crumb_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(crumbs)],
    }

    labels = []
    for x in ctx.ids(it):
        n = ctx.name(it, x)
        if n:
            labels.append(f'<a class="kicker-ministry" href="{esc(ctx.list_href(it, x))}">{esc(n)}</a>')
    ph = [photo_html(p) for p in photos]
    pts = "".join(f"<li>{esc(p)}</li>" for p in it.get("points") or [])
    tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in it.get("tags") or [])
    ex = explain_html(it)
    date = str(it.get("date", ""))

    crumb_nav = ('<nav class="ap-crumbs" aria-label="現在地"><ol>'
                 '<li><a href="/index.html">有権者</a></li>'
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
  <p class="kicker"><time datetime="{esc(date)}">{fmt_date(date)}</time>{'<span class="sep">・</span>'.join(labels)}</p>
  <h1 class="headline">{esc(it.get("title"))}</h1>
  {ph[0] if ph else ""}
  <p class="summary">{esc(it.get("summary"))}</p>
  {ex}{quotes_html(it)}
  {(('<p class="points-label" data-no-gloss>今回のポイント</p>' if ex else "") + f'<ul class="points">{pts}</ul>') if pts else ""}
  {"".join(ph[1:])}
  {source_line(it)}{refs_line(it)}
  {f'<p class="tags">{tags}</p>' if tags else ""}
</article>
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
            '府省ごとに見るときは<a href="/ministries.html">府省別の記事一覧</a>、都道府県は<a href="/local.html">地方</a>へ。</p>\n'
            + "\n".join(secs))
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "記事一覧｜有権者", "url": SITE + "/a/",
          "isPartOf": {"@type": "WebSite", "name": "有権者", "url": SITE + "/"}}
    return page(title="記事一覧｜有権者", desc=desc, canonical=SITE + "/a/", og_type="website", og_image=OG_DEFAULT, ld=[ld], body=body)


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

    # 前・次：同じ府省（地方は同じ県）の中で日付順
    by_group = {}
    for it in items:
        by_group.setdefault((ctx.is_local(it), ctx.gid(it)), []).append(it)

    out = root / "a"
    out.mkdir(exist_ok=True)
    written = 0
    for grp in by_group.values():
        for i, it in enumerate(grp):  # grp は新しい順
            newer = grp[i - 1] if i > 0 else None
            older = grp[i + 1] if i + 1 < len(grp) else None
            written += write_if_changed(out / f"{it['id']}.html", article_page(it, ctx, newer, older))
    written += write_if_changed(out / "index.html", index_page(items, ctx))

    deleted = []
    for f in sorted(out.glob("*.html")):
        if f.name != "index.html" and f.stem not in seen:
            f.unlink()
            deleted.append(f.name)
    written += write_if_changed(root / "sitemap.xml", sitemap(items))
    return {"pages": len(items), "written": written, "deleted": deleted, "skipped": skipped}


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
