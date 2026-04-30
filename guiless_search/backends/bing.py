import base64
import json
import logging

from urllib.parse import parse_qs, quote_plus, urlparse

from PySide6.QtWebEngineCore import QWebEngineProfile

from .base import SearchEngine
from .. import config
from ..profile import inject_cookies

log = logging.getLogger("guiless-search")

_EXTRACT_JS = """\
(function() {
    var results = [];
    document.querySelectorAll('li.b_algo').forEach(function(li) {
        var a = li.querySelector('h2 a');
        if (!a || !a.href) return;
        var p = li.querySelector('.b_caption p') ||
                li.querySelector('.b_lineclamp') ||
                li.querySelector('.b_algoSlug');
        results.push({
            link: a.href,
            title: (a.textContent || '').trim(),
            snippet: p ? (p.textContent || '').trim() : ''
        });
    });
    return JSON.stringify(results);
})()
"""

_PROBE_JS = "document.querySelectorAll('li.b_algo').length"


def _resolve_ensearch() -> tuple[str, str, str]:
    hostname = (urlparse(config.BING_BASE_URL).hostname or "").lower()
    is_cn_host = hostname == "cn.bing.com"

    if config.BING_ENSEARCH == "0":
        return "", "QBLH", "local/forced"
    if config.BING_ENSEARCH == "1":
        return ("1", "QBLHCN", "intl/forced") if is_cn_host else (
            "", "QBLHCN", "intl/forced",
        )
    if is_cn_host:
        return "1", "QBLHCN", "intl/auto-cn"
    return "", "QBLHCN", "intl/auto"


def _decode_bing_redirect(url: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.hostname not in ("www.bing.com", "bing.com", "cn.bing.com"):
            return url
        if parsed.path != "/ck/a":
            return url
        qs = parse_qs(parsed.query)
        u_vals = qs.get("u")
        if not u_vals or not u_vals[0].startswith("a1"):
            return url
        encoded = u_vals[0][2:]
        padded = encoded + "=" * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode(
            "utf-8", errors="replace",
        )
        if decoded.startswith("http"):
            return decoded
    except Exception:
        pass
    return url


class BingEngine(SearchEngine):
    engine_name = "bing"
    default_port = 8765

    def _build_search_url(self, query: str) -> str:
        q = quote_plus(query)
        ensearch_param, form_code, mode = _resolve_ensearch()
        params = [f"q={q}", f"form={form_code}"]
        if ensearch_param:
            params.append(f"ensearch={ensearch_param}")
        url = f"{config.BING_BASE_URL}/search?{'&'.join(params)}"
        log.info("[%s] navigate %s (%s)", self.engine_name, url, mode)
        return url

    def _probe_js(self) -> str:
        return _PROBE_JS

    def _extract_js(self) -> str:
        return _EXTRACT_JS

    def _decode_redirect(self, url: str) -> str:
        return _decode_bing_redirect(url)

    def _max_results(self) -> int:
        return 30

    def _inject_cookies(self, profile: QWebEngineProfile) -> None:
        cookies: dict[str, str] = {}
        if config.BING_U_COOKIE:
            cookies["_U"] = config.BING_U_COOKIE
        inject_cookies(
            profile, ".bing.com", cookies, config.BING_EXTRA_COOKIES,
        )
