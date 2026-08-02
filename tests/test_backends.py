import base64
import unittest
from unittest.mock import MagicMock, patch

from guiless_search.backends.bing import _decode_bing_redirect
from guiless_search.backends.duckduckgo import _decode_ddg_redirect
from guiless_search.backends.google import _decode_google_redirect
from guiless_search.backends.sogou import _decode_sogou_redirect


class GoogleRedirectTests(unittest.TestCase):
    def test_url_wrapper_is_unwrapped(self):
        self.assertEqual(
            _decode_google_redirect(
                "https://www.google.com/url?q=https%3A%2F%2Fexample.com%2Fp&sa=U"
            ),
            "https://example.com/p",
        )

    def test_non_wrapper_urls_pass_through(self):
        self.assertEqual(
            _decode_google_redirect("https://example.com/direct"),
            "https://example.com/direct",
        )
        self.assertEqual(
            _decode_google_redirect("https://www.google.com/search?q=x"),
            "https://www.google.com/search?q=x",
        )


class BingRedirectTests(unittest.TestCase):
    def test_ck_wrapper_is_unwrapped(self):
        encoded = base64.urlsafe_b64encode(b"https://example.com/page").decode().rstrip("=")
        self.assertEqual(
            _decode_bing_redirect(f"https://www.bing.com/ck/a?u=a1{encoded}"),
            "https://example.com/page",
        )

    def test_non_wrapper_urls_pass_through(self):
        self.assertEqual(
            _decode_bing_redirect("https://example.com/direct"),
            "https://example.com/direct",
        )


class DuckDuckGoRedirectTests(unittest.TestCase):
    def test_l_wrapper_is_unwrapped(self):
        self.assertEqual(
            _decode_ddg_redirect("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2F"),
            "https://example.com/",
        )

    def test_non_wrapper_urls_pass_through(self):
        self.assertEqual(
            _decode_ddg_redirect("https://example.com/direct"),
            "https://example.com/direct",
        )


class SogouRedirectTests(unittest.TestCase):
    def test_foreign_lookalike_host_is_not_fetched(self):
        self.assertEqual(
            _decode_sogou_redirect("https://sogou.com.evil.com/link?url=x"),
            "https://sogou.com.evil.com/link?url=x",
        )

    def test_non_sogou_urls_pass_through(self):
        self.assertEqual(
            _decode_sogou_redirect("https://example.com/link"),
            "https://example.com/link",
        )

    def test_link_resolves_location_replace(self):
        html = b'<script>window.location.replace("https://real.example/a")</script>'
        resp = MagicMock()
        resp.__enter__.return_value.read.return_value = html
        with patch("urllib.request.urlopen", return_value=resp):
            self.assertEqual(
                _decode_sogou_redirect("https://www.sogou.com/link?url=abc"),
                "https://real.example/a",
            )


if __name__ == "__main__":
    unittest.main()
