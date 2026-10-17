"""有権者：官邸・各府省の新着情報を集める。

使い方:
    python tools/collect.py            # 新着だけ drafts/candidates.json に書く
    python tools/collect.py --days 5   # 何日前までを対象にするか（初期値 3）

- 一次情報（官邸・府省の公式サイト）だけを読む。
- 首相官邸のRSSは再配布が禁止されているので、官邸は「新着情報」のHTMLページから読む。
- 既に見たURLは drafts/seen.json に記録し、二度と候補に出さない。
- 要約はこのスクリプトでは作らない（Hermes が候補を読み、要約して drafts/drafts.json に書く）。
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "data" / "sources.json"
DRAFTS = ROOT / "drafts"
SEEN = DRAFTS / "seen.json"
CANDIDATES = DRAFTS / "candidates.json"
JST = dt.timezone(dt.timedelta(hours=9))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130 Safari/537.36 yukensha-collector")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    head = raw[:200].decode("ascii", "ignore")
    m = re.search(r'encoding=["\']([\w-]+)', head)
    encs = ([m.group(1)] if m else []) + ["utf-8", "cp932", "euc-jp"]
    for enc in encs:
        try:
            return raw.decode("cp932" if enc.lower() in ("shift_jis", "sjis", "x-sjis") else enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def norm_date(s: str) -> str:
    """いろいろな日付表記を YYYY-MM-DD にする。"""
    s = (s or "").strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return "-".join(m.groups())
    m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", s)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    try:  # RSS 2.0 の pubDate
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).astimezone(JST).strftime("%Y-%m-%d")
    except Exception:
        return ""


def parse_feed(text: str, base: str):
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    root = ET.fromstring(text)
    items = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        title = link = date = ""
        for c in el:
            ct = c.tag.split("}")[-1]
            if ct == "title":
                title = clean(c.text or "")
            elif ct == "link":
                link = (c.text or "").strip() or c.get("href", "")
            elif ct in ("date", "pubDate", "updated", "published") and not date:
                date = norm_date(c.text or "")
        if not link:
            link = el.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", "")
        if title and link:
            items.append({"title": title, "url": urljoin(base, link), "date": date})
    return items


def parse_kantei(text: str, base: str):
    items = []
    for m in re.finditer(r'<li class="list-new__item">(.*?)</li>', text, re.S):
        block = m.group(1)
        a = re.search(r'href="([^"]+)"', block)
        d = re.search(r'datetime="([\d-]+)"', block)
        label = re.search(r'<span class="label[^"]*">(.*?)</span>', block, re.S)
        desc = re.search(r'list-new__description">(.*?)</p>', block, re.S)
        if a and desc:
            items.append({
                "title": clean(desc.group(1)),
                "url": urljoin(base, a.group(1)),
                "date": d.group(1) if d else "",
                "category": clean(label.group(1)) if label else "",
            })
    return items


def parse_mofa(text: str, base: str):
    today = dt.datetime.now(JST).date()
    items = []
    body = text.split('id="pressrelease"', 1)[-1]
    for m in re.finditer(r'<dt class="list-title">\s*(\d{1,2})月(\d{1,2})日付\s*</dt>\s*<dd>(.*?)</dd>', body, re.S):
        mo, d, block = int(m.group(1)), int(m.group(2)), m.group(3)
        y = today.year if mo <= today.month else today.year - 1
        for a in re.finditer(r'<a href="([^"]+)">(.*?)</a>', block, re.S):
            items.append({"title": clean(a.group(2)), "url": urljoin(base, a.group(1)),
                          "date": f"{y:04d}-{mo:02d}-{d:02d}"})
    return items


def parse_env(text: str, base: str):
    items = []
    parts = re.split(r'p-press-release-list__heading">', text)[1:]
    for part in parts:
        date = norm_date(part[:40])
        for m in re.finditer(r'<li class="c-news-link__item">(.*?)</li>', part, re.S):
            block = m.group(1)
            tag = re.search(r'c-tag[^"]*">(.*?)</span>', block, re.S)
            a = re.search(r'<a href="([^"]+)" class="c-news-link__link">(.*?)</a>', block, re.S)
            if a:
                items.append({"title": clean(a.group(2)), "url": urljoin(base, a.group(1)),
                              "date": date, "category": clean(tag.group(1)) if tag else ""})
    return items


def parse_meti(text: str, base: str):
    # 経産省のAtomフィードは更新が止まっているので、ニュースリリース一覧のHTMLから読む
    items = []
    for m in re.finditer(r'<div class="left img_box">\s*<img[^>]*alt="([^"]*)"[^>]*>\s*</div>\s*'
                         r'<div class="left txt_box"><p>([^<]+)</p><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text, re.S):
        cat, date, href, title = m.groups()
        items.append({"title": clean(title), "url": urljoin(base, href),
                      "date": norm_date(date), "category": clean(cat)})
    return items


PARSERS = {"rss": parse_feed, "meti_html": parse_meti, "kantei_html": parse_kantei, "mofa_html": parse_mofa, "env_html": parse_env}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    args = ap.parse_args()

    DRAFTS.mkdir(exist_ok=True)
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    seen = set(json.loads(SEEN.read_text(encoding="utf-8"))) if SEEN.exists() else set()
    cutoff = (dt.datetime.now(JST).date() - dt.timedelta(days=args.days)).isoformat()

    new, errors = [], []
    for src in sources:
        try:
            items = PARSERS[src["type"]](fetch(src["url"]), src["url"])
        except Exception as e:  # 1つのサイトが落ちても他は続ける
            errors.append(f'{src["name"]}: {e}')
            continue
        count = 0
        for it in items:
            if it["url"] in seen or (it["date"] and it["date"] < cutoff):
                continue
            seen.add(it["url"])
            it.update({"ministry": src["id"], "ministry_name": src["name"], "site": src["site"]})
            new.append(it)
            count += 1
        print(f'{src["name"]}: {len(items)}件中 新着{count}件')

    # 前回の候補でまだ処理していないものも残す
    old = json.loads(CANDIDATES.read_text(encoding="utf-8")) if CANDIDATES.exists() else []
    merged = old + new
    merged.sort(key=lambda x: x.get("date", ""), reverse=True)
    CANDIDATES.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    SEEN.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")
    print(f"新着 合計{len(new)}件 → {CANDIDATES.relative_to(ROOT)}（未処理の候補 計{len(merged)}件）")
    for e in errors:
        print("取得失敗:", e, file=sys.stderr)


if __name__ == "__main__":
    main()
