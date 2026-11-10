"""有権者：47都道府県の報道発表（新着）を集める。国の collect.py の地方版。

使い方:
    python tools/collect_local.py                      # 新着を drafts/local_candidates.json に足す
    python tools/collect_local.py --days 7             # 何日前までを対象にするか（初期値 3）
    python tools/collect_local.py --pref tokyo,kanagawa  # 県をしぼる（id は data/pref_sources.json）
    python tools/collect_local.py --dry-run            # 書き込まずに見るだけ（候補も表示）
    python tools/collect_local.py --report out.txt     # 表示した内容をファイルにも書く

- 読むのは data/pref_sources.json の feeds（県の公式サイトの報道発表。RSS・Atom・HTML一覧・JSON）。
- 栃木県・東京都はRSSの再配布・サイト構築が規約で禁止（事前申請）なので、HTML一覧から読む。
- 行儀よく：リクエストは1つずつ、間に1秒あける、1回20秒で打ち切り、全体は --max-seconds（初期値600秒）まで。
  愛知県は bot 対策があるので cookie を持って1回だけ取り、弾かれたら報告して飛ばす（再試行しない）。
- 既に見たURLは drafts/local_seen.json に記録し、二度と候補に出さない。
- 要約はこのスクリプトでは作らない（候補から選んで、自分の言葉で要約して drafts/drafts.json に書く）。
"""
import argparse
import datetime as dt
import html
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import JST, clean, fetch, norm_date as norm_date_rfc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "data" / "pref_sources.json"
DRAFTS = ROOT / "drafts"
SEEN = DRAFTS / "local_seen.json"
CANDIDATES = DRAFTS / "local_candidates.json"
TIMEOUT = 20
INTERVAL = 1.0

# 新着（全体）しかない県で落とすもの。feeds の "exclude": "@noise" で使う（"@noise|ほかの語" のように足せる）
# パブコメの「意見募集」は有権者に関係があるので残す（結果の公表は落とす）
NOISE = ("入札|落札|開札|発注|見積|プロポーザル|指名停止|随意契約|業務委託|委託業務|施工監理|RFI|公募|(?<!意見)募集|採用|任用|試験|求人|"
         "イベント|講座|講演会|講習|セミナー|研修|教室|説明会|相談会|フェア|フェスタ|フェス|まつり|祭り|"
         "コンテスト|コンクール|展示|パネル展|企画展|ツアー|体験|ワークショップ|"
         "パブリックコメント.*結果|意見募集.*結果|縦覧|県公報|譲渡|休診|様式|申請書|よくある質問|トップページ")


class TimeUp(Exception):
    pass


class Fetcher:
    """リクエストを1つずつ・1秒あけて出す。全体の時間を超えたら TimeUp。"""

    def __init__(self, max_seconds):
        self.deadline = time.monotonic() + max_seconds
        self.last = 0.0
        self.count = 0

    def get(self, url, encoding="", cookies=False):
        if time.monotonic() > self.deadline:
            raise TimeUp("時間切れ（--max-seconds）")
        wait = self.last + INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())) if cookies else None
        try:
            self.count += 1
            text = fetch(url, timeout=TIMEOUT, encoding=encoding, opener=opener)
        finally:
            self.last = time.monotonic()
        if cookies and re.search(r"Incapsula|_Incapsula_Resource|Request unsuccessful", text[:3000]):
            raise RuntimeError("bot 対策で弾かれた（Imperva）。今回は飛ばす")
        return text


# ---------- 日付 ----------

def norm_date(s):
    """RSS・HTMLのいろいろな日付を YYYY-MM-DD（日本時間）にする。読めなければ ""。"""
    s = (s or "").strip()
    if re.match(r"\d{4}-\d{2}-\d{2}T\d", s) and re.search(r"(Z|[+-]\d{2}:?\d{2})$", s):
        try:
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(JST).strftime("%Y-%m-%d")
        except ValueError:
            pass
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        return ymd(*m.groups())
    m = re.search(r"(\d{4})\)?\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", s)
    if m:
        return ymd(*m.groups())
    m = re.search(r"令和\s*(\d{1,2}|元)\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", s)
    if m:
        return ymd(2018 + (1 if m.group(1) == "元" else int(m.group(1))), m.group(2), m.group(3))
    return norm_date_rfc(s)


