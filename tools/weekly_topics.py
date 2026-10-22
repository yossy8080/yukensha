"""今週の論点：公開済みの記事を、タグ（テーマ）ごとに数える（Hermesが「今週の論点」を下書きするときに使う）。

使い方: python tools/weekly_topics.py [--days 7]
政府の発表の「件数」でテーマを並べる。どのテーマを取り上げるかの主観を減らすため。
"""
import argparse
import collections
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JST = dt.timezone(dt.timedelta(hours=9))

ap = argparse.ArgumentParser()
ap.add_argument("--days", type=int, default=7)
a = ap.parse_args()
today = dt.datetime.now(JST).date()
since = (today - dt.timedelta(days=a.days - 1)).isoformat()
news = [n for n in json.loads((ROOT / "data/news.json").read_text(encoding="utf-8")) if n["date"] >= since]
print(f"対象：{since}〜{today.isoformat()}　記事{len(news)}件")
by = collections.defaultdict(list)
for n in news:
    for t in n.get("tags", []):
        by[t].append(n)
for tag, items in sorted(by.items(), key=lambda kv: -len(kv[1])):
    mins = sorted({n["ministry"] for n in items})
    print(f"\n## {tag}（{len(items)}件／{len(mins)}府省：{', '.join(mins)}）")
    for n in sorted(items, key=lambda n: n["date"]):
        star = "★" if n.get("featured") else " "
        print(f"  {star} {n['date']} {n['id']}  {n['title']}")
