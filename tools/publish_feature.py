"""有権者：特集を公開する（Roy の OK のあとに使う）

使い方: python tools/publish_feature.py <slug>            公開して GitHub に送る
        python tools/publish_feature.py <slug> --no-push  コミットまで（push と IndexNow はしない）
  1. drafts/features/<slug>.json を読む（形を確かめる。おかしければ何も変えずに止まる）
  2. data/features.json に入れる（同じ slug があれば置きかえ。published_at は最初のまま、updated_at を今に）
  3. build_pages.build() で t/ ・sitemap.xml・feed.xml を作り直す
  4. git add data/features.json t sitemap.xml feed.xml → commit「特集を公開：<題名>」→ push（git の見つけ方・push は review_server.py と同じ）
  5. push できたら IndexNow で知らせる（tools/indexnow.py。失敗しても公開は止めない）
"""
import argparse
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
JST = dt.timezone(dt.timedelta(hours=9))
SITE = "https://yukensha.com"


def load_tool(name):
    spec = importlib.util.spec_from_file_location(f"pf_{name}", HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def read(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def write(p: Path, data):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def check(d: dict, slug: str):
    """下書きの形を確かめる。おかしければ ValueError（何も保存しない）。"""
    if not isinstance(d, dict):
        raise ValueError("下書きの中身が {…} の形ではありません")
    if d.get("slug") != slug:
        raise ValueError(f"下書きの slug（{d.get('slug')!r}）がファイル名（{slug}）と違います")
    for k in ("title", "lead"):
        if not isinstance(d.get(k), str) or not d[k].strip():
            raise ValueError(f"{k} がありません")
    secs = d.get("sections")
    if not isinstance(secs, list) or not any(isinstance(s, dict) and s.get("h2") for s in secs):
        raise ValueError("sections（見出し h2 のある章）が1つもありません")
    for k in ("timeline", "faq", "related_article_ids", "related_terms", "tags"):
        if k in d and not isinstance(d[k], list):
            raise ValueError(f"{k} はリストにしてください")


def merge(features: list, d: dict, now: str):
    """同じ slug は置きかえ（published_at は最初のまま）。新しいものは published_at = now。(一覧, 書き直しか) を返す。"""
    old = next((f for f in features if isinstance(f, dict) and f.get("slug") == d["slug"]), None)
    d = dict(d)
    d["published_at"] = old.get("published_at") or now if old else now
    d["updated_at"] = now
    rest = [f for f in features if f is not old]
    out = [d] + rest
    out.sort(key=lambda f: str(f.get("published_at") or "") if isinstance(f, dict) else "", reverse=True)
    return out, old is not None


def publish(slug: str, root=ROOT, push=True, now=None) -> str:
    """特集を1件公開する。結果をやさしい日本語で返す。形がおかしいときは ValueError。"""
    root = Path(root)
    bp = load_tool("build_pages")
    if not bp.SAFE_ID.match(slug or "") or slug.lower() == "index":
        raise ValueError(f"slug に使えない文字があります: {slug!r}（英数字・- ・_ だけ）")
    src = root / "drafts" / "features" / f"{slug}.json"
    if not src.is_file():
        raise ValueError(f"下書きがありません: drafts/features/{slug}.json")
    d = read(src, None)
    check(d, slug)
    now = now or dt.datetime.now(JST).isoformat(timespec="seconds")

    path = root / "data" / "features.json"
    features = read(path, [])
    if not isinstance(features, list):
        raise ValueError("data/features.json の形がおかしい（[…] ではない）")
    features, updated = merge(features, d, now)
    write(path, features)
    result = bp.build(root)
    lines = [f"特集を{'書き直し' if updated else '公開'}しました：{d['title']}（t/{slug}.html）"]

    rs = load_tool("review_server")  # git の見つけ方（Hermes に付いている git も探す）と git() をそのまま使う
    rs.ROOT = root
    if not (root / ".git").exists():
        return "\n".join(lines + ["（git のフォルダではないので、コミットはしていません）"])
    rs.git("add", "-A", "--", "data/features.json", "t", "sitemap.xml", "feed.xml")
    code, out = rs.git("commit", "-m", f"特集を公開：{d['title']}")
    if code != 0:
        return "\n".join(lines + [f"（コミットできませんでした：{out[-200:]}）"])
    lines.append("コミットしました。")
    if not push:
        lines.append("--no-push なので GitHub には送っていません（あとで git push）。")
        return "\n".join(lines)
    if not rs.git("remote")[1]:
        lines.append("（GitHub とつながっていないので push はしていません）")
        return "\n".join(lines)
    code, out = rs.git("push")
    if code != 0:
        lines.append(f"GitHubへの送信に失敗: {out[-200:]}")
        return "\n".join(lines)
    lines.append("1分ほどで公開サイトに反映されます。")
    urls = [f"{SITE}/t/{slug}.html", f"{SITE}/t/", f"{SITE}/", f"{SITE}/feed.xml"] + (result.get("urls") or [])
    try:
        lines.append(load_tool("indexnow").submit(urls))
    except Exception as e:
        lines.append(f"IndexNow：送れませんでした（{type(e).__name__}）")
    return "\n".join(lines)


def main(argv=None, root=ROOT) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="drafts/features/<slug>.json の特集を公開する")
    ap.add_argument("slug")
    ap.add_argument("--no-push", action="store_true", help="コミットまで（push・IndexNow はしない）")
    a = ap.parse_args(argv)
    try:
        print(publish(a.slug, root, push=not a.no_push))
    except ValueError as e:
        print("公開しませんでした：" + str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
