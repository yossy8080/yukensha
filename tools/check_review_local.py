"""有権者：確認ページ（review_server.py）の「地方の記事」の振り分けを確かめる

使い方: python tools/check_review_local.py
- 一時フォルダに data/・drafts/ のコピーを作り、その中だけで publish() / manage() を動かす（本物の data/ には触らない。git も使わない）
- 確かめること:
  1. 地方の下書き（"scope": "local"）は data/local_news.json に入り、data/news.json には入らない
  2. 国の下書きだけのときの news.json は、main ブランチの review_server.py の結果と1バイトも違わない
  3. 都道府県 id が間違っている地方の下書きは、何も保存せずにエラーになる
  4. 地方の書き直し（同じ id）は置きかえ・最初の公開日時と写真を引き継ぐ
  5. 公開済みの地方の記事を直す／非公開に戻す（news.json には触らない）
最後に「OK」と出れば全部通っています。
"""
import datetime as real_dt
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REAL_ROOT = HERE.parent
FIXED_NOW = real_dt.datetime(2026, 11, 10, 9, 0, 0, tzinfo=real_dt.timezone(real_dt.timedelta(hours=9)))


class FakeDatetime(real_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED_NOW


class FakeDt:
    datetime = FakeDatetime
    timezone = real_dt.timezone
    timedelta = real_dt.timedelta


def load_module(name, path, root):
    """review_server.py を読み込み、場所を一時フォルダに差しかえる（git は呼ばれたら失敗にする）"""
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.ROOT = root
    m.NEWS = root / "data" / "news.json"
    m.DRAFTS = root / "drafts" / "drafts.json"
    m.REJECTED = root / "drafts" / "rejected.json"
    m.UNPUBLISHED = root / "drafts" / "unpublished.json"
    m.OPINION = root / "data" / "opinion.json"
    m.OPINION_DRAFTS = root / "drafts" / "opinion_drafts.json"
    if hasattr(m, "LOCAL_NEWS"):
        m.LOCAL_NEWS = root / "data" / "local_news.json"
        m.PREFECTURES = root / "data" / "prefectures.json"
    m.dt = FakeDt

    def no_git(*a):
        raise AssertionError("git が呼ばれました（テストでは使わない）")
    m.git = no_git
    for p in (m.NEWS, m.DRAFTS):
        assert REAL_ROOT not in p.parents, "本物のフォルダを指しています"
    return m


def make_root(base: Path, name: str, drafts: list) -> Path:
    root = base / name
    (root / "data").mkdir(parents=True)
    (root / "drafts").mkdir()
    for f in ("news.json", "prefectures.json"):
        shutil.copy(REAL_ROOT / "data" / f, root / "data" / f)
    (root / "data" / "local_news.json").write_text("[]\n", encoding="utf-8")
    (root / "drafts" / "drafts.json").write_text(json.dumps(drafts, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return root


def j(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def draft(i, **kw):
    d = {"id": f"2026-11-10-test-{i}", "date": "2026-11-10", "tags": ["テスト"], "title": f"テスト{i}", "summary": "テストの要約",
         "points": ["テスト"], "source_url": "https://example.jp/", "source_title": "テスト", "site": "テスト"}
    d.update(kw)
    return d


def main():
    real_before = {f: f.read_bytes() for f in (REAL_ROOT / "data").glob("*.json")}
    # main の版（比べ合わせ用）。git は review_server.py と同じ探し方（Roy の PC は Hermes に付いている git）
    spec = importlib.util.spec_from_file_location("rs_find_git", HERE / "review_server.py")
    finder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finder)
    try:
        old_src = subprocess.run([finder.GIT or "git", "-C", str(REAL_ROOT), "show", "main:tools/review_server.py"], capture_output=True, text=True, encoding="utf-8")
    except OSError:
        old_src = subprocess.CompletedProcess([], 1, "", "")
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        new_path = HERE / "review_server.py"

        # 2. 国の下書きだけ：main の版と同じ結果になるか
        nat = [draft("n1", ministry="kantei"), draft("n2", ministry="mof", featured=True), draft("n3", ministry="env")]
        ra = make_root(base, "new_nat", nat)
        A = load_module("rs_new_nat", new_path, ra)
        A.publish({"approve": [nat[0]["id"], nat[1]["id"]], "reject": [nat[2]["id"]], "edits": {nat[0]["id"]: {"title": "直した見出し"}}})
        A.manage({"edits": {nat[1]["id"]: {"summary": "直した要約"}}, "unpublish": [nat[0]["id"]]})
        if old_src.returncode == 0:
            (base / "old.py").write_text(old_src.stdout, encoding="utf-8")
            rb = make_root(base, "old_nat", nat)
            B = load_module("rs_old_nat", base / "old.py", rb)
            B.publish({"approve": [nat[0]["id"], nat[1]["id"]], "reject": [nat[2]["id"]], "edits": {nat[0]["id"]: {"title": "直した見出し"}}})
            B.manage({"edits": {nat[1]["id"]: {"summary": "直した要約"}}, "unpublish": [nat[0]["id"]]})
            for f in ("data/news.json", "drafts/drafts.json", "drafts/rejected.json", "drafts/unpublished.json"):
                assert (ra / f).read_bytes() == (rb / f).read_bytes(), f"国の記事の結果が main と違います: {f}"
            print("OK 国の記事だけのときは main の review_server.py と同じ結果（news.json など4ファイルが1バイトも同じ）")
        else:
            print("（main の review_server.py を読めなかったので、main との比べ合わせは飛ばしました）")
        assert (ra / "data" / "local_news.json").read_text(encoding="utf-8") == "[]\n", "国の記事だけなのに local_news.json が変わりました"

        # 1. 国と地方をいっしょに公開
        mix = [draft("n4", ministry="kantei"),
               draft("l1", scope="local", pref="tokyo", site="東京都ホームページ"),
               draft("l2", scope="local", pref="kanagawa", pref_also=["tokyo"], site="神奈川県ホームページ",
                     photos=[]),
               draft("l3", scope="local", pref="kagawa", site="香川県ホームページ")]
        rc = make_root(base, "mix", mix)
        C = load_module("rs_mix", new_path, rc)
        news_before = j(rc / "data" / "news.json")
        r = C.publish({"approve": [mix[0]["id"], mix[1]["id"], mix[2]["id"]], "reject": [], "edits": {}})
        news_after, local_after = j(rc / "data" / "news.json"), j(rc / "data" / "local_news.json")
        assert len(news_after) == len(news_before) + 1 and any(n["id"] == mix[0]["id"] for n in news_after), "国の記事が news.json に入っていません"
        assert not any(n["id"].startswith("2026-11-10-test-l") for n in news_after), "地方の記事が news.json に入っています"
        assert {n["id"] for n in local_after} == {mix[1]["id"], mix[2]["id"]}, "地方の記事が local_news.json に入っていません"
        assert all("scope" not in n and n["published_at"] for n in local_after), "local_news.json の記事の形がおかしい"
        assert [d["id"] for d in j(rc / "drafts" / "drafts.json")] == [mix[3]["id"]], "残りの下書きがおかしい"
        assert r["published"] == 3 and r["local_published"] == 2, r
        print("OK 地方の下書きは local_news.json へ、国の下書きは news.json へ")

        # 3. 都道府県 id の間違い：何も保存しない
        bad = [draft("b1", scope="local", pref="tokio"), draft("b2", ministry="kantei")]
        rd = make_root(base, "bad", bad)
        D = load_module("rs_bad", new_path, rd)
        before = {f: (rd / f).read_bytes() for f in ("data/news.json", "data/local_news.json", "drafts/drafts.json")}
        try:
            D.publish({"approve": [bad[0]["id"], bad[1]["id"]]})
            raise AssertionError("間違った都道府県 id なのにエラーになりませんでした")
        except ValueError as e:
            assert "tokio" in str(e)
        assert all((rd / f).read_bytes() == b for f, b in before.items()), "エラーなのにファイルが変わりました"
        print("OK 都道府県 id が間違っている地方の下書きはエラー（何も保存しない）")

        # 4. 地方の書き直し（同じ id）：置きかえ、最初の公開日時と写真を引き継ぐ
        local = j(rc / "data" / "local_news.json")
        photo = {"src": "assets/photos/x.jpg", "alt": "テスト", "credit": "写真：東京都ホームページ", "page_url": "", "license": "PDL1.0",
                 "people": False, "ok_license": True, "ok_people": False}
        for n in local:
            if n["id"] == mix[1]["id"]:
                n["published_at"] = "2026-11-01T09:00:00+09:00"
                n["photos"] = [photo]
        (rc / "data" / "local_news.json").write_text(json.dumps(local, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        rw = draft("l1", scope="local", pref="tokyo", title="書き直した見出し")
        (rc / "drafts" / "drafts.json").write_text(json.dumps([rw], ensure_ascii=False), encoding="utf-8")
        news_bytes = (rc / "data" / "news.json").read_bytes()
        r = C.publish({"approve": [rw["id"]]})
        got = {n["id"]: n for n in j(rc / "data" / "local_news.json")}[rw["id"]]
        assert r["local_updated"] == 1 and got["title"] == "書き直した見出し", r
        assert got["published_at"] == "2026-11-01T09:00:00+09:00" and got["updated_at"] and got["photos"] == [photo], got
        assert len(j(rc / "data" / "local_news.json")) == 2, "書き直しで記事が増えました"
        assert (rc / "data" / "news.json").read_bytes() == news_bytes, "地方の書き直しで news.json が変わりました"
        print("OK 地方の書き直しは置きかえ（最初の公開日時・写真を引き継ぐ。news.json は変わらない）")

        # 5. 公開済みの地方の記事を直す／非公開に戻す
        r = C.manage({"local_edits": {mix[2]["id"]: {"summary": "直した要約", "points": ["a"]}}, "local_unpublish": [mix[1]["id"]]})
        local = j(rc / "data" / "local_news.json")
        assert [n["id"] for n in local] == [mix[2]["id"]] and local[0]["summary"] == "直した要約", local
        assert [n["id"] for n in j(rc / "drafts" / "unpublished.json")] == [mix[1]["id"]]
        assert (rc / "data" / "news.json").read_bytes() == news_bytes, "地方の記事を直したら news.json が変わりました"
        assert r["local_edited"] == 1 and r["local_unpublished"] == 1, r
        print("OK 公開済みの地方の記事の修正・非公開（news.json は変わらない）")

        # 本物の data/ が変わっていないこと
        assert all(f.read_bytes() == b for f, b in real_before.items()), "本物の data/ が変わっています"
    print("OK")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("NG", e)
        sys.exit(1)
