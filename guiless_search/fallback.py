import concurrent.futures
import logging
from typing import Sequence

from .aggregator import aggregate_results
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
        single    — use the first engine only
        fallback  — try engines in order, stop on first non-empty result
        parallel  — query all engines concurrently, aggregate & deduplicate
    """
    mode = mode or config.SEARCH_MODE

    if mode == "single" or len(engines) == 1:
        engine = engines[0]
        results = engine.search(query, count)
        return results, engine.engine_name

    if mode == "parallel":
        return _search_parallel(query, count, engines)

    # fallback mode (catch-all)
    for engine in engines:
        results = engine.search(query, count)
        if results:
            return results, engine.engine_name
    return [], engines[-1].engine_name if engines else "none"


def _search_parallel(
    query: str,
    count: int,
    engines: Sequence[SearchEngine],
) -> tuple[list[dict], str]:
    """Query all engines in parallel and aggregate the results."""
    timeout = getattr(config, "PARALLEL_TIMEOUT", 10.0)
    futures: dict[concurrent.futures.Future, SearchEngine] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(engines)) as executor:
        for engine in engines:
            futures[
                executor.submit(engine.search, query, count, timeout)
            ] = engine

        done, not_done = concurrent.futures.wait(
            futures,
            timeout=timeout,
            return_when=concurrent.futures.ALL_COMPLETED,
        )

        results_by_engine: dict[str, list[dict]] = {}
        for fut in done:
            eng = futures[fut]
            try:
                results_by_engine[eng.engine_name] = fut.result()
            except Exception as exc:
                log.warning("[%s] Parallel search error: %s", eng.engine_name, exc)
                results_by_engine[eng.engine_name] = []

        for fut in not_done:
            eng = futures[fut]
            log.warning(
                "[%s] Parallel search timed out after %.0fs",
                eng.engine_name, timeout,
            )
            results_by_engine[eng.engine_name] = []

    engine_order = [e.engine_name for e in engines]
    aggregated = aggregate_results(results_by_engine, count, engine_order)
    return aggregated, "parallel"
