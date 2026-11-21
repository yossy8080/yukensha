"""tools/build_pages.py の確認（python tools/test_build_pages.py）

- a/ のページ数 = news.json + local_news.json の記事数。m/・p/・g/ のページ数
- 生成ページ：<h1> は1つ・canonical は自分の URL・title は重ならない・GoatCounter・feed・用語集・パンくず
- /index.html へのリンクが無い・/ から始まるリンクの先にファイルがある
- feed.xml（50件）・IndexNow（鍵のファイル・dry_run でネットに出ない）・確認ページの push のあとの IndexNow
- どのページも html.parser で読めて、<h1> に題名、canonical がその記事の URL
- sitemap.xml が XML として正しく、<loc> の数 = 決まったページ + /a/ + 記事数
- 確認が済んでいない写真はどのページにも出ない
- github.io・/yukensha/ への古いリンクが無い
- data/ が main から変わっていない（入力の JSON に触っていない）
- 一時フォルダのコピーで：作り直しても差分が出ない・非公開にした記事のページは消える（a/index.html は残る）・
  review_server の「非公開に戻す」で a/ と sitemap.xml もコミットされる
"""
import html
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


bp = load("build_pages", HERE / "build_pages.py")
indexnow = load("indexnow", HERE / "indexnow.py")


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h1, self.in_h1, self.canonical, self.imgs = "", False, None, []
        self.h1_count, self.title, self.in_title, self.hrefs = 0, "", False, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h1":
            self.in_h1 = True
            self.h1_count += 1
        elif tag == "title":
            self.in_title = True
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        elif tag == "img":
            self.imgs.append(a.get("src"))
        if tag in ("a", "link") and a.get("href") and a.get("rel") not in ("preconnect", "canonical", "icon") \
                and not a.get("href", "").startswith("https://fonts."):
            self.hrefs.append(a["href"])

    def handle_endtag(self, tag):
        if tag == "h1":
            self.in_h1 = False
        elif tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_h1:
            self.h1 += data
        if self.in_title:
            self.title += data


def generated_pages(root=None):
    """build_pages.py が作る HTML（a/・m/・p/・g/）。"""
    root = root or ROOT
    return sorted(f for d in ("a", "m", "p", "g") for f in (root / d).glob("*.html"))


