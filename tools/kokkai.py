"""国会会議録から、ある会議での総理・官房長官の発言の全文を取り出す（Hermesが引用を選ぶときに使う）。

使い方: python tools/kokkai.py ISSUE_ID [内閣総理大臣|内閣官房長官] [--max 6000]
ISSUE_ID は candidates.json の issue_id。会議録の発言は著作権法40条で自由に利用できる（出典は明記する）。
"""
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import fetch  # noqa: E402

args = sys.argv[1:]
mx = 6000
if "--max" in args:
    i = args.index("--max"); mx = int(args[i + 1]); del args[i:i + 2]
issue = args[0]
pos = args[1] if len(args) > 1 else "内閣総理大臣"
q = urllib.parse.urlencode({"issueID": issue, "speakerPosition": pos, "maximumRecords": 100, "recordPacking": "json"})
data = json.loads(fetch("https://kokkai.ndl.go.jp/api/speech?" + q))
out = []
for s in data.get("speechRecord", []):
    out.append(f"--- {s['date']} {s['nameOfHouse']} {s['nameOfMeeting']} {s['issue']} 発言{s['speechOrder']} {s['speaker']}\n"
               f"URL: {s['speechURL']}\n{s['speech']}")
print("\n".join(out)[:mx] if out else "発言が見つかりません")