def ymd(y, m, d):
    try:
        return dt.date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return ""


def guess_year(m, d, today):
    """年のない「11月9日」に年をつける（今日より1か月以上先なら去年）。"""
    for y in (today.year, today.year - 1):
        s = ymd(y, m, d)
        if s and s <= (today + dt.timedelta(days=31)).isoformat():
            return s
    return ""


def month_vars(day):
    fy = day.year if day.month >= 4 else day.year - 1
    return {"yyyy": f"{day.year:04d}", "yy": f"{day.year % 100:02d}", "mm": f"{day.month:02d}", "m": str(day.month),
            "fy": str(fy), "fy_reiwa": str(fy - 2018), "reiwa": str(day.year - 2018)}


def months_in(cutoff, today):
    """対象期間に入る月（新しい順）。月別ページの県は、月をまたぐと先月のページも読む。"""
    out, d = [], today
    while True:
        if (d.year, d.month) not in [(x.year, x.month) for x in out]:
            out.append(d)
        if d <= cutoff:
            return out
        d -= dt.timedelta(days=1)


# ---------- 読み取り ----------

A_RE = r'<a\b[^>]*?\bhref\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a\s*>'
DATE_RE = (r"(?P<iso>(\d{4})-(\d{1,2})-(\d{1,2}))"
           r"|(?P<west>(\d{4})\)?\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日)"
           r"|(?P<wareki>令和\s*(?:\d{1,2}|元)\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)"
           r"|(?<![\d年])(?P<md>(\d{1,2})\s*月\s*(\d{1,2})\s*日)")
TOKEN = re.compile(f"(?P<a>{A_RE})|{DATE_RE}", re.S | re.I)
PDF_TAIL = re.compile(r"\s*[（(]\s*(PDF|pdf|ＰＤＦ)[^）)]*[）)]|\s*[（(]\s*[\d,.]+\s*[KMkm]i?B\s*[）)]|\s*\[PDF[^\]]*\]")


def norm_url(url):
    """二重スラッシュや ?ref=rss を取って、同じ記事が別URLにならないようにする。"""
    p = urlsplit(url)
    path = re.sub(r"/{2,}", "/", p.path)
    query = re.sub(r"(^|&)ref=rss(&|$)", r"\1", p.query).strip("&")
    return p._replace(path=path, query=query).geturl()


def title_of(raw):
    t = PDF_TAIL.sub("", clean(raw))
    return re.sub(r"\s*New!?$", "", t).strip()


def cut(text, feed):
    if feed.get("start") and feed["start"] in text:
        text = text[text.index(feed["start"]):]
    if feed.get("end") and feed["end"] in text:
        text = text[:text.index(feed["end"])]
    return text


def parse_rss(text, base, feed, today):
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text.lstrip("﻿"))
    items = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        root = None
    if root is not None:
        for el in root.iter():
            if el.tag.split("}")[-1] not in ("item", "entry"):
                continue
            title = link = date = ""
            for c in el:
                ct = c.tag.split("}")[-1]
                if ct == "title":
                    title = clean(c.text or "")
                elif ct == "link" and not link:
                    link = (c.text or "").strip() or (c.get("href", "") if c.get("rel", "alternate") == "alternate" else "")
                elif ct in ("date", "pubDate", "published", "updated", "issued") and not date:
                    date = norm_date(c.text or "")
            link = link or el.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", "")
            if title and link:
                items.append({"title": title, "url": urljoin(base, link), "date": date})
        return items
    # 壊れたXMLのとき（& がそのまま等）は正規表現で拾う
    for m in re.finditer(r"<(item|entry)\b.*?</\1>", text, re.S):
        b = m.group(0)
        t = re.search(r"<title[^>]*>(.*?)</title>", b, re.S)
        lk = re.search(r"<link[^>]*>(.*?)</link>", b, re.S) or re.search(r'<link[^>]*href="([^"]+)"', b)
        d = re.search(r"<(?:dc:date|pubDate|published|updated)[^>]*>(.*?)<", b, re.S)
        if t and lk:
            items.append({"title": clean(re.sub(r"<!\[CDATA\[|\]\]>", "", t.group(1))), "url": urljoin(base, lk.group(1).strip()),
                          "date": norm_date(d.group(1)) if d else ""})
    return items


