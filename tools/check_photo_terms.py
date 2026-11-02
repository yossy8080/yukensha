"""写真の利用ルールが書かれていないサイトを毎日チェックする。

使い方:  python tools/check_photo_terms.py
  - WATCH のページを取得し、「自由に使ってよい」系の記載（政府標準利用規約・PDL・CC BY など）を探す
  - 前回の結果は drafts/photo_terms_state.json に保存（公開されないフォルダ）
  - 出力の1行目: 「許可あり」「許可なし」「取得失敗」のどれか（サイトごと）
"""
import hashlib
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "drafts" / "photo_terms_state.json"

# 写真をまだ使えないサイト（許可の記載が出たら使い始める）
WATCH = [
    {
        "id": "bousai",
        "name": "防災庁",
        "pages": ["https://www.bousai.go.jp/notice.html"],
    },
]

# 「自由に使ってよい」に当たる記載
ALLOW = [
    "政府標準利用規約", "公共データ利用規約", "PDL1.0", "PDL 1.0", "Public Data License",
    "クリエイティブ・コモンズ", "CC BY", "CC-BY", "出典を記載", "出典を明記", "自由に利用", "自由に複製",
    "複製、公衆送信、翻訳・変形等の翻案等、自由に",
]
# 関連しそうな記載（変化を知らせるだけ）
WATCHWORDS = ["著作権", "利用規約", "コンテンツの利用", "二次利用", "写真", "画像"]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def page_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "ignore")
    links = re.findall(r'href="([^"]*(?:copyright|riyou|kiyaku|terms|policy|chosaku)[^"]*)"', raw, re.I)
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t).strip(), sorted(set(links))


def main():
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    for w in WATCH:
        try:
            texts, links = [], set()
            for u in w["pages"]:
                t, l = page_text(u)
                texts.append(t)
                links.update(l)
            text = " ".join(texts)
        except Exception as e:  # noqa: BLE001
            print(f"{w['name']}: 取得失敗（{type(e).__name__}）")
            continue
        hits = [k for k in ALLOW if k in text]
        words = [k for k in WATCHWORDS if k in text]
        digest = hashlib.sha256(text.encode()).hexdigest()[:16]
        prev = state.get(w["id"], {})
        changed = prev.get("hash") not in (None, digest)
        status = "許可あり" if hits else "許可なし"
        print(f"{w['name']}: {status}" + ("（ページに変更あり）" if changed else "（変化なし）" if prev else "（初回）"))
        if hits:
            print("  見つかった記載:", "、".join(hits))
            for k in hits[:3]:
                i = text.find(k)
                print("  …" + text[max(0, i - 120): i + 200] + "…")
        if words:
            print("  関連語:", "、".join(words))
        if links:
            print("  規約らしいリンク:", " ".join(links))
        state[w["id"]] = {"hash": digest, "status": status, "hits": hits}
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
