"""tools/build_pages.py の確認（python tools/test_build_pages.py）

- a/ のページ数 = news.json + local_news.json の記事数
- どのページも html.parser で読めて、<h1> に題名、canonical がその記事の URL
- sitemap.xml が XML として正しく、<loc> の数 = 決まったページ + /a/ + 記事数
- 確認が済んでいない写真はどのページにも出ない
- github.io・/yukensha/ への古いリンクが無い
- data/ が main から変わっていない（入力の JSON に触っていない）
- 一時フォルダのコピーで：作り直しても差分が出ない・非公開にした記事のページは消える（a/index.html は残る）・
  review_server の「非公開に戻す」で a/ と sitemap.xml もコミットされる
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


bp = load("build_pages", HERE / "build_pages.py")


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h1, self.in_h1, self.canonical, self.imgs = "", False, None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h1":
            self.in_h1 = True
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        elif tag == "img":
            self.imgs.append(a.get("src"))

    def handle_endtag(self, tag):
        if tag == "h1":
            self.in_h1 = False

    def handle_data(self, data):
        if self.in_h1:
            self.h1 += data


def articles(root=ROOT):
    return (json.loads((root / "data" / "news.json").read_text(encoding="utf-8")),
            json.loads((root / "data" / "local_news.json").read_text(encoding="utf-8")))


class TestBuiltSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bp.build(ROOT)
        cls.news, cls.local = articles()
        cls.items = cls.news + cls.local

    def test_page_count(self):
        pages = [f for f in (ROOT / "a").glob("*.html") if f.name != "index.html"]
        self.assertEqual(len(pages), len(self.news) + len(self.local))
        self.assertTrue((ROOT / "a" / "index.html").is_file())

    def test_pages_parse(self):
        for it in self.items:
            p = Page()
            p.feed((ROOT / "a" / f"{it['id']}.html").read_text(encoding="utf-8"))
            p.close()
            self.assertEqual(p.h1.strip(), it["title"], it["id"])
            self.assertEqual(p.canonical, f"https://yukensha.com/a/{it['id']}.html")

    def test_index_links_all(self):
        t = (ROOT / "a" / "index.html").read_text(encoding="utf-8")
        for it in self.items:
            self.assertIn(f'href="/a/{it["id"]}.html"', t)

    def test_sitemap(self):
        tree = ET.parse(ROOT / "sitemap.xml")
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = [e.text for e in tree.getroot().findall("s:url/s:loc", ns)]
        self.assertEqual(len(locs), len(bp.FIXED_PAGES) + 1 + len(self.items))
        self.assertEqual(len(set(locs)), len(locs))
        self.assertIn("https://yukensha.com/a/", locs)

    def test_no_unapproved_photos(self):
        bad = {"/" + p["src"] for it in self.items for p in it.get("photos") or [] if not bp.photo_ok(p)}
        ok = {"/" + p["src"] for it in self.items for p in it.get("photos") or [] if bp.photo_ok(p)}
        bad -= ok  # 同じファイルを別の記事で確認済みにしていることはない想定（あれば下で分かる）
        self.assertTrue(bad, "確認待ちの写真が1枚も無いと、この確認の意味がない")
        for f in (ROOT / "a").glob("*.html"):
            t = f.read_text(encoding="utf-8")
            for src in bad:
                self.assertNotIn(src, t, f.name)
                self.assertNotIn("https://yukensha.com" + src, t, f.name)

    def test_no_old_urls(self):
        for f in [*(ROOT / "a").glob("*.html"), ROOT / "sitemap.xml"]:
            t = f.read_text(encoding="utf-8")
            self.assertNotIn("github.io", t, f.name)
            self.assertNotIn("/yukensha/", t, f.name)

    def test_data_unchanged(self):
        # main と分かれたところ（merge-base）と比べる：分かれたあとに main で公開した記事の差は、このブランチの変更ではない
        git = load("rs_git", HERE / "review_server.py").GIT or "git"
        run = lambda *a: subprocess.run([git, "-C", str(ROOT), *a], capture_output=True, text=True, encoding="utf-8")
        base = run("merge-base", "main", "HEAD").stdout.strip() or "main"
        r = run("diff", base, "--stat", "--", "data/")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")


class TestInCopy(unittest.TestCase):
    """一時フォルダのコピーで試す（本物の a/・data/ には触らない）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="yk_pages_"))
        (self.tmp / "data").mkdir()
        for f in ("news.json", "local_news.json", "sources.json", "prefectures.json"):
            shutil.copy(ROOT / "data" / f, self.tmp / "data" / f)
        (self.tmp / "drafts").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_idempotent_and_delete_stale(self):
        r1 = bp.build(self.tmp)
        self.assertGreater(r1["written"], 0)
        self.assertEqual(bp.build(self.tmp)["written"], 0)  # 2回目は何も書きかえない
        news = json.loads((self.tmp / "data" / "news.json").read_text(encoding="utf-8"))
        gone = news.pop(0)
        (self.tmp / "data" / "news.json").write_text(json.dumps(news, ensure_ascii=False), encoding="utf-8")
        r3 = bp.build(self.tmp)
        self.assertEqual(r3["deleted"], [gone["id"] + ".html"])
        self.assertFalse((self.tmp / "a" / f"{gone['id']}.html").exists())
        self.assertTrue((self.tmp / "a" / "index.html").exists())
        self.assertNotIn(gone["id"], (self.tmp / "sitemap.xml").read_text(encoding="utf-8"))

    def test_bad_id_skipped(self):
        news = json.loads((self.tmp / "data" / "news.json").read_text(encoding="utf-8"))
        news[0]["id"] = "../evil"
        (self.tmp / "data" / "news.json").write_text(json.dumps(news, ensure_ascii=False), encoding="utf-8")
        r = bp.build(self.tmp)
        self.assertEqual(r["skipped"], ["../evil"])
        self.assertFalse((self.tmp / "evil.html").exists())

    def test_review_server_unpublish_commits_pages(self):
        rs = load("rs_copy", HERE / "review_server.py")
        if not rs.GIT:
            self.skipTest("git が見つからない")
        rs.ROOT = self.tmp
        rs.NEWS = self.tmp / "data" / "news.json"
        rs.LOCAL_NEWS = self.tmp / "data" / "local_news.json"
        rs.UNPUBLISHED = self.tmp / "drafts" / "unpublished.json"
        bp.build(self.tmp)
        for args in (("init", "-q"), ("config", "user.email", "t@example.com"), ("config", "user.name", "t"),
                     ("config", "core.autocrlf", "false"), ("add", "-A"), ("commit", "-q", "-m", "init")):
            rs.git(*args)
        gone = json.loads(rs.NEWS.read_text(encoding="utf-8"))[0]["id"]
        res = rs.manage({"unpublish": [gone]})
        self.assertEqual(res["unpublished"], 1)
        self.assertTrue(res["git"].startswith("保存しました"), res["git"])
        code, out = rs.git("show", "--name-status", "--format=", "HEAD")
        self.assertIn(f"D\ta/{gone}.html", out)
        self.assertIn("M\tsitemap.xml", out)
        self.assertIn("M\ta/index.html", out)
        self.assertEqual(rs.git("status", "--porcelain", "--", "a", "sitemap.xml")[1], "")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    unittest.main(verbosity=2)