def parse_dated(text, base, feed, today, undated=False):
    """HTMLの一覧：リンクと日付を文書の順に読み、リンクには直前（date_after なら直後）の日付をつける。
    日付のつかないリンク（最初の日付より前のメニューなど）は捨てる（undated=True なら残す）。
    feed の start/end で読む範囲を、link（URL）・skip（タイトル）の正規表現でリンクをしぼる。"""
    link_re = re.compile(feed.get("link", "."))
    skip_re = re.compile(feed["skip"]) if feed.get("skip") else None
    from_url = re.compile(feed["date_from_url"]) if feed.get("date_from_url") else None
    tokens = []
    for m in TOKEN.finditer(cut(text, feed)):
        if m.group("a"):
            href = html.unescape(m.group(2)).strip()
            if href.startswith(("#", "javascript:", "mailto:")):
                continue
            url = urljoin(base, href)
            title = title_of(m.group(3))
            if link_re.search(url) and len(title) >= 4 and not (skip_re and skip_re.search(title)):
                tokens.append(("a", url, title))
        else:
            if m.group("md"):
                d = guess_year(m.group(m.re.groupindex["md"] + 1), m.group(m.re.groupindex["md"] + 2), today)
            else:
                d = norm_date(m.group(0))
            if d:
                tokens.append(("d", d))
    items, seen = [], set()
    for i, tk in enumerate(tokens):
        if tk[0] != "a" or tk[1] in seen:
            continue
        seen.add(tk[1])
        rng = tokens[i + 1:] if feed.get("date_after") else reversed(tokens[:i])
        date = next((t[1] for t in rng if t[0] == "d"), "")
        if from_url:
            u = from_url.search(tk[1])
            date = ymd(u.group(1)[:4], u.group(1)[4:6], u.group(1)[6:8]) if u else date
        if date or undated:
            items.append({"title": tk[2], "url": tk[1], "date": date})
    return items


def parse_links(text, base, feed, today):
    """日付のない一覧（鹿児島・沖縄）：上から max_items 件。新着かどうかは local_seen.json との差分で決める。"""
    items = [dict(it, date="") for it in parse_dated(text, base, feed, today, undated=True)]
    return items[:feed.get("max_items", 15)]


def parse_fukui(text, base, feed, today):
    """福井県：kintone kViewer の内部JSON（records[]。詳細ページは __kviewer_record_code__）。"""
    m = re.match(r"(https://[^/]+/public/)internal/api/records/([0-9a-f]+)/", feed["url"])
    detail = f"{m.group(1)}{m.group(2)}/detail/"
    items = []
    for r in json.loads(text).get("records", []):
        title = (r.get("タイトル") or {}).get("value", "")
        date = (r.get("投込日") or {}).get("value", "")
        code, rid = r.get("__kviewer_record_code__", ""), (r.get("$id") or {}).get("value", "")
        if title and code:
            # 詳細URLの暗号トークンは取るたびに変わることがあるので、既読の判定は $id で行う
            items.append({"title": clean(title), "url": detail + code, "date": norm_date(date), "key": f"fukui-kviewer:{rid}"})
    return items


