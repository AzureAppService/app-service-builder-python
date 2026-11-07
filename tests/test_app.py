import os
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from app import Handler, SampleHTTPServer


class DocumentationTests(unittest.TestCase):
    def test_readme_docs_host(self):
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
        self.assertIn("https://builder.appservice.azure.com/docs/", readme)
        self.assertNotIn("https://builderapps.azure.com/docs", readme)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        with patch("socket.getfqdn", side_effect=AssertionError("Unexpected DNS lookup")):
            self.server = SampleHTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive(), "Sample server did not stop")

    def assert_response(self, path, status, body, content_type="text/plain; charset=utf-8"):
        connection = HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            content = response.read()
            self.assertEqual(response.status, status)
            self.assertEqual(content, body.encode("utf-8"))
            self.assertEqual(response.getheader("Content-Length"), str(len(content)))
            self.assertEqual(
                response.getheader("Content-Type"), content_type
            )
        finally:
            connection.close()

    def test_health(self):
        self.assert_response("/health", 200, "OK\n")

    def test_unknown_path(self):
        self.assert_response("/not-found", 404, "Not found\n")

    def test_query_does_not_change_route(self):
        self.assert_response("/health?check=1", 200, "OK\n")

    def get_home(self, path="/"):
        connection = HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            content = response.read()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), "text/html; charset=utf-8")
            self.assertEqual(response.getheader("Content-Length"), str(len(content)))
            return content.decode("utf-8")
        finally:
            connection.close()

    def test_root_default_greeting_and_routes(self):
        body = self.get_home()
        self.assertTrue(body.startswith("<!doctype html>"))
        self.assertIn("<title>Python sample", body)
        self.assertIn('<h1 id="greeting">Hello', body)
        self.assertIn("App Service Builder / python-web: Hello", body)
        for path in ("/", "/health"):
            self.assertIn(f'href="{path}"', body)
        self.assertNotIn("{{GREETING}}", body)
        self.assertNotIn("/demo", body)
        self.assertIn('href="https://builder.appservice.azure.com/docs/"', body)
        self.assertIn('href="https://builder.appservice.azure.com/docs/quickstarts/portal/"', body)
        self.assertNotIn("https://builderapps.azure.com/docs", body)

    def test_root_escapes_public_greeting(self):
        os.environ["SAMPLE_GREETING"] = '<script>alert("Hi")</script> & café'
        os.environ["PRIVATE_TEST_VALUE"] = "must-not-appear"
        body = self.get_home()
        self.assertIn("&lt;script&gt;alert(&quot;Hi&quot;)&lt;/script&gt; &amp; café", body)
        self.assertNotIn("<script>", body)
        self.assertNotIn(os.environ["PRIVATE_TEST_VALUE"], body)

    def test_root_public_greeting(self):
        os.environ["SAMPLE_GREETING"] = "Welcome"
        self.assertIn('<h1 id="greeting">Welcome', self.get_home())

    def test_root_empty_greeting_uses_default(self):
        os.environ["SAMPLE_GREETING"] = ""
        self.assertIn('<h1 id="greeting">Hello', self.get_home())

    def test_root_query_does_not_change_route(self):
        self.assertEqual(self.get_home("/?preview=1"), self.get_home())

    def test_removed_route_returns_404(self):
        for path in ("/demo", "/demo?preview=1"):
            self.assert_response(path, 404, "Not found\n")

    def test_unsupported_methods_remain_unsupported(self):
        for path in ("/", "/health"):
            for method in ("POST", "HEAD"):
                with self.subTest(path=path, method=method):
                    connection = HTTPConnection(*self.server.server_address, timeout=5)
                    try:
                        connection.request(method, path)
                        response = connection.getresponse()
                        body = response.read()
                        self.assertEqual(response.status, 501)
                        if method == "HEAD":
                            self.assertEqual(body, b"")
                    finally:
                        connection.close()

    def test_bind_does_not_require_reverse_dns(self):
        self.assertEqual(self.server.server_name, "builder-python-sample")
        self.assertEqual(self.server.server_port, self.server.server_address[1])


if __name__ == "__main__":
    unittest.main()
