"""Centralised configuration — env vars + CLI overrides merged at startup."""

import os

# ── Global ───────────────────────────────────────────────────────────────────
USER_AGENT = os.environ.get("USER_AGENT", "")
API_KEY = os.environ.get("API_KEY", "")
SEARCH_INTERVAL = float(os.environ.get("SEARCH_INTERVAL", "1"))
SEARCH_MODE = os.environ.get("SEARCH_MODE", "parallel")  # single | fallback | parallel
PARALLEL_TIMEOUT = float(os.environ.get("PARALLEL_TIMEOUT", "10"))
BACKENDS = os.environ.get("BACKENDS", "google,duckduckgo,sogou,bing")
DEFAULT_BACKEND = os.environ.get("DEFAULT_BACKEND", "google")

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8565"))
PROFILE_DIR = os.environ.get("PROFILE_DIR", "")

# ── DuckDuckGo ───────────────────────────────────────────────────────────────
DDG_BASE_URL = os.environ.get(
    "DDG_BASE_URL", "https://html.duckduckgo.com/html",
).rstrip("/")
DDG_REGION = os.environ.get("DDG_REGION", "").strip()

# ── Google ───────────────────────────────────────────────────────────────────
GOOGLE_BASE_URL = os.environ.get(
    "GOOGLE_BASE_URL", "https://www.google.com",
).rstrip("/")
GOOGLE_EXTRA_COOKIES = os.environ.get("GOOGLE_EXTRA_COOKIES", "")

# ── Bing ─────────────────────────────────────────────────────────────────────
BING_BASE_URL = os.environ.get(
    "BING_BASE_URL", "https://www.bing.com",
).rstrip("/")
BING_U_COOKIE = os.environ.get("BING_U_COOKIE", "")
BING_EXTRA_COOKIES = os.environ.get("BING_EXTRA_COOKIES", "")
BING_ENSEARCH = os.environ.get("BING_ENSEARCH", "").strip()

# ── Sogou ───────────────────────────────────────────────────────────────────
SOGOU_BASE_URL = os.environ.get(
    "SOGOU_BASE_URL", "https://www.sogou.com",
).rstrip("/")