def parse_nagasaki(text, base, feed, today):
    """長崎県：/data/press.json（items[] は未ソート、日付は ISODate('…Z') でUTC）。"""
    items = []
    for it in json.loads(text).get("items", []):
        m = re.search(r"ISODate\('(.+?)'\)", it.get("date", ""))
        raw = m.group(1) if m else it.get("date", "")
        mm = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})T(.*)", raw)  # 月日がゼロ埋めでないことがある
        if mm:
            raw = f"{int(mm.group(1)):04d}-{int(mm.group(2)):02d}-{int(mm.group(3)):02d}T{mm.group(4)}"
        if it.get("title") and it.get("link"):
            items.append({"title": clean(it["title"]), "url": urljoin(base, it["link"]), "date": norm_date(raw)})
    items.sort(key=lambda x: x["date"], reverse=True)
    return items


PARSERS = {"rss": parse_rss, "atom": parse_rss, "dated": parse_dated, "links": parse_links,
           "fukui_kintone": parse_fukui, "nagasaki_json": parse_nagasaki}


def feed_urls(feed, months, fetcher, cache):
    """月別ページの県は URL を作る（{yyyy}{mm} など）か、索引ページから探す（discover）。"""
    if feed.get("discover"):
        disc = feed["discover"]
        if disc["url"] not in cache:
            cache[disc["url"]] = fetcher.get(disc["url"])
        page, urls = cache[disc["url"]], []
        for d in months:
            v = month_vars(d)
            part = page
            if disc.get("start"):
                s = disc["start"].format(**v)
                if s not in page:
                    continue
                part = page[page.index(s) + len(s):]
                if disc.get("until"):  # 次の年度の見出しの手前まで（今月がまだないとき去年の同じ月を拾わない）
                    u = re.search(disc["until"].format(**v), part)
                    part = part[:u.start()] if u else part
            text_re = re.compile(disc["text"].format(**v))
            for m in re.finditer(A_RE, part, re.S | re.I):
                if text_re.search(clean(m.group(2))):
                    urls.append(urljoin(disc["url"], html.unescape(m.group(1))))
                    break
        if not urls:
            raise RuntimeError(f"索引ページに今月のリンクが見つからない（{disc['url']}）")
        return list(dict.fromkeys(urls))
    if "{" in feed["url"]:
        return list(dict.fromkeys(feed["url"].format(**month_vars(d)) for d in months))
    return [feed["url"]]


def match(pattern, s):
    return bool(pattern) and re.search(pattern.replace("@noise", NOISE), s)


def collect_pref(src, fetcher, cutoff, today, cache):
    """1つの県の feeds を読む。戻り値: (候補, 失敗の一覧, 注意の一覧, 一覧の件数, 除外した件数)"""
    months = months_in(cutoff, today)
    lo, hi = cutoff.isoformat(), (today + dt.timedelta(days=1)).isoformat()
    out, errors, notes, total, dropped = [], [], [], 0, 0
    for feed in src["feeds"]:
        parser = PARSERS[feed.get("parser") or feed["kind"]]
        try:
            urls = feed_urls(feed, months, fetcher, cache)
        except TimeUp:
            raise
        except Exception as e:
            errors.append(f'{feed["label"]}: {short(e)}')
            continue
        for url in urls:
            try:
                items = parser(fetcher.get(url, feed.get("encoding", ""), feed.get("cookies", False)), url, feed, today)
            except TimeUp:
                raise
            except Exception as e:
                errors.append(f'{feed["label"]}: {short(e)}（{url}）')
                continue
            if not items:
                errors.append(f'{feed["label"]}: 0件（読み取れない・形が変わった？ {url}）')
            elif len(items) >= 10 and all(lo <= it["date"] <= hi for it in items):
                notes.append(f'{feed["label"]}: 一覧の{len(items)}件が全部期間内（もっと前の分は載っていない。取りこぼしがあるかも）')
            total += len(items)
            for it in items:
                if it["date"] and not (lo <= it["date"] <= hi):
                    continue
                on = it["url"] if feed.get("include_on") == "url" else it["title"]
                if (feed.get("include") and not match(feed["include"], on)) or match(feed.get("exclude", ""), it["title"]):
                    dropped += 1
                    continue
                it["url"] = norm_url(it["url"])
                out.append(dict(it, source_label=feed["label"]))
    return out, errors, notes, total, dropped


