"""Multi-engine result aggregation, deduplication, and ranking.

The ranking strategy is intentionally simple and robust for automated
headless-browser search:

- URLs returned by more distinct engines rank higher.
- Ties are broken by the engine's position in the configured order.
- Final ties are broken by the original position within that engine.

Cross-engine agreement is the strongest available trust signal; we avoid
content-based heuristics because anti-bot garbage from some engines can
look structurally normal while being semantically irrelevant.
"""

import logging
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

log = logging.getLogger("guiless-search")

# Query parameters stripped during URL normalization.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "source", "si",
}


def normalize_url(url: str) -> str:
    """Return a canonical form of *url* for deduplication purposes.

    - lower-cases scheme and host
    - strips a single leading ``www.`` prefix
    - strips trailing slashes from the path
    - removes known tracking query parameters
    """
    try:
        p = urlparse(url.strip())
        scheme = p.scheme.lower()
        netloc = p.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = p.path.rstrip("/") or "/"

        if p.query:
            q = parse_qs(p.query, keep_blank_values=True)
            filtered = {
                k: v for k, v in q.items()
                if k.lower() not in _TRACKING_PARAMS
            }
            query = urlencode(filtered, doseq=True) if filtered else ""
        else:
            query = ""

        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return url


def aggregate_results(
    results_by_engine: dict[str, list[dict]],
    count: int,
    engine_order: list[str],
) -> list[dict]:
    """Merge results from multiple engines and rank them.

    Results are ranked by (in order of priority):

    - Number of distinct engines that returned the URL (more is better).
    - The earliest engine in *engine_order* that returned the URL.
    - Position within that engine's result list (earlier is better).

    Args:
        results_by_engine: Mapping ``engine_name -> list of raw results``.
        count: Maximum number of results to return.
        engine_order: Engine priority list used for tie-breaking.

    Returns:
        A list of result dicts, each containing ``link``, ``title``,
        and ``snippet``.
    """
    # Bucket by normalized URL
    buckets: dict[str, list[tuple[str, int, dict]]] = {}
    for engine_name, results in results_by_engine.items():
        for position, result in enumerate(results, start=1):
            raw_url = result.get("link", "")
            if not raw_url:
                continue
            norm = normalize_url(raw_url)
            buckets.setdefault(norm, []).append((engine_name, position, result))

    # Merge each bucket and compute sort keys
    items: list[dict] = []
    for norm_url, entries in buckets.items():
        # Distinct engines that returned this URL
        sources = list({e[0] for e in entries})
        engine_count = len(sources)

        # Merge titles / snippets: prefer the longest non-empty value
        titles = [(e[2].get("title") or "").strip() for e in entries]
        titles = [t for t in titles if t]
        best_title = max(titles, key=len) if titles else ""

        snippets = [(e[2].get("snippet") or "").strip() for e in entries]
        snippets = [s for s in snippets if s]
        best_snippet = max(snippets, key=len) if snippets else ""

        # Choose canonical link from the highest-priority engine
        best_link = ""
        for eng in engine_order:
            for e_name, _, e_result in entries:
                if e_name == eng and e_result.get("link"):
                    best_link = e_result["link"]
                    break
            if best_link:
                break
        if not best_link:
            best_link = norm_url

        # Determine the best (earliest-in-order) engine and its position
        best_engine = None
        best_position = 9999
        for eng in engine_order:
            for e_name, e_pos, _ in entries:
                if e_name == eng:
                    best_engine = e_name
                    best_position = e_pos
                    break
            if best_engine:
                break

        items.append({
            "link": best_link,
            "title": best_title,
            "snippet": best_snippet,
            "sources": sources,
            "_count": engine_count,
            "_best_engine": best_engine,
            "_best_pos": best_position,
        })

    # Sort
    def _sort_key(item: dict):
        best_idx = (
            engine_order.index(item["_best_engine"])
            if item["_best_engine"] in engine_order
            else 9999
        )
        return (-item["_count"], best_idx, item["_best_pos"])

    items.sort(key=_sort_key)

    # Format output (only standard fields exposed)
    output = []
    for item in items[:count]:
        output.append({
            "link": item["link"],
            "title": item["title"],
            "snippet": item["snippet"],
        })

    log.info(
        "Aggregated %d engines -> %d unique -> top %d",
        len(results_by_engine), len(items), len(output),
    )
    for i, item in enumerate(items[:count], 1):
        log.info(
            "  [%d] sources=%s | %s",
            i, ",".join(sorted(item["sources"])), item["title"],
        )

    return output
