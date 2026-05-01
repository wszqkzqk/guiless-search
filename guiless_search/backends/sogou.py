import logging
import re
import urllib.request
from urllib.parse import quote_plus, urlparse

from PySide6.QtWebEngineCore import QWebEngineProfile

from .base import SearchEngine
from .. import config

log = logging.getLogger("guiless-search")

_EXTRACT_JS = """\
(function() {
    var results = [];
    document.querySelectorAll('div.vrwrap').forEach(function(div) {
        var a = div.querySelector('h3.vr-title a') || div.querySelector('a[id*="title"]');
        if (!a || !a.href) return;
        var title = (a.textContent || '').trim();
        if (!title) return;
        var snippet = div.querySelector('div.fz-mid.space-txt') ||
                      div.querySelector('div.ft');
        results.push({
            link: a.href,
            title: title,
            snippet: snippet ? (snippet.textContent || '').trim() : ''
        });
    });
    return JSON.stringify(results);
})()
"""

_PROBE_JS = "document.querySelectorAll('div.vrwrap').length"

_REDIRECT_RE = re.compile(
    r"""window\.location\.replace\(["']([^"']+)["']\)""",
    re.IGNORECASE,
)
_META_REFRESH_RE = re.compile(
    r"""<meta[^>]+http-equiv=["']refresh["'][^>]+content=["'][^"']*URL=([^"'>\s]+)["']""",
    re.IGNORECASE,
)


def _decode_sogou_redirect(url: str) -> str:
    try:
        parsed = urlparse(url)
        if not (parsed.hostname and 'sogou.com' in parsed.hostname and parsed.path == '/link'):
            return url
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read(4096).decode('utf-8', errors='replace')
        m = _REDIRECT_RE.search(html)
        if m:
            return m.group(1)
        m = _META_REFRESH_RE.search(html)
        if m:
            return m.group(1)
    except Exception:
        pass
    return url


class SogouEngine(SearchEngine):
    engine_name = "sogou"
    default_port = 8565

    def _build_search_url(self, query: str) -> str:
        q = quote_plus(query)
        return f"{config.SOGOU_BASE_URL}/web?query={q}"

    def _probe_js(self) -> str:
        return _PROBE_JS

    def _extract_js(self) -> str:
        return _EXTRACT_JS

    def _decode_redirect(self, url: str) -> str:
        return _decode_sogou_redirect(url)

    def _max_results(self) -> int:
        return 30
