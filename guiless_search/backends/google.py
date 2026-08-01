import logging

from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from PySide6.QtCore import QUrl, QTimer
from PySide6.QtWebEngineCore import QWebEngineProfile

from .base import SearchEngine
from .. import config
from ..profile import inject_cookies

log = logging.getLogger("guiless-search")

_EXTRACT_JS = """\
(function() {
    var results = [];
    var seen = new Set();
    document.querySelectorAll('#rso div.tF2Cxc').forEach(function(div) {
        var a = div.querySelector('div.yuRUbf > a');
        if (!a) {
            var h3a = div.querySelector('a > h3');
            if (h3a) a = h3a.closest('a');
        }
        if (!a || !a.href) return;
        if (a.href.startsWith('javascript:')) return;
        if (seen.has(a.href)) return;
        seen.add(a.href);

        var h3 = div.querySelector('h3');
        var title = h3 ? h3.textContent.trim() : '';
        if (!title) return;

        var snippet = '';
        var sn = div.querySelector('div.VwiC3b') ||
                 div.querySelector('div[data-sncf]') ||
                 div.querySelector('span.aCOpRe') ||
                 div.querySelector('.IsZvec div');
        if (sn) snippet = sn.textContent.trim();

        results.push({link: a.href, title: title, snippet: snippet});
    });
    return JSON.stringify(results);
})()
"""

_PROBE_JS = "document.querySelectorAll('#rso div.tF2Cxc').length"

_CONSENT_DETECT_JS = """\
!!(document.querySelector('#L2AGLb') ||
   document.querySelector('[jsname="b3VHJd"]') ||
   document.querySelector('form[action*="consent"]'))
"""

_CONSENT_CLICK_JS = """\
(function() {
    var btn = document.querySelector('#L2AGLb') ||
              document.querySelector('[jsname="b3VHJd"]');
    if (btn) { btn.click(); return true; }
    return false;
})()
"""


def _decode_google_redirect(url: str) -> str:
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if hostname not in (
            "www.google.com", "google.com",
            "www.google.com.hk", "google.com.hk",
        ):
            return url
        if parsed.path != "/url":
            return url
        qs = parse_qs(parsed.query)
        for key in ("q", "url"):
            vals = qs.get(key)
            if vals and vals[0]:
                decoded = unquote(vals[0])
                if decoded.startswith("http"):
                    return decoded
    except Exception:
        pass
    return url


class GoogleEngine(SearchEngine):
    engine_name = "google"
    default_port = 8665

    def _build_search_url(self, query: str) -> str:
        params = [f"q={quote_plus(query)}"]
        return f"{config.GOOGLE_BASE_URL}/search?{'&'.join(params)}"

    def _probe_js(self) -> str:
        return _PROBE_JS

    def _extract_js(self) -> str:
        return _EXTRACT_JS

    def _decode_redirect(self, url: str) -> str:
        return _decode_google_redirect(url)

    def _max_results(self) -> int:
        return 10

    def _inject_cookies(self, profile: QWebEngineProfile) -> None:
        cookies = {
            "SOCS": "CAISHAgBEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmVuIAEaBgiA_LyaBg",
            "CONSENT": "PENDING+987",
        }
        inject_cookies(
            profile, ".google.com", cookies, config.GOOGLE_EXTRA_COOKIES,
        )

    # ── GDPR consent handling ──

    def _on_page_loaded(self, ok: bool) -> bool:
        self._page.runJavaScript(
            _CONSENT_DETECT_JS, 0, self._on_consent_check,
        )
        return False

    def _on_consent_check(self, is_consent) -> None:
        if self._current is None:
            return
        if is_consent:
            log.info("[%s] Consent page detected, processing consent dialog", self.engine_name)
            self._page.runJavaScript(
                _CONSENT_CLICK_JS, 0, self._on_consent_clicked,
            )
        else:
            self._start_probe()

    def _on_consent_clicked(self, clicked) -> None:
        if self._current is None:
            return
        if clicked:
            log.info("[%s] Consent accepted, waiting for redirect...", self.engine_name)
            QTimer.singleShot(2000, self._after_consent_redirect)
        else:
            log.warning("[%s] Could not find consent button", self.engine_name)
            self._start_probe()

    def _after_consent_redirect(self) -> None:
        if self._current is None:
            return
        url = self._build_search_url(self._current.query)
        page = self._ensure_page()
        page.loadFinished.connect(self._on_loaded)
        self._load_connected = True
        page.load(QUrl(url))
