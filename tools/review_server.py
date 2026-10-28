"""有権者：確認用サーバー（Royが下書きを確認して公開するためのもの）

起動: python tools/review_server.py   →  ブラウザで http://localhost:5600/review
- http://localhost:5600/          サイト本体のプレビュー（公開済みの記事だけ）
- http://localhost:5600/review    下書きの確認ページ（公開する／しないを選ぶ）

「公開する」を押すと:
  1. 選んだ下書きを data/news.json に追加（公開済みになる）
  2. 「公開しない」を選んだものは drafts/rejected.json に移す
  3. git にコミットする（GitHubとつながっていれば push もする）
自分のPCの中だけで動き、外からはアクセスできません（127.0.0.1 のみ）。
"""
import datetime as dt
import json
import os
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEWS = ROOT / "data" / "news.json"
DRAFTS = ROOT / "drafts" / "drafts.json"
REJECTED = ROOT / "drafts" / "rejected.json"
UNPUBLISHED = ROOT / "drafts" / "unpublished.json"
OPINION = ROOT / "data" / "opinion.json"
OPINION_DRAFTS = ROOT / "drafts" / "opinion_drafts.json"
REVIEW_HTML = Path(__file__).resolve().parent / "review.html"
PORT = int(os.environ.get("YUKENSHA_PORT", "5600"))
JST = dt.timezone(dt.timedelta(hours=9))
EDITABLE = ("title", "summary", "points", "featured", "tags", "explain", "refs")


def clean(k, v):
    """explain / refs は辞書のリストだけ通す（文字の項目だけ残し、空の行は捨てる）。"""
    keys = {"explain": ("q", "a"), "refs": ("title", "site", "url")}.get(k)
    if not keys:
        return v
    out = []
    for x in v if isinstance(v, list) else []:
        if isinstance(x, dict):
            item = {f: str(x.get(f) or "").strip() for f in keys}
            if any(item.values()):
                out.append(item)
    return out


def apply_edits(item: dict, e: dict):
    for k in EDITABLE:
        if k in e:
            v = clean(k, e[k])
            if k in ("explain", "refs") and not v:
                item.pop(k, None)  # 空にしたら項目ごと消す（前と同じ表示に戻る）
            else:
                item[k] = v



