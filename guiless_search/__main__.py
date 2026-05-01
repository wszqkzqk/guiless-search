#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Copyright (C) 2026 Zhou Qiankang <wszqkzqk@qq.com>
#
# This file is part of GUI-Less Search.
#
# GUI-Less Search is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# GUI-Less Search is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with GUI-Less Search. If not, see <https://www.gnu.org/licenses/>.

"""CLI entry point for guiless-search."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--disable-gpu --disable-software-rasterizer",
)

import argparse
import logging
import signal
import threading
from http.server import HTTPServer

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from . import config, __version__
from .backends import create_engine, AVAILABLE_BACKENDS
from .profile import build_profile, default_profile_dir
from .server import SearchHandler

log = logging.getLogger("guiless-search")


def main():
    parser = argparse.ArgumentParser(
        description="GUI-Less Search — Multi-backend headless web search proxy",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--host", default=os.environ.get("HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--port", type=int,
        default=int(os.environ.get("PORT", "8565")),
    )
    parser.add_argument(
        "--backends", default=None,
        help="Comma-separated list of backends to enable (default: google,duckduckgo,sogou,bing)",
    )
    parser.add_argument(
        "--default-backend", default=None,
        help="Default backend for /search (default: google)",
    )
    parser.add_argument(
        "--search-mode", default=None,
        choices=["single", "fallback", "parallel"],
        help="Search mode: single, fallback, or parallel (default: parallel)",
    )
    parser.add_argument(
        "--parallel-timeout", type=float, default=None,
        help="Max seconds to wait for all parallel engines (default: 10)",
    )
    parser.add_argument(
        "--search-interval", type=float, default=None,
        help="Global minimum seconds between searches per engine (default: 1)",
    )
    parser.add_argument(
        "--api-key", default=None,
        help="API key for Bearer token authentication (optional)",
    )
    parser.add_argument(
        "--profile-dir", default=None,
        help="Custom profile directory",
    )
    parser.add_argument(
        "--user-agent", default=None,
        help="Custom User-Agent string",
    )
    # ── Engine-specific options ──
    parser.add_argument("--ddg-base-url", default=None)
    parser.add_argument("--ddg-region", default=None)
    parser.add_argument("--google-base-url", default=None)
    parser.add_argument("--google-cookies", default=None)
    parser.add_argument("--bing-base-url", default=None)
    parser.add_argument("--bing-u-cookie", default=None)
    parser.add_argument("--bing-cookies", default=None)
    parser.add_argument("--bing-ensearch", default=None)
    parser.add_argument("--sogou-base-url", default=None)

    args = parser.parse_args()

    # ── Apply CLI overrides to config ──
    if args.host:
        config.HOST = args.host
    if args.port:
        config.PORT = args.port
    if args.backends is not None:
        config.BACKENDS = args.backends
    if args.default_backend is not None:
        config.DEFAULT_BACKEND = args.default_backend
    if args.search_mode is not None:
        config.SEARCH_MODE = args.search_mode
    if args.search_interval is not None:
        config.SEARCH_INTERVAL = args.search_interval
    if args.parallel_timeout is not None:
        config.PARALLEL_TIMEOUT = args.parallel_timeout
    if args.api_key is not None:
        config.API_KEY = args.api_key
    if args.profile_dir is not None:
        config.PROFILE_DIR = args.profile_dir
    if args.user_agent is not None:
        config.USER_AGENT = args.user_agent
    if args.ddg_base_url is not None:
        config.DDG_BASE_URL = args.ddg_base_url.rstrip("/")
    if args.ddg_region is not None:
        config.DDG_REGION = args.ddg_region.strip()
    if args.google_base_url is not None:
        config.GOOGLE_BASE_URL = args.google_base_url.rstrip("/")
    if args.google_cookies is not None:
        config.GOOGLE_EXTRA_COOKIES = args.google_cookies
    if args.bing_base_url is not None:
        config.BING_BASE_URL = args.bing_base_url.rstrip("/")
    if args.bing_u_cookie is not None:
        config.BING_U_COOKIE = args.bing_u_cookie
    if args.bing_cookies is not None:
        config.BING_EXTRA_COOKIES = args.bing_cookies
    if args.bing_ensearch is not None:
        config.BING_ENSEARCH = args.bing_ensearch.strip()
    if args.sogou_base_url is not None:
        config.SOGOU_BASE_URL = args.sogou_base_url.rstrip("/")

    # ── Parse backend list ──
    backend_names = [b.strip() for b in config.BACKENDS.split(",") if b.strip()]
    for name in backend_names:
        if name not in AVAILABLE_BACKENDS:
            log.error("Unknown backend: '%s'. Available: %s", name, AVAILABLE_BACKENDS)
            sys.exit(1)

    if config.DEFAULT_BACKEND not in backend_names:
        log.warning(
            "Default backend '%s' not in enabled backends, using '%s'",
            config.DEFAULT_BACKEND, backend_names[0],
        )
        config.DEFAULT_BACKEND = backend_names[0]

    # ── Ensure profile dir ──
    storage = config.PROFILE_DIR or default_profile_dir("guiless-search")
    os.makedirs(storage, exist_ok=True)
    if "XDG_DATA_HOME" not in os.environ:
        os.environ["XDG_DATA_HOME"] = storage

    # ── Qt app ──
    app = QApplication(sys.argv)
    app.setApplicationName("guiless-search")

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: app.quit())
    _sig_timer = QTimer()
    _sig_timer.start(500)
    _sig_timer.timeout.connect(lambda: None)

    profile = build_profile(app, storage)

    # ── Create engines ──
    engines = {}
    engine_order = []
    for name in backend_names:
        if name == config.DEFAULT_BACKEND:
            engine_order.insert(0, name)
        else:
            engine_order.append(name)
    for name in engine_order:
        engines[name] = create_engine(name, profile, config.SEARCH_INTERVAL)

    # Inject into handler class
    SearchHandler.engines = engines
    SearchHandler.engine_order = engine_order

    # ── HTTP server ──
    server = HTTPServer((config.HOST, config.PORT), SearchHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    log.info("Listening on http://%s:%d", config.HOST, config.PORT)
    log.info(
        "  backends: %s, default: %s, mode: %s, interval: %.1fs, auth: %s",
        ",".join(backend_names),
        config.DEFAULT_BACKEND,
        config.SEARCH_MODE,
        config.SEARCH_INTERVAL,
        "enabled" if config.API_KEY else "disabled",
    )

    try:
        app.exec()
    finally:
        server.shutdown()
        server.server_close()
        log.info("Shutdown complete")


if __name__ == "__main__":
    main()
