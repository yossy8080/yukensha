"""有権者：確認用サーバー（Royが下書きを確認して公開するためのもの）

起動: python tools/review_server.py   →  ブラウザで http://localhost:5600/review
- http://localhost:5600/          サイト本体のプレビュー（公開済みの記事だけ）
- http://localhost:5600/review    下書きの確認ページ（公開する／しないを選ぶ）

「公開する」を押すと:
  1. 選んだ下書きを data/news.json に追加（公開済みになる）
     すでに公開中の記事と同じ id の下書きは「書き直し」として、その記事を置きかえる
     地方の下書き（"scope": "local" と "pref": 都道府県id）は data/local_news.json に入れる（news.json には入れない）
  2. 「公開しない」を選んだものは drafts/rejected.json に移す
  3. 記事ごとのページ（a/）と sitemap.xml を作り直す（tools/build_pages.py。公開済みの記事の修正・非公開に戻すときも）
  4. git にコミットする（記事が使っている写真 assets/photos/ と a/・sitemap.xml も一緒に。GitHubとつながっていれば push もする）
自分のPCの中だけで動き、外からはアクセスできません（127.0.0.1 のみ）。
公開の振り分けの確認: python tools/check_review_local.py（一時フォルダのコピーで試す。本物の data/ には触らない）
"""
import datetime as dt
import json
import os
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEWS = ROOT / "data" / "news.json"
LOCAL_NEWS = ROOT / "data" / "local_news.json"
PREFECTURES = ROOT / "data" / "prefectures.json"
DRAFTS = ROOT / "drafts" / "drafts.json"
REJECTED = ROOT / "drafts" / "rejected.json"
UNPUBLISHED = ROOT / "drafts" / "unpublished.json"
OPINION = ROOT / "data" / "opinion.json"
OPINION_DRAFTS = ROOT / "drafts" / "opinion_drafts.json"
REVIEW_HTML = Path(__file__).resolve().parent / "review.html"
PORT = int(os.environ.get("YUKENSHA_PORT", "5600"))
JST = dt.timezone(dt.timedelta(hours=9))
EDITABLE = ("title", "summary", "points", "featured", "tags", "explain", "refs", "photos")
PHOTO_DIR = "assets/photos/"


def clean_photos(v, need_file=True) -> list:
    """photos は辞書のリストだけ通す。写真のファイルは assets/photos/ の中にあるものだけ（.. は使えない）。
    おかしいものがあれば保存せずにエラーにする（どの写真か分かるように返す）。
    need_file=False（下書きのまま残すとき）は、ファイルがまだ無くてもよい（ほかの下書きの公開を止めないため）。"""
    if not isinstance(v, list):
        raise ValueError("photos はリストにしてください")
    out = []
    for x in v:
        if not isinstance(x, dict):
            raise ValueError("photos の中身は {src, alt, …} の形にしてください")
        src = str(x.get("src") or "").strip().replace("\\", "/")
        if not src.startswith(PHOTO_DIR) or ".." in src or (need_file and not (ROOT / src).is_file()):
            raise ValueError(f"写真のファイルがありません（assets/photos/ の中に置いてください）: {src}")
        item = {"src": src}
        for f in ("alt", "credit", "page_url", "license"):
            item[f] = str(x.get(f) or "").strip()
        if not item["page_url"].startswith(("https://", "http://")):
            item["page_url"] = ""  # javascript: などのリンクは入れない
        item["people"] = x.get("people") is not False  # 書いていなければ「人物あり」として扱う（確認が必要な側に倒す）
        item["ok_license"] = x.get("ok_license") is True
        item["ok_people"] = x.get("ok_people") is True
        for f in ("width", "height"):
            if isinstance(x.get(f), int) and x[f] > 0:
                item[f] = x[f]
        out.append(item)
    return out


def photo_files(items) -> list:
    """記事が使っている写真のファイル（assets/photos/ の中にあって、実際にあるものだけ）。"""
    files = set()
    for n in items:
        for p in n.get("photos") or []:
            src = str(p.get("src") or "") if isinstance(p, dict) else ""
            if src.startswith(PHOTO_DIR) and ".." not in src and (ROOT / src).is_file():
                files.add(src)
    return sorted(files)


def clean(k, v, need_file=True):
    """explain / refs は辞書のリストだけ通す（文字の項目だけ残し、空の行は捨てる）。"""
    if k == "photos":
        return clean_photos(v, need_file)
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


