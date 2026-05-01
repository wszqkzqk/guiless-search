import logging

from .base import SearchEngine
from .duckduckgo import DuckDuckGoEngine
from .google import GoogleEngine
from .bing import BingEngine
from .sogou import SogouEngine

log = logging.getLogger("guiless-search")

_ENGINE_MAP: dict[str, type[SearchEngine]] = {
    "google": GoogleEngine,
    "sogou": SogouEngine,
    "duckduckgo": DuckDuckGoEngine,
    "bing": BingEngine,
}

AVAILABLE_BACKENDS = list(_ENGINE_MAP.keys())


def create_engine(
    name: str,
    profile,
    search_interval: float = 1.0,
    search_timeout: float = 45.0,
    idle_timeout: float = 300.0,
) -> SearchEngine:
    """Create a search engine instance by name."""
    cls = _ENGINE_MAP.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown backend '{name}'. "
            f"Available: {', '.join(AVAILABLE_BACKENDS)}"
        )
    engine = cls(profile, search_interval, search_timeout, idle_timeout)
    engine._inject_cookies(profile)
    return engine
