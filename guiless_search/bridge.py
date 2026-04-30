import queue
import threading


class SearchRequest:
    """Thread-safe bridge between HTTP handler threads and the Qt engine."""

    __slots__ = ("query", "count", "results", "done")

    def __init__(self, query: str, count: int):
        self.query = query
        self.count = count
        self.results: list[dict] = []
        self.done = threading.Event()


# Per-engine queues are created in backends/__init__.py and stored on each
# SearchEngine instance.  This module only defines the shared request type.
