import os
import unittest

from guiless_search.proxy import apply_proxy

_SAVED_ENV = dict(os.environ)


class ApplyProxyTests(unittest.TestCase):
    def setUp(self):
        for key in list(os.environ):
            if "proxy" in key.lower():
                del os.environ[key]
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(_SAVED_ENV)

    def _flags(self) -> str:
        return os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]

    def test_no_proxy_leaves_flags_untouched(self):
        self.assertEqual(apply_proxy(), "")
        self.assertEqual(self._flags(), "--disable-gpu")

    def test_explicit_proxy_applies_to_http_and_https(self):
        summary = apply_proxy("http://127.0.0.1:7890")
        self.assertEqual(
            summary, "http=http://127.0.0.1:7890;https=http://127.0.0.1:7890",
        )
        self.assertIn(
            "--proxy-server=http=http://127.0.0.1:7890;https=http://127.0.0.1:7890",
            self._flags(),
        )

    def test_invalid_explicit_proxy_rejected(self):
        with self.assertRaises(ValueError):
            apply_proxy("socks5://127.0.0.1:1080")

    def test_env_fallback(self):
        os.environ["http_proxy"] = "http://127.0.0.1:7890"
        apply_proxy()
        self.assertIn("--proxy-server=http=http://127.0.0.1:7890", self._flags())

    def test_invalid_env_proxy_ignored(self):
        os.environ["http_proxy"] = "socks5://127.0.0.1:1080"
        self.assertEqual(apply_proxy(), "")

    def test_no_proxy_becomes_bypass_list(self):
        os.environ["https_proxy"] = "http://127.0.0.1:7890"
        os.environ["no_proxy"] = "localhost, .example.com"
        apply_proxy()
        self.assertIn("--proxy-bypass-list=localhost;.example.com", self._flags())

    def test_user_supplied_flag_wins(self):
        os.environ["http_proxy"] = "http://127.0.0.1:7890"
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--proxy-server=http://10.0.0.1:8080"
        apply_proxy()
        self.assertEqual(self._flags().count("--proxy-server"), 1)
        self.assertIn("http://10.0.0.1:8080", self._flags())


if __name__ == "__main__":
    unittest.main()
