"""有権者：IndexNow で、変わったページを検索エンジン（Bing など）にすぐ知らせる

使い方:
  python tools/indexnow.py --all             sitemap.xml の全部の URL を送る
  python tools/indexnow.py --urls URL ...    指定した URL だけ送る
  python tools/indexnow.py --all --dry-run   送らずに、送る内容だけ表示する
- 鍵（KEY）は公開してよいもの。サイトの一番上に <鍵>.txt を置き、中身は鍵だけ（検索エンジンがそれを見て本人確認する）
- 確認ページ（tools/review_server.py）で公開・修正して push できたあとに自動で呼ばれる。失敗しても公開は止めない
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HOST = "yukensha.com"
SITE = "https://" + HOST
KEY = "cd11b7311202af032809200bf75680c1"
KEY_LOCATION = f"{SITE}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_URLS = 10000
TIMEOUT = 15
ROOT = Path(__file__).resolve().parent.parent


def clean(urls) -> list:
    """このサイトの URL だけ・重なりなし・順番はそのまま・最大 10000件。"""
    out, seen = [], set()
    for u in urls or []:
        u = str(u or "").strip()
        if (u == SITE or u.startswith(SITE + "/")) and u not in seen:
            seen.add(u)
            out.append(u)
    return out[:MAX_URLS]


def payload(urls) -> dict:
    return {"host": HOST, "key": KEY, "keyLocation": KEY_LOCATION, "urlList": clean(urls)}


def submit(urls, dry_run=False) -> str:
    """URL を IndexNow に送る。結果を短い日本語で返す（例外は出さない）。dry_run=True なら送らない。"""
    try:
        body = payload(urls)
        n = len(body["urlList"])
        if not n:
            return "IndexNow：送る URL がありません"
        if dry_run:
            return f"IndexNow（送らずに確認）：{n}件"
        req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            code = r.status
        if code in (200, 202):
            return f"IndexNow：{n}件を検索エンジンに知らせました"
        return f"IndexNow：送信の結果が {code} でした（{n}件）"
    except urllib.error.HTTPError as e:
        why = {400: "形がおかしい", 403: "鍵が確認できない（鍵のファイルが公開されていない？）", 422: "URL がこのサイトのものではない", 429: "送りすぎ"}.get(e.code, "")
        return f"IndexNow：送れませんでした（{e.code} {why}）".replace(" ）", "）")
    except Exception as e:  # ネットにつながらない・時間切れなど
        return f"IndexNow：送れませんでした（{type(e).__name__}）"


def sitemap_urls(root=ROOT) -> list:
    tree = ET.parse(Path(root) / "sitemap.xml")
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [e.text.strip() for e in tree.getroot().findall("s:url/s:loc", ns) if e.text]


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="IndexNow で URL を検索エンジンに知らせる")
    ap.add_argument("--all", action="store_true", help="sitemap.xml の全部の URL")
    ap.add_argument("--urls", nargs="+", default=[], help="送る URL")
    ap.add_argument("--dry-run", action="store_true", help="送らずに表示だけ")
    a = ap.parse_args(argv)
    urls = (sitemap_urls() if a.all else []) + a.urls
    if not urls:
        ap.error("--all か --urls を指定してください")
    if a.dry_run:
        for u in clean(urls):
            print(u)
    print(submit(urls, dry_run=a.dry_run))


if __name__ == "__main__":
    main()