def read(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def write(p: Path, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def find_git():
    """RoyのPCにはgitが入っていないので、Hermesに付いているgitを探す。"""
    import glob
    import shutil
    g = shutil.which("git")
    if g:
        return g
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", "tools")
    for pat in ("git-*/cmd/git.exe", "git-*/mingw64/bin/git.exe"):
        hits = sorted(glob.glob(os.path.join(base, pat)))
        if hits:
            return hits[-1]
    return None


GIT = find_git()


def git(*args):
    if not GIT:
        return 1, "gitが見つかりません"
    try:
        r = subprocess.run([GIT, "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8")
        return r.returncode, (r.stdout + r.stderr).strip()
    except OSError as e:
        return 1, str(e)


def publish(body: dict) -> dict:
    drafts = read(DRAFTS, [])
    news = read(NEWS, [])
    approve, reject = set(body.get("approve", [])), set(body.get("reject", []))
    edits = body.get("edits", {})
    now = dt.datetime.now(JST).isoformat(timespec="seconds")

    published, rejected, remaining = [], [], []
    for d in drafts:
        apply_edits(d, edits.get(d["id"], {}))
        if d["id"] in approve:
            d["published_at"] = now
            published.append(d)
        elif d["id"] in reject:
            d["rejected_at"] = now
            rejected.append(d)
        else:
            remaining.append(d)

    known = {n["id"] for n in news}
    news += [p for p in published if p["id"] not in known]
    news.sort(key=lambda n: (n["date"], n.get("published_at", "")), reverse=True)
    write(NEWS, news)
    write(DRAFTS, remaining)
    if rejected:
        write(REJECTED, read(REJECTED, []) + rejected)

    msg = save_git(f"記事を{len(published)}件公開（{now[:10]}）") if published else ""
    return {"published": len(published), "rejected": len(rejected), "remaining": len(remaining), "git": msg}


def save_git(message: str) -> str:
    """data/news.json をコミットしてGitHubに送る。結果をやさしい日本語で返す。"""
    if not (ROOT / ".git").exists():
        return ""
    git("add", "data/news.json")
    code, out = git("commit", "-m", message)
    if code != 0:
        return "（記録用のコミットはできませんでしたが、保存は完了しています）"
    msg = "保存しました。"
    if git("remote")[1]:
        code, out = git("push")
        msg += " 1分ほどで公開サイトに反映されます。" if code == 0 else f" GitHubへの送信に失敗: {out[-200:]}"
    return msg


def publish_opinion(body: dict) -> dict:
    """オピニオン（今週の論点など）の下書きを公開する／しない。"""
    drafts = read(OPINION_DRAFTS, [])
    posts = read(OPINION, [])
    approve, reject = set(body.get("approve", [])), set(body.get("reject", []))
    edits = body.get("edits", {})
    now = dt.datetime.now(JST).isoformat(timespec="seconds")
    published, remaining, rejected = [], [], 0
    for d in drafts:
        for k in ("title", "lead", "body"):
            if k in edits.get(d["id"], {}):
                d[k] = edits[d["id"]][k]
        if d["id"] in approve:
            d["published_at"] = now
            published.append(d)
        elif d["id"] in reject:
            rejected += 1
        else:
            remaining.append(d)
    known = {x["id"] for x in posts}
    posts = sorted(posts + [x for x in published if x["id"] not in known], key=lambda x: x["date"], reverse=True)
    write(OPINION, posts)
    write(OPINION_DRAFTS, remaining)
    msg = ""
    if published and (ROOT / ".git").exists():
        git("add", "data/opinion.json")
        msg = save_git(f"オピニオンを{len(published)}件公開（{now[:10]}）")
    return {"published": len(published), "rejected": rejected, "remaining": len(remaining), "git": msg}


def manage(body: dict) -> dict:
    """公開済みの記事を直す／非公開に戻す。"""
    news = read(NEWS, [])
    edits = body.get("edits", {})
    unpublish = set(body.get("unpublish", []))
    now = dt.datetime.now(JST).isoformat(timespec="seconds")
    edited, removed, keep = 0, [], []
    for n in news:
        e = edits.get(n["id"])
        if e:
            apply_edits(n, e)
            n["updated_at"] = now
            edited += 1
        if n["id"] in unpublish:
            n["unpublished_at"] = now
            removed.append(n)
        else:
            keep.append(n)
    write(NEWS, keep)
    if removed:
        write(UNPUBLISHED, read(UNPUBLISHED, []) + removed)
    parts = []
    if edited:
        parts.append(f"{edited}件を修正")
    if removed:
        parts.append(f"{len(removed)}件を非公開")
    msg = save_git("公開済みの記事：" + "・".join(parts) + f"（{now[:10]}）") if parts else ""
    return {"edited": edited, "unpublished": len(removed), "total": len(keep), "git": msg}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, data, code=200):
        b = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.split("?")[0] in ("/review", "/review/"):
            b = REVIEW_HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path == "/api/drafts":
            self._json(read(DRAFTS, []))
        elif self.path == "/api/opinion_drafts":
            self._json(read(OPINION_DRAFTS, []))
        elif self.path == "/api/news":
            self._json(read(NEWS, []))
        elif self.path == "/api/config":
            self._json(read(ROOT / "data" / "config.json", {}))
        elif self.path.startswith("/drafts/") or self.path.startswith("/tools/") or self.path.startswith("/.git"):
            self.send_error(404)  # 下書きや道具はサイトとしては見せない
        else:
            super().do_GET()

    def do_POST(self):
        actions = {"/api/publish": publish, "/api/manage": manage, "/api/publish_opinion": publish_opinion}
        if self.path not in actions:
            return self.send_error(404)
        n = int(self.headers.get("Content-Length", 0))
        try:
            self._json(actions[self.path](json.loads(self.rfile.read(n) or b"{}")))
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"確認ページ: http://localhost:{PORT}/review   サイト: http://localhost:{PORT}/   （止めるときは Ctrl+C）")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
