import logging
import queue
import random
import time

from PySide6.QtCore import QObject, QUrl, QTimer
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineSettings,
)

from ..browser_init import _BROWSER_INIT_JS
from ..bridge import SearchRequest
from ..utils import parse_js

log = logging.getLogger("guiless-search")


class SearchEngine(QObject):
    """Base class for headless search engines.

    Subclasses must implement:
        _build_search_url(query) -> str
        _probe_js() -> str
        _extract_js() -> str
        _decode_redirect(url) -> str
        _max_results() -> int

    The common queue-poll → rate-limit → navigate → load-finish pipeline is
    handled here; the subclass controls what happens after the page loads via
    ``_on_page_loaded``.
    """

    # ── Class-level attributes for the registry ──
    engine_name: str = ""
    default_port: int = 0

    # ── Unified probe parameters ──
    _PROBE_INTERVAL_MS = 200
    _MAX_PROBES = 20

    def __init__(
        self,
        profile: QWebEngineProfile,
        search_interval: float = 1.0,
    ):
        super().__init__()
        self._search_interval = search_interval
        self._page = QWebEnginePage(profile, self)
        self._page.settings().setAttribute(
            QWebEngineSettings.WebAttribute.AutoLoadImages, False,
        )
        self._page.settings().setAttribute(
            QWebEngineSettings.WebAttribute.PluginsEnabled, False,
        )

        # Inject browser-normalization JS at DocumentCreation in MainWorld
        script = QWebEngineScript()
        script.setSourceCode(_BROWSER_INIT_JS)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setInjectionPoint(
            QWebEngineScript.InjectionPoint.DocumentCreation,
        )
        script.setRunsOnSubFrames(True)
        self._page.scripts().insert(script)

        self._search_queue: queue.Queue[SearchRequest] = queue.Queue()
        self._current: SearchRequest | None = None
        self._last_search_time: float = 0.0
        self._poll_count: int = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(50)

    # ── Subclass MUST implement ──

    def _build_search_url(self, query: str) -> str:
        raise NotImplementedError

    def _probe_js(self) -> str:
        raise NotImplementedError

    def _extract_js(self) -> str:
        raise NotImplementedError

    def _decode_redirect(self, url: str) -> str:
        raise NotImplementedError

    def _max_results(self) -> int:
        raise NotImplementedError

    # ── Optional hooks ──

    def _inject_cookies(self, profile: QWebEngineProfile) -> None:
        """Inject engine-specific cookies.  Called once at construction."""

    def _on_page_loaded(self, ok: bool) -> bool:
        """Called after loadFinished.  Return True to start probing,
        False if the subclass has taken over the flow (e.g. Google
        consent handling)."""
        return True

    # ── Public entry point used by the server ──

    def search(
        self, query: str, count: int = 10, timeout: float = 30.0,
    ) -> list[dict]:
        """Enqueue a search request and block until results arrive."""
        req = SearchRequest(query, count)
        self._search_queue.put(req)
        if not req.done.wait(timeout=timeout):
            log.warning("[%s] Search timed out: '%s'", self.engine_name, query)
        return req.results

    # ── Queue poll + rate limiting ──

    def _poll(self) -> None:
        if self._current is not None:
            return
        try:
            self._current = self._search_queue.get_nowait()
        except queue.Empty:
            return

        if self._search_interval > 0:
            elapsed = time.monotonic() - self._last_search_time
            jitter = random.uniform(0, self._search_interval * 0.5)
            required = self._search_interval + jitter
            if elapsed < required:
                delay_ms = int((required - elapsed) * 1000)
                QTimer.singleShot(delay_ms, self._start_search)
                return

        self._start_search()

    def _start_search(self) -> None:
        assert self._current is not None
        self._last_search_time = time.monotonic()
        log.info("[%s] Searching: '%s'", self.engine_name, self._current.query)
        self._navigate()

    def _navigate(self) -> None:
        assert self._current is not None
        url = self._build_search_url(self._current.query)
        log.info("[%s] navigate %s", self.engine_name, url)
        self._page.loadFinished.connect(self._on_loaded)
        self._page.load(QUrl(url))

    def _on_loaded(self, ok: bool) -> None:
        self._page.loadFinished.disconnect(self._on_loaded)
        if not ok:
            log.warning("[%s] Page load failed", self.engine_name)
            self._finish([])
            return
        log.info("[%s] Page loaded: %s", self.engine_name, self._page.url().toString())
        if self._on_page_loaded(ok):
            self._start_probe()

    # ── Probe / extract pipeline (subclasses may call directly) ──

    def _start_probe(self) -> None:
        self._poll_count = 0
        QTimer.singleShot(self._PROBE_INTERVAL_MS, self._probe)

    def _probe(self) -> None:
        self._poll_count += 1
        self._page.runJavaScript(self._probe_js(), 0, self._on_probe)

    def _on_probe(self, n) -> None:
        n = int(n) if n else 0
        if n > 0:
            self._extract()
        elif self._poll_count < self._MAX_PROBES:
            QTimer.singleShot(self._PROBE_INTERVAL_MS, self._probe)
        else:
            log.warning(
                "[%s] No results after %d polls, extracting anyway",
                self.engine_name, self._poll_count,
            )
            self._extract()

    def _extract(self) -> None:
        self._page.runJavaScript(self._extract_js(), 0, self._on_results)

    def _on_results(self, data) -> None:
        assert self._current is not None
        results = parse_js(data)
        for r in results:
            if "link" in r:
                r["link"] = self._decode_redirect(r["link"])
        count = min(self._current.count, self._max_results())
        self._finish(results[:count])

    def _finish(self, results: list[dict]) -> None:
        assert self._current is not None
        req = self._current
        self._current = None
        req.results = results
        req.done.set()
        log.info(
            "[%s] Query '%s' -> %d results",
            self.engine_name, req.query, len(results),
        )
        for i, r in enumerate(results, 1):
            log.info(
                "  [%d] %s | %s",
                i, r.get("title", ""), r.get("link", ""),
            )
