"""tools/review_server.py の守りの確認（python -m unittest tools/test_review_server_security.py）

- Host が localhost / 127.0.0.1 でなければ GET も POST も 403（DNS の差し替え対策）
- POST は Origin が確認ページと同じ・Sec-Fetch-Site が same-origin / none・Content-Type が application/json のときだけ通す
- 本物の data/ には触らない：通る POST の確認では manage を差し替える
"""
import http.client
import importlib.util
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

spec = importlib.util.spec_from_file_location("review_server", Path(__file__).resolve().parent / "review_server.py")
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)


class SecurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calls = []
        cls._manage = rs.manage
        rs.manage = lambda body: cls.calls.append(body) or {"ok": True}
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), rs.Handler)
        cls.port = cls.srv.server_address[1]
        cls._port = rs.PORT
        rs.PORT = cls.port
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        rs.manage = cls._manage
        rs.PORT = cls._port

    def setUp(self):
        self.calls.clear()

    def req(self, method, path, headers, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest(method, path, skip_host=True)
        for k, v in headers.items():
            c.putheader(k, v)
        data = body.encode("utf-8") if body is not None else b""
        if body is not None:
            c.putheader("Content-Length", str(len(data)))
        c.endheaders(data or None)
        r = c.getresponse()
        out = r.status, r.read()
        c.close()
        return out

    def post(self, **headers):
        h = {"Host": f"localhost:{self.port}", **headers}
        return self.req("POST", "/api/manage", h, json.dumps({"unpublish": ["x"]}))

    def test_post_evil_origin(self):
        status, b = self.post(**{"Origin": "https://evil.example", "Content-Type": "application/json"})
        self.assertEqual(status, 403)
        self.assertIn("error", json.loads(b))
        self.assertEqual(self.calls, [])

    def test_post_text_plain(self):
        status, _ = self.post(**{"Content-Type": "text/plain"})
        self.assertEqual(status, 403)
        self.assertEqual(self.calls, [])

    def test_post_cross_site(self):
        status, _ = self.post(**{"Sec-Fetch-Site": "cross-site", "Content-Type": "application/json"})
        self.assertEqual(status, 403)
        self.assertEqual(self.calls, [])

    def test_get_evil_host(self):
        for path in ("/api/drafts", "/api/config", "/review", "/"):
            status, _ = self.req("GET", path, {"Host": f"evil.example:{self.port}"})
            self.assertEqual(status, 403, path)

    def test_post_evil_host(self):
        status, _ = self.req("POST", "/api/manage", {"Host": f"evil.example:{self.port}",
                                                    "Content-Type": "application/json"}, "{}")
        self.assertEqual(status, 403)
        self.assertEqual(self.calls, [])

    def test_post_allowed(self):
        status, b = self.post(**{"Origin": f"http://localhost:{self.port}", "Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(b), {"ok": True})
        self.assertEqual(self.calls, [{"unpublish": ["x"]}])

    def test_get_config(self):
        status, b = self.req("GET", "/api/config", {"Host": f"127.0.0.1:{self.port}"})
        self.assertEqual(status, 200)
        json.loads(b)


if __name__ == "__main__":
    unittest.main()
