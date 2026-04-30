import logging
import threading
from typing import Sequence

from .backends.base import SearchEngine
from . import config

log = logging.getLogger("guiless-search")


def search_with_fallback(
    query: str,
    count: int,
    engines: Sequence[SearchEngine],
    mode: str = "",
) -> tuple[list[dict], str]:
    """Execute a search using the configured mode.

    Returns (results, backend_name_used).

    Modes:
        single   — use the first engine only
        fallback — try engines in order, stop on first non-empty result
    """
    mode = mode or config.SEARCH_MODE

    if mode == "single" or len(engines) == 1:
        engine = engines[0]
        results = engine.search(query, count)
        return results, engine.engine_name

    # fallback (default)
    for engine in engines:
        results = engine.search(query, count)
        if results:
            return results, engine.engine_name
    return [], engines[-1].engine_name if engines else "none"
