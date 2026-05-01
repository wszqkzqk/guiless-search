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

    Subclasses implement:
        _build_search_url(query) -> str
        _probe_js() -> str
        _extract_js() -> str
        _decode_redirect(url) -> str
        _max_results() -> int

    The queue-poll → rate-limit → navigate → load-finish pipeline is
    handled here; subclasses control page-load behaviour via
    ``_on_page_loaded``.

    The QWebEnginePage is created lazily on the first search and
    released via ``LifecycleState.Discarded`` after ``idle_timeout``
    seconds of inactivity.  Discarded terminates the Chromium renderer
    process without calling ``deleteLater``, avoiding the known Qt
    object-lifecycle memory leak.
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
        search_timeout: float = 45.0,
        idle_timeout: float = 300.0,
    ):
        super().__init__()
        self._profile = profile
        self._search_interval = search_interval
        self._search_timeout = search_timeout
        self._idle_timeout = idle_timeout
        self._page: QWebEnginePage | None = None

        self._search_queue: queue.Queue[SearchRequest] = queue.Queue()
        self._current: SearchRequest | None = None
        self._last_search_time: float = 0.0
        self._search_start_time: float = 0.0
        self._poll_count: int = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(50)

        # Single-shot idle timer: releases the page after prolonged inactivity.
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._release_page)

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

    # ── Page lifecycle ──

    def _ensure_page(self) -> QWebEnginePage:
        """Return a usable QWebEnginePage, creating it on first call.

        If the page was previously discarded, transitions it back to
        ``Active``, which spawns a fresh renderer process and internally
        navigates to ``about:blank`` — the subsequent ``page.load()`` in
        ``_navigate`` supersedes that.
        """
        if self._page is None:
            log.info("[%s] Creating WebEnginePage (lazy)", self.engine_name)
            self._page = QWebEnginePage(self._profile, self)
            self._page.settings().setAttribute(
                QWebEngineSettings.WebAttribute.AutoLoadImages, False,
            )
            self._page.settings().setAttribute(
                QWebEngineSettings.WebAttribute.PluginsEnabled, False,
            )
            script = QWebEngineScript()
            script.setSourceCode(_BROWSER_INIT_JS)
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            script.setInjectionPoint(
                QWebEngineScript.InjectionPoint.DocumentCreation,
            )
            script.setRunsOnSubFrames(True)
            self._page.scripts().insert(script)
            return self._page
        if self._page.lifecycleState() != QWebEnginePage.LifecycleState.Active:
            log.info(
                "[%s] Reactivating WebEnginePage from %s",
                self.engine_name, self._page.lifecycleState(),
            )
            self._page.setLifecycleState(QWebEnginePage.LifecycleState.Active)
        return self._page

    def _release_page(self) -> None:
        """Discard the page via ``LifecycleState.Discarded``.

        This terminates the Chromium renderer process through Qt's own
        API and keeps the ``QWebEnginePage`` object alive for later
        reactivation, avoiding ``deleteLater`` entirely.
        """
        if self._page is None or self._current is not None:
            return
        log.info(
            "[%s] Discarding WebEnginePage (idle %.0fs)",
            self.engine_name, self._idle_timeout,
        )
        self._page.setLifecycleState(QWebEnginePage.LifecycleState.Discarded)

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
            if (
                self._search_start_time
                and time.monotonic() - self._search_start_time > self._search_timeout
            ):
                log.warning(
                    "[%s] Search hard-timeout after %.0fs, aborting",
                    self.engine_name, self._search_timeout,
                )
                self._finish([])
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
        self._idle_timer.stop()
        self._last_search_time = time.monotonic()
        log.info("[%s] Searching: '%s'", self.engine_name, self._current.query)
        self._navigate()

    def _navigate(self) -> None:
        assert self._current is not None
        page = self._ensure_page()
        self._search_start_time = time.monotonic()
        url = self._build_search_url(self._current.query)
        log.info("[%s] navigate %s", self.engine_name, url)
        page.loadFinished.connect(self._on_loaded)
        page.load(QUrl(url))

    def _on_loaded(self, ok: bool) -> None:
        self._page.loadFinished.disconnect(self._on_loaded)
        if self._current is None:
            return
        if self._page.url().toString() == "about:blank":
            self._page.loadFinished.connect(self._on_loaded)
            return
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
        if self._current is None:
            return
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
        if self._current is None:
            return
        results = parse_js(data)
        for r in results:
            if "link" in r:
                r["link"] = self._decode_redirect(r["link"])
        count = min(self._current.count, self._max_results())
        self._finish(results[:count])

    def _finish(self, results: list[dict]) -> None:
        if self._current is None:
            return
        req = self._current
        self._current = None
        self._search_start_time = 0.0
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
        # Schedule page release after idle timeout.
        if self._idle_timeout > 0:
            self._idle_timer.start(int(self._idle_timeout * 1000))