def write_json(path, data):
    """途中で切れても壊れないように、一時ファイルに書いてから置き換える。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def read_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit(f"{path.relative_to(ROOT).as_posix()} が壊れている（{e}）。直すか消してからもう一度")


def short(e):
    s = str(e) or e.__class__.__name__
    return s if len(s) < 120 else s[:117] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--pref", default="", help="カンマ区切りの id（例 tokyo,kanagawa）")
    ap.add_argument("--dry-run", action="store_true", help="書き込まずに表示だけ")
    ap.add_argument("--max-seconds", type=int, default=600)
    ap.add_argument("--report", default="", help="表示をこのファイルにも書く（UTF-8）")
    args = ap.parse_args()

    lines = []

    def say(s=""):
        lines.append(s)
        print(s, flush=True)

    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    if args.pref:
        want = {x.strip() for x in args.pref.split(",") if x.strip()}
        unknown = want - {s["id"] for s in sources}
        if unknown:
            sys.exit(f"知らない id: {', '.join(sorted(unknown))}")
        sources = [s for s in sources if s["id"] in want]
    seen = set(read_json(SEEN, []))
    old = read_json(CANDIDATES, [])
    today = dt.datetime.now(JST).date()
    cutoff = today - dt.timedelta(days=args.days)
    fetcher, cache = Fetcher(args.max_seconds), {}
    started = time.monotonic()
    say(f"地方の新着 {today}（{cutoff} 以降, {len(sources)}都道府県{', 見るだけ' if args.dry_run else ''}）")

    new, ok, failed = [], 0, []
    for src in sources:
        try:
            items, errors, notes, total, dropped = collect_pref(src, fetcher, cutoff, today, cache)
        except Exception as e:  # 時間切れ・設定の書き間違いなど。その県だけ失敗にして次へ
            failed.append(src["name"])
            say(f'{src["name"]}: 失敗（{short(e) if isinstance(e, TimeUp) else e.__class__.__name__ + ": " + short(e)}）')
            continue
        fresh = []
        for it in items:
            key = it.pop("key", re.sub(r"^http://", "https://", it["url"]))  # http と https の同じ記事を1つに
            if key in seen:
                continue
            seen.add(key)
            fresh.append({"pref": src["id"], "pref_name": src["name"], "title": it["title"], "url": it["url"],
                          "date": it["date"], "source_label": it["source_label"], "site": src["site"]})
        new += fresh
        msg = f'{src["name"]}: 新着 {len(fresh)}（一覧 {total}件' + (f"・除外 {dropped}件" if dropped else "") + "）"
        if errors:
            msg += " / 失敗: " + " / ".join(errors)
        if notes:
            msg += " / 注意: " + " / ".join(notes)
        if errors and not total:
            failed.append(src["name"])
        else:
            ok += 1
        say(msg)
        if args.dry_run:
            for it in fresh:
                say(f'    {it["date"] or "日付なし"}  {it["title"]}  {it["url"]}')

    say(f"合計 新着 {len(new)}件 / 取得できた {ok}都道府県・失敗 {len(failed)}" + (f"（{'・'.join(failed)}）" if failed else "")
        + f" / リクエスト {fetcher.count}回・{time.monotonic() - started:.0f}秒")
    if not args.dry_run:
        DRAFTS.mkdir(exist_ok=True)
        merged = sorted(old + new, key=lambda x: x.get("date", ""), reverse=True)
        write_json(CANDIDATES, merged)
        write_json(SEEN, sorted(seen))
        say(f"→ {CANDIDATES.relative_to(ROOT).as_posix()}（未処理の候補 計{len(merged)}件）")
    if args.report:
        Path(args.report).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    main()