def apply_edits(item: dict, e: dict, need_file=True):
    for k in EDITABLE:
        if k in e:
            v = clean(k, e[k], need_file)
            if k in ("explain", "refs") and not v:
                item.pop(k, None)  # 空にしたら項目ごと消す（前と同じ表示に戻る）
            else:
                item[k] = v  # photos は空でも [] で残す（書き直しで「写真を全部外した」と分かるように）



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


def is_local(d: dict) -> bool:
    """地方（都道府県）の下書きか。"scope": "local" のものだけ（無ければ国の記事）。"""
    return d.get("scope") == "local"


def check_pref(d: dict, pref_ids: set):
    """地方の下書きの都道府県 id（pref・pref_also）が data/prefectures.json にあるか。無ければ何も保存せずにエラー。"""
    ids = [d.get("pref"), *(d.get("pref_also") or [])]
    bad = [x for x in ids if x not in pref_ids]
    if bad:
        raise ValueError(f"地方の下書き {d['id']} の都道府県 id が正しくありません: {bad}（data/prefectures.json の id を使ってください）")


def merge_published(items: list, published: list, now: str):
    """公開する下書きを公開済みの一覧に入れる。同じ id は「書き直し」：元の記事を置きかえる（最初の公開日時は残す）。
    items をその場で並べ替えて (new, updated) を返す。"""
    pos = {n["id"]: i for i, n in enumerate(items)}
    new, updated = 0, 0
    for p in published:
        if p["id"] in pos:
            old = items[pos[p["id"]]]
            if "photos" not in p and old.get("photos"):
                p["photos"] = old["photos"]  # 書き直しに photos 欄が無ければ、公開中の写真（と確認の結果）を引き継ぐ
            p["published_at"] = old.get("published_at", now)
            p["updated_at"] = now
            items[pos[p["id"]]] = p
            updated += 1
        else:
            pos[p["id"]] = len(items)
            items.append(p)
            new += 1
    items.sort(key=lambda n: (n["date"], n.get("published_at", "")), reverse=True)
    return new, updated


def publish(body: dict) -> dict:
    drafts = read(DRAFTS, [])
    news = read(NEWS, [])
    approve, reject = set(body.get("approve", [])), set(body.get("reject", []))
    edits = body.get("edits", {})
    now = dt.datetime.now(JST).isoformat(timespec="seconds")

    published, rejected, remaining = [], [], []
    pref_ids = None
    for d in drafts:
        apply_edits(d, edits.get(d["id"], {}), need_file=d["id"] in approve)
        if d["id"] in approve:
            if is_local(d):
                if pref_ids is None:
                    pref_ids = {p["id"] for p in read(PREFECTURES, [])}
                check_pref(d, pref_ids)
            if "photos" in d:  # 公開する記事の写真は、ファイルがそろっているか確かめる（足りなければ何も保存しない）
                apply_edits(d, {"photos": d["photos"]})
            d["published_at"] = now
            published.append(d)
        elif d["id"] in reject:
            d["rejected_at"] = now
            rejected.append(d)
        else:
            remaining.append(d)

    # 国の記事は data/news.json、地方の記事は data/local_news.json へ（下書きの写真の確認だけを保存したときは、公開済みの記事には触らない）
    national = [p for p in published if not is_local(p)]
    local = [p for p in published if is_local(p)]
    new, updated = merge_published(news, national, now)
    if national:
        write(NEWS, news)
    lnew, lupdated = 0, 0
    if local:
        for p in local:
            p.pop("scope", None)  # local_news.json に入っていること自体が「地方」の印
        local_news = read(LOCAL_NEWS, [])
        lnew, lupdated = merge_published(local_news, local, now)
        write(LOCAL_NEWS, local_news)
    write(DRAFTS, remaining)
    if rejected:
        write(REJECTED, read(REJECTED, []) + rejected)

    parts = []
    if new:
        parts.append(f"{new}件公開")
    if updated:
        parts.append(f"{updated}件書き直し")
    if lnew:
        parts.append(f"地方{lnew}件公開")
    if lupdated:
        parts.append(f"地方{lupdated}件書き直し")
    msg = save_git("記事を" + "・".join(parts) + f"（{now[:10]}）", pages=True) if parts else ""
    return {"published": new + lnew, "updated": updated + lupdated, "local_published": lnew, "local_updated": lupdated,
            "rejected": len(rejected), "remaining": len(remaining), "git": msg}