def public_html(root=None):
    """手で書いた公開の HTML（サイトの一番上の *.html）。"""
    return sorted((root or ROOT).glob("*.html"))


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

    def expected_counts(self):
        """m/・p/・g/ のページ数を、build とは別に数える。"""
        sources = json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf-8"))
        prefs = json.loads((ROOT / "data" / "prefectures.json").read_text(encoding="utf-8"))
        m = [s["id"] for s in sources if not s.get("hidden")
             and any(n.get("ministry") == s["id"] or s["id"] in (n.get("also") or []) for n in self.news)]
        p = [x["id"] for x in prefs if any(n.get("pref") == x["id"] or x["id"] in (n.get("pref_also") or []) for n in self.local)]
        gl = bp.Glossary(json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8")))
        g = {t for it in self.items for t in gl.find(it)}
        return m, p, g

    def test_page_counts_mpg(self):
        m, p, g = self.expected_counts()
        self.assertGreater(len(m), 0)
        self.assertGreater(len(g), 0)
        self.assertEqual(sorted(f.stem for f in (ROOT / "m").glob("*.html") if f.name != "index.html"), sorted(m))
        self.assertEqual(sorted(f.stem for f in (ROOT / "p").glob("*.html") if f.name != "index.html"), sorted(p))
        self.assertEqual(len([f for f in (ROOT / "g").glob("*.html") if f.name != "index.html"]), len(g))
        for d in ("m", "p", "g"):
            self.assertTrue((ROOT / d / "index.html").is_file(), d)

    def test_generated_pages_basics(self):
        """どの生成ページも：読める・<h1> は1つ・canonical は自分の URL・title は重ならない・GoatCounter・feed のリンク。"""
        titles = {}
        for f in generated_pages():
            rel = f.relative_to(ROOT).as_posix()
            t = f.read_text(encoding="utf-8")
            p = Page()
            p.feed(t)
            p.close()
            self.assertEqual(p.h1_count, 1, rel)
            self.assertEqual(p.canonical, bp.page_url(rel), rel)
            self.assertTrue(p.title, rel)
            self.assertNotIn(p.title, titles, f"{rel} と {titles.get(p.title)} の title が同じ")
            titles[p.title] = rel
            self.assertIn(bp.GOATCOUNTER, t, rel)
            self.assertIn('<link rel="alternate" type="application/atom+xml" title="有権者" href="/feed.xml">', t, rel)
            self.assertIn('href="/g/">用語集</a>', t, rel)
            self.assertIn("誤りに気づいたら", t, rel)
            self.assertIn('"@type": "BreadcrumbList"', t, rel)
            self.assertIn('<meta name="description" content="', t, rel)
            self.assertIn('<meta property="og:title"', t, rel)
        self.assertGreater(len(titles), len(self.items))

    def test_public_pages_head_and_footer(self):
        for f in public_html():
            t = f.read_text(encoding="utf-8")
            self.assertIn("gc.zgo.at/count.js", t, f.name)
            self.assertIn('href="/feed.xml"', t, f.name)
            self.assertRegex(t, r'href="/?g/">用語集</a>', f.name)

    def test_no_index_html_links(self):
        for f in [*public_html(), *generated_pages()]:
            t = f.read_text(encoding="utf-8")
            self.assertNotIn('href="/index.html', t, f.name)
            self.assertNotIn('href="index.html', t, f.name)

    def test_internal_links_resolve(self):
        """生成ページ（と、一覧を入れた手書きのページ）の / から始まるリンクの先にファイルがある。"""
        files = [*generated_pages(), ROOT / "ministries.html", ROOT / "local.html", ROOT / "pledges.html"]
        missing = []
        for f in files:
            p = Page()
            p.feed(f.read_text(encoding="utf-8"))
            p.close()
            for h in p.hrefs:
                if h.startswith("//") or re.match(r"^[a-z]+:", h) or h.startswith("#"):
                    continue
                path = unquote(re.split(r"[?#]", h)[0])
                if not path.startswith("/"):
                    path = "/" + (f.parent.relative_to(ROOT).as_posix() + "/" if f.parent != ROOT else "") + path
                target = ROOT / (path.lstrip("/") + ("index.html" if path.endswith("/") else ""))
                if not target.is_file():
                    missing.append(f"{f.relative_to(ROOT).as_posix()} → {h}")
        self.assertEqual(missing, [])

    def test_static_blocks(self):
        m, p, _ = self.expected_counts()
        mt = (ROOT / "ministries.html").read_text(encoding="utf-8")
        lt = (ROOT / "local.html").read_text(encoding="utf-8")
        for x in m:
            self.assertIn(f'href="/m/{x}.html"', mt)
        for x in p:
            self.assertIn(f'href="/p/{x}.html"', lt)
        self.assertIn("府省ごとの記事一覧", mt)
        self.assertIn("m/${encodeURIComponent(m)}.html", mt)  # ?m= のときの canonical
        pt = (ROOT / "pledges.html").read_text(encoding="utf-8")
        self.assertIn('<details class="static-pledges"><summary>公約の一覧（文字だけで見る）</summary>', pt)
        data = json.loads((ROOT / "data" / "pledges.json").read_text(encoding="utf-8"))
        for party in data["parties"]:
            for pl in party["pledges"]:
                self.assertIn(html.escape(pl["text"]), pt, pl["id"])
        # 決まった印のあいだだけを書きかえている（印は1つずつ）
        for t, name in ((mt, "STATIC-LIST"), (lt, "STATIC-LIST"), (pt, "STATIC-PLEDGES")):
            self.assertEqual(t.count(f"<!-- {name}:BEGIN -->"), 1)
            self.assertEqual(t.count(f"<!-- {name}:END -->"), 1)

    def test_article_sections(self):
        """記事のページ：背景の問いは h2、関連する記事は4件（自分は入らない）、用語のリンク。"""
        with_terms = 0
        for it in self.items:
            t = (ROOT / "a" / f"{it['id']}.html").read_text(encoding="utf-8")
            qs = [x["q"] for x in it.get("explain") or [] if x.get("q")]
            for q in qs:
                self.assertIn(f'<h2 class="explain-q">{html.escape(q)}</h2>', t, it["id"])
            self.assertNotIn("<dt>", t)
            rel = re.search(r'<h2 class="ap-h2" id="ap-related">関連する記事</h2><ul class="ap-rel">(.*?)</ul>', t)
            self.assertTrue(rel, it["id"])
            links = re.findall(r'href="/a/([^"]+)\.html"', rel.group(1))
            self.assertEqual(len(links), 4, it["id"])
            self.assertNotIn(it["id"], links)
            if "この記事に出てくる言葉" in t:
                with_terms += 1
        self.assertGreater(with_terms, len(self.items) // 2)

    def test_term_slug(self):
        self.assertEqual(bp.term_slug("JC-STAR"), "jc-star")
        self.assertEqual(bp.term_slug("G7"), "g7")
        self.assertEqual(bp.term_slug("特定技能"), "特定技能")
        self.assertEqual(bp.term_slug('A/B:C*D?"E<F>|G#%&H I'), "abcdefgh-i")
        self.assertEqual(bp.term_slug("国の 予算/案?"), "国の予算案")
        s = bp.assign_slugs([{"term": "GX"}, {"term": "gx"}, {"term": "index"}])
        self.assertEqual(s, {"GX": "gx", "gx": "gx-2", "index": "index-2"})

    def test_sitemap(self):
        tree = ET.parse(ROOT / "sitemap.xml")
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = [e.text for e in tree.getroot().findall("s:url/s:loc", ns)]
        m, p, g = self.expected_counts()
        self.assertEqual(len(locs), len(bp.FIXED_PAGES) + 1 + len(self.items) + 3 + len(m) + len(p) + len(g))
        self.assertEqual(len(set(locs)), len(locs))
        for u in ("https://yukensha.com/a/", "https://yukensha.com/m/", "https://yukensha.com/p/", "https://yukensha.com/g/"):
            self.assertIn(u, locs)
        self.assertNotIn("https://yukensha.com/feed.xml", locs)
        for u in locs:
            path = unquote(u[len("https://yukensha.com/"):])
            self.assertTrue((ROOT / (path + "index.html" if path.endswith("/") or not path else path)).is_file(), u)
            self.assertNotRegex(u, r"[^\x21-\x7e]", "日本語は % で表す")
        lastmods = {e.find("s:loc", ns).text: (e.find("s:lastmod", ns).text if e.find("s:lastmod", ns) is not None else None)
                    for e in tree.getroot().findall("s:url", ns)}
        for u, lm in lastmods.items():
            if "/m/" in u or "/p/" in u or "/g/" in u:
                self.assertTrue(lm and bp.W3C.match(lm), u)

    def test_feed(self):
        tree = ET.parse(ROOT / "feed.xml")
        a = "{http://www.w3.org/2005/Atom}"
        entries = tree.getroot().findall(a + "entry")
        self.assertEqual(len(entries), min(50, len(self.items)))
        newest = sorted(self.items, key=bp.sort_key, reverse=True)[:50]
        for e, it in zip(entries, newest):
            url = f"https://yukensha.com/a/{it['id']}.html"
            self.assertEqual(e.find(a + "id").text, url)
            self.assertEqual(e.find(a + "link").get("href"), url)
            self.assertEqual(e.find(a + "title").text, it["title"])
            self.assertRegex(e.find(a + "updated").text, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)$")
            self.assertTrue(e.find(a + "summary").text)

    def test_indexnow(self):
        key = (ROOT / f"{indexnow.KEY}.txt")
        self.assertTrue(key.is_file())
        self.assertEqual(key.read_bytes(), indexnow.KEY.encode("ascii"))
        self.assertEqual(indexnow.KEY, "cd11b7311202af032809200bf75680c1")
        with mock.patch.object(indexnow.urllib.request, "urlopen", side_effect=AssertionError("ネットに出てはいけない")):
            r = indexnow.submit(["https://yukensha.com/", "https://example.com/x"], dry_run=True)
        self.assertIsInstance(r, str)
        self.assertIn("1件", r)  # ほかのサイトの URL は落とす
        body = indexnow.payload(["https://yukensha.com/a/"] * 3)
        self.assertEqual(body, {"host": "yukensha.com", "key": indexnow.KEY,
                                "keyLocation": f"https://yukensha.com/{indexnow.KEY}.txt", "urlList": ["https://yukensha.com/a/"]})
        self.assertEqual(len(indexnow.clean([f"https://yukensha.com/{i}" for i in range(10050)])), 10000)

        class Resp:
            status = 202
            def __enter__(self): return self
            def __exit__(self, *a): return False
        sent = []
        def fake(req, timeout):
            sent.append((req.full_url, json.loads(req.data), timeout))
            return Resp()
        with mock.patch.object(indexnow.urllib.request, "urlopen", side_effect=fake):
            self.assertIn("知らせました", indexnow.submit(["https://yukensha.com/"]))
        self.assertEqual(sent[0][0], "https://api.indexnow.org/indexnow")
        self.assertEqual(sent[0][2], 15)
        with mock.patch.object(indexnow.urllib.request, "urlopen", side_effect=OSError("つながらない")):
            self.assertIn("送れませんでした", indexnow.submit(["https://yukensha.com/"]))  # 例外は出さない

    def test_review_server_indexnow_hook(self):
        rs = load("rs_hook", HERE / "review_server.py")
        calls = []
        rs.notify_indexnow = lambda result, ids: calls.append((result, ids)) or "IndexNow：テスト"
        for push_code, expect in ((0, 1), (1, 0)):
            calls.clear()
            def fake_git(*args, _c=push_code):
                if args[0] == "remote":
                    return 0, "origin"
                if args[0] == "push":
                    return _c, "x"
                return 0, ""
            rs.git = fake_git
            msg = rs.git_commit("test", True, ["a1"], {"urls": []})
            self.assertEqual(len(calls), expect, msg)
            if expect:
                self.assertIn("IndexNow：テスト", msg)
        it = self.news[0]
        urls = rs.indexnow_urls({"terms": {it["id"]: ["x"]}, "urls": ["https://yukensha.com/m/"]}, [it["id"]])
        for u in (f"https://yukensha.com/a/{it['id']}.html", f"https://yukensha.com/m/{it['ministry']}.html",
                  "https://yukensha.com/g/x.html", "https://yukensha.com/", "https://yukensha.com/a/",
                  "https://yukensha.com/feed.xml", "https://yukensha.com/m/"):
            self.assertIn(u, urls)

    def test_no_unapproved_photos(self):
        bad = {"/" + p["src"] for it in self.items for p in it.get("photos") or [] if not bp.photo_ok(p)}
        ok = {"/" + p["src"] for it in self.items for p in it.get("photos") or [] if bp.photo_ok(p)}
        bad -= ok  # 同じファイルを別の記事で確認済みにしていることはない想定（あれば下で分かる）
        self.assertTrue(bad, "確認待ちの写真が1枚も無いと、この確認の意味がない")
        for f in [*generated_pages(), *public_html(), ROOT / "feed.xml"]:
            t = f.read_text(encoding="utf-8")
            for src in bad:
                self.assertNotIn(src, t, f.name)
                self.assertNotIn(src.lstrip("/"), t, f.name)

    def test_photo_tags(self):
        """og:image は確認済みの1枚目（無ければサイトの画像）。2枚目からは loading="lazy"。"""
        for it in self.items:
            t = (ROOT / "a" / f"{it['id']}.html").read_text(encoding="utf-8")
            ok = [p for p in it.get("photos") or [] if bp.photo_ok(p)]
            og = re.search(r'<meta property="og:image" content="([^"]+)">', t).group(1)
            self.assertEqual(og, "https://yukensha.com/" + ok[0]["src"] if ok else bp.OG_DEFAULT, it["id"])
            imgs = re.findall(r"<img [^>]*>", t)
            self.assertEqual(len(imgs), len(ok), it["id"])
            for i, tag in enumerate(imgs):
                self.assertEqual('loading="lazy"' in tag, i > 0, it["id"])

    def test_no_old_urls(self):
        for f in [*generated_pages(), ROOT / "sitemap.xml", ROOT / "feed.xml"]:
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
        r = run("status", "--porcelain", "--", "data/")  # まだコミットしていない変更も無い
        self.assertEqual(r.stdout.strip(), "")


class TestInCopy(unittest.TestCase):
    """一時フォルダのコピーで試す（本物の a/・data/ には触らない）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="yk_pages_"))
        (self.tmp / "data").mkdir()
        for f in ("news.json", "local_news.json", "sources.json", "prefectures.json", "glossary.json", "pledges.json", "pref_sources.json"):
            shutil.copy(ROOT / "data" / f, self.tmp / "data" / f)
        for f in ("ministries.html", "local.html", "pledges.html"):
            shutil.copy(ROOT / f, self.tmp / f)
        (self.tmp / "drafts").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_idempotent_and_delete_stale(self):
        r1 = bp.build(self.tmp)
        self.assertGreater(r1["written"], 0)
        self.assertEqual(bp.build(self.tmp)["written"], 0)  # 2回目は何も書きかえない
        for f in ("ministries.html", "local.html", "pledges.html"):  # 手書きのページは本物と同じ（印のあいだも含めて）
            self.assertEqual((self.tmp / f).read_bytes(), (ROOT / f).read_bytes(), f)
        self.assertEqual(set(r1["counts"]), {"a", "m", "p", "g"})
        self.assertIn("https://yukensha.com/a/", r1["urls"])
        self.assertNotIn("https://yukensha.com/sitemap.xml", r1["urls"])
        news = json.loads((self.tmp / "data" / "news.json").read_text(encoding="utf-8"))
        gone = news.pop(0)
        (self.tmp / "data" / "news.json").write_text(json.dumps(news, ensure_ascii=False), encoding="utf-8")
        r3 = bp.build(self.tmp)
        self.assertEqual(r3["deleted"], [gone["id"] + ".html"])
        self.assertFalse((self.tmp / "a" / f"{gone['id']}.html").exists())
        self.assertTrue((self.tmp / "a" / "index.html").exists())
        self.assertNotIn(gone["id"], (self.tmp / "sitemap.xml").read_text(encoding="utf-8"))

    def test_glossary_pages_optional(self):
        """data/glossary_pages.json（任意）があれば説明文と参考リンクを出す。無くても作れる。"""
        bp.build(self.tmp)
        gl = json.loads((self.tmp / "data" / "glossary.json").read_text(encoding="utf-8"))
        slugs = {f.stem for f in (self.tmp / "g").glob("*.html")}
        e = next(x for x in gl if bp.term_slug(x["term"]) in slugs)
        f = self.tmp / "g" / f"{bp.term_slug(e['term'])}.html"
        self.assertNotIn('class="g-intro"', f.read_text(encoding="utf-8"))
        extra = {e["term"]: {"intro": ["一つ目の<段落>。", "二つ目の段落。"], "refs": [{"title": "参考", "site": "どこか省", "url": "https://example.go.jp/x"}]}}
        (self.tmp / "data" / "glossary_pages.json").write_text(json.dumps(extra, ensure_ascii=False), encoding="utf-8")
        r = bp.build(self.tmp)
        t = f.read_text(encoding="utf-8")
        self.assertIn('<p class="g-intro">一つ目の&lt;段落&gt;。</p>', t)
        self.assertIn('href="https://example.go.jp/x"', t)
        self.assertIn(bp.page_url(f"g/{f.name}"), r["urls"])
        (self.tmp / "data" / "glossary_pages.json").write_text("[]", encoding="utf-8")  # 形が違っても止まらない
        bp.build(self.tmp)

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
        self.assertIn("M\tfeed.xml", out)
        self.assertIn("M\tm/index.html", out)
        self.assertEqual(rs.git("status", "--porcelain", "--", *rs.PAGE_PATHS)[1], "")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    unittest.main(verbosity=2)
