import json
import logging

from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from PySide6.QtWebEngineCore import QWebEngineProfile

from .base import SearchEngine
from .. import config

log = logging.getLogger("guiless-search")

_EXTRACT_JS = """\
(function() {
    var results = [];
    document.querySelectorAll('.result.web-result').forEach(function(div) {
        var a = div.querySelector('a.result__a');
        if (!a || !a.href) return;
        var snippet = div.querySelector('a.result__snippet');
        results.push({
            link: a.href,
            title: (a.textContent || '').trim(),
            snippet: snippet ? (snippet.textContent || '').trim() : ''
        });
    });
    return JSON.stringify(results);
})()
"""

_PROBE_JS = "document.querySelectorAll('.result.web-result').length"


def _decode_ddg_redirect(url: str) -> str:
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if hostname not in (
            "duckduckgo.com", "www.duckduckgo.com",
            "html.duckduckgo.com", "lite.duckduckgo.com",
        ):
            return url
        if parsed.path != "/l/":
            return url
        qs = parse_qs(parsed.query)
        uddg = qs.get("uddg")
        if not uddg:
            return url
        decoded = unquote(uddg[0])
        if decoded.startswith("http"):
            return decoded
    except Exception:
        pass
    return url


class DuckDuckGoEngine(SearchEngine):
    engine_name = "duckduckgo"
    default_port = 8565

    def _build_search_url(self, query: str) -> str:
        q = quote_plus(query)
        params = [f"q={q}"]
        if config.DDG_REGION:
            params.append(f"kl={quote_plus(config.DDG_REGION)}")
        return f"{config.DDG_BASE_URL}/?{'&'.join(params)}"

    def _probe_js(self) -> str:
        return _PROBE_JS

    def _extract_js(self) -> str:
        return _EXTRACT_JS

    def _decode_redirect(self, url: str) -> str:
        return _decode_ddg_redirect(url)

    def _max_results(self) -> int:
        return 30