def rebuild_pages() -> str:
    """記事ごとのページ（a/）と sitemap.xml を作り直す（tools/build_pages.py）。
    失敗しても公開は止めない：保存はそのままにして、理由を返す（成功したら ""）。"""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_pages", Path(__file__).resolve().parent / "build_pages.py")
        bp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bp)
        r = bp.build(ROOT)
    except Exception as e:
        return f"記事ページ（a/）の作り直しに失敗しました（記事の保存は完了しています。python tools/build_pages.py で作り直せます）: {e}"
    if r.get("skipped"):
        return "記事ページを作れなかった記事（id がファイル名に使えない）: " + ", ".join(r["skipped"])
    return ""


def save_git(message: str, pages=False) -> str:
    """data/news.json・data/local_news.json と、記事が使っている写真をコミットしてGitHubに送る。結果をやさしい日本語で返す。
    写真は news.json / local_news.json のどれかの記事が使っているものだけ入れる（使っていない写真は git に入れない）。
    pages=True（記事を公開・修正・非公開にしたとき）は、先に記事ごとのページと sitemap.xml を作り直して一緒にコミットする。"""
    note = rebuild_pages() if pages else ""
    if not (ROOT / ".git").exists():
        return note
    msg = git_commit(message, pages)
    return f"{msg} {note}" if note else msg


def git_commit(message: str, pages: bool) -> str:
    if pages:
        git("add", "-A", "--", "a", "sitemap.xml")  # -A：非公開に戻した記事の消えたページも入れる
    git("add", "data/news.json")
    if LOCAL_NEWS.exists():
        git("add", "data/local_news.json")
    photos = photo_files(read(NEWS, []) + read(LOCAL_NEWS, []))
    if photos:
        git("add", "--", *photos)
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


def edit_list(items: list, edits: dict, unpublish: set, now: str):
    """公開済みの一覧の記事を直す／非公開に戻す。(残す記事, 非公開にした記事, 直した数) を返す。"""
    edited, removed, keep = 0, [], []
    for n in items:
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
    return keep, removed, edited


def manage(body: dict) -> dict:
    """公開済みの記事を直す／非公開に戻す。国の記事は edits / unpublish、地方の記事は local_edits / local_unpublish。"""
    news = read(NEWS, [])
    edits = body.get("edits", {})
    unpublish = set(body.get("unpublish", []))
    now = dt.datetime.now(JST).isoformat(timespec="seconds")
    ledits = body.get("local_edits", {})
    lunpublish = set(body.get("local_unpublish", []))
    keep, removed, edited = edit_list(news, edits, unpublish, now)
    if edits or unpublish or not (ledits or lunpublish):  # 地方の記事だけを直すときは news.json に触らない
        write(NEWS, keep)
    lkeep, lremoved, ledited = [], [], 0
    if ledits or lunpublish:
        lkeep, lremoved, ledited = edit_list(read(LOCAL_NEWS, []), ledits, lunpublish, now)
        write(LOCAL_NEWS, lkeep)
    if removed or lremoved:
        write(UNPUBLISHED, read(UNPUBLISHED, []) + removed + lremoved)
    parts = []
    if edited:
        parts.append(f"{edited}件を修正")
    if removed:
        parts.append(f"{len(removed)}件を非公開")
    if ledited:
        parts.append(f"地方{ledited}件を修正")
    if lremoved:
        parts.append(f"地方{len(lremoved)}件を非公開")
    msg = save_git("公開済みの記事：" + "・".join(parts) + f"（{now[:10]}）", pages=True) if parts else ""
    return {"edited": edited + ledited, "unpublished": len(removed) + len(lremoved), "total": len(keep),
            "local_edited": ledited, "local_unpublished": len(lremoved), "git": msg}


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
        elif self.path == "/api/local_news":
            self._json(read(LOCAL_NEWS, []))
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
    # Windowsでは同じポートに2つ目のサーバーが重ねて立ち上がってしまうので、使用中なら止める
    class Server(ThreadingHTTPServer):
        allow_reuse_address = False

        def server_bind(self):
            import socket
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

    try:
        srv = Server(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"ポート{PORT}はもう使われています。別の「確認ページを開く.cmd」の黒い画面が開いていないか確認して、それを閉じてからもう一度開いてください。")
        raise SystemExit(1)
    print(f"フォルダ: {ROOT}")
    print(f"確認ページ: http://localhost:{PORT}/review   サイト: http://localhost:{PORT}/   （止めるときは Ctrl+C）")
    srv.serve_forever()
