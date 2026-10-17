"""ページ本文をテキストで取り出す（Hermesが要約を書くときに使う）。

使い方: python tools/fetch_page.py URL [URL ...] [--max 4000]
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import fetch, clean  # noqa: E402


def main_text(html_text: str) -> str:
    t = re.sub(r"(?is)<(script|style|noscript|header|footer|nav)[^>]*>.*?</\1>", " ", html_text)
    for pat in (r'(?is)id="main_content"[^>]*>(.*)', r'(?is)<main[^>]*>(.*)</main>',
                r'(?is)<article[^>]*>(.*)</article>',
                r'(?is)id="(?:contents|main|maincontents|contents-body)"[^>]*>(.*)'):
        m = re.search(pat, t)
        if m and len(clean(m.group(1))) > 200:
            t = m.group(1)
            break
    t = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</tr>|</dt>|</dd>", "\n", t)
    lines = [clean(x) for x in t.split("\n")]
    return "\n".join(x for x in lines if x)


if __name__ == "__main__":
    args = sys.argv[1:]
    mx = 4000
    if "--max" in args:
        i = args.index("--max")
        mx = int(args[i + 1])
        del args[i:i + 2]
    for u in args:
        print("=" * 8, u)
        try:
            print(main_text(fetch(u))[:mx])
        except Exception as e:
            print("取得失敗:", e)
