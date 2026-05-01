import json
import logging
import re
from http.server import BaseHTTPRequestHandler

from . import config
from . import __version__
from .backends import AVAILABLE_BACKENDS
from .fallback import search_with_fallback
from .utils import format_results_markdown

log = logging.getLogger("guiless-search")

_MCP_PROTOCOL_VERSION = "2024-11-05"
_MCP_MAX_RESULT_CHARS = 120000


class SearchHandler(BaseHTTPRequestHandler):
    """Unified HTTP handler with /search, /search/{backend}, /mcp, /health."""

    # Will be set by __main__ before server starts
    engines: dict = {}  # name -> SearchEngine instance
    engine_order: list[str] = []

    def log_message(self, fmt, *args):
        log.info(fmt, *args)

    # ── Auth ──

    def _check_auth(self) -> bool:
        if not config.API_KEY:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:].strip()
            if token == config.API_KEY:
                return True
        self._send_json({"error": "unauthorized"}, 401)
        return False

    # ── Response helpers ──

    def _send_json(self, data, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: int = 204):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_mcp_result(self, request_id, result):
        self._send_json({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _send_mcp_error(self, request_id, code: int, message: str, data=None):
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        self._send_json({"jsonrpc": "2.0", "id": request_id, "error": error})

    def _read_json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            self._send_json({"error": "empty body"}, 400)
            return None
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, 400)
            return None

    # ── MCP tools ──

    @staticmethod
    def _mcp_tools() -> list[dict]:
        return [
            {
                "name": "search_web",
                "description": (
                    "Search the web and return a structured list of results "
                    "including title, URL, and snippet. Supports multiple "
                    "backends: google, duckduckgo, sogou, bing. When backend "
                    "is 'auto' or omitted, uses the configured search mode."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string.",
                        },
                        "count": {
                            "type": "integer",
                            "description": (
                                "Max number of results to return (1-30). "
                                "Defaults to 5."
                            ),
                            "minimum": 1,
                            "maximum": 30,
                        },
                        "backend": {
                            "type": "string",
                            "enum": AVAILABLE_BACKENDS + ["auto"],
                            "description": (
                            "Search backend. 'auto' uses the configured "
                            "SEARCH_MODE. Defaults to 'auto'."
                            ),
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "_meta": {
                    "anthropic/maxResultSizeChars": _MCP_MAX_RESULT_CHARS,
                },
            },
        ]

    def _mcp_call_search_web(self, params: dict) -> dict:
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be an object")

        query = arguments.get("query")
        if not isinstance(query, str):
            raise ValueError("arguments.query must be a string")
        query = query.strip()
        if not query:
            raise ValueError("arguments.query is required")

        count = arguments.get("count", 5)
        if not isinstance(count, int):
            raise ValueError("arguments.count must be an integer")
        if count < 1 or count > 30:
            raise ValueError("arguments.count must be in range [1, 30]")

        backend = arguments.get("backend", "auto")

        if backend == "auto":
            ordered = [self.engines[n] for n in self.engine_order if n in self.engines]
            results, used = search_with_fallback(query, count, ordered)
        else:
            engine = self.engines.get(backend)
            if engine is None:
                raise ValueError(
                    f"Unknown backend '{backend}'. "
                    f"Available: {', '.join(AVAILABLE_BACKENDS)}"
                )
            results = engine.search(query, count)
            used = backend

        markdown = format_results_markdown(results)
        return {
            "content": [{"type": "text", "text": markdown}],
            "structuredContent": {
                "query": query,
                "count": count,
                "backend": used,
                "results": results,
            },
            "isError": False,
        }

    # ── MCP JSON-RPC dispatch ──

    def _handle_mcp(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            self._send_mcp_error(
                None, -32600, "Invalid Request", {"reason": "empty body"},
            )
            return

        try:
            body = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send_mcp_error(None, -32700, "Parse error")
            return

        if not isinstance(body, dict):
            self._send_mcp_error(None, -32600, "Invalid Request")
            return

        has_id = "id" in body
        request_id = body.get("id")
        method = body.get("method")
        params = body.get("params", {})

        if (
            body.get("jsonrpc") != "2.0"
            or not isinstance(method, str)
            or not method
        ):
            self._send_mcp_error(
                request_id if has_id else None, -32600, "Invalid Request",
            )
            return

        if not isinstance(params, dict):
            if has_id:
                self._send_mcp_error(
                    request_id, -32602, "Invalid params",
                    {"reason": "params must be an object"},
                )
            else:
                self._send_empty()
            return

        if not has_id:
            self._send_empty()
            return

        if method == "initialize":
            self._send_mcp_result(
                request_id,
                {
                    "protocolVersion": _MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "guiless-search",
                        "version": __version__,
                    },
                },
            )
            return

        if method == "ping":
            self._send_mcp_result(request_id, {})
            return

        if method == "notifications/initialized":
            self._send_mcp_result(request_id, {})
            return

        if method == "tools/list":
            self._send_mcp_result(request_id, {"tools": self._mcp_tools()})
            return

        if method == "tools/call":
            try:
                result = self._mcp_call_search_web(params)
            except ValueError as e:
                self._send_mcp_error(
                    request_id, -32602, "Invalid params",
                    {"reason": str(e)},
                )
                return
            self._send_mcp_result(request_id, result)
            return

        self._send_mcp_error(request_id, -32601, "Method not found")

    # ── HTTP routing ──

    def do_GET(self):
        if self.path == "/health":
            status_map = {}
            for name, engine in self.engines.items():
                status_map[name] = "ok"
            self._send_json({"status": "ok", "backends": status_map})
        else:
            if not self._check_auth():
                return
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._check_auth():
            return

        if self.path in ("/mcp", "/mcp/"):
            self._handle_mcp()
            return

        # /search or /search/{backend}
        if self.path == "/search":
            backend = None
        elif self.path.startswith("/search/"):
            backend = self.path[len("/search/"):]
            if "/" in backend:
                self._send_json({"error": "not found"}, 404)
                return
        else:
            self._send_json({"error": "not found"}, 404)
            return

        body = self._read_json_body()
        if body is None:
            return

        query = body.get("query", "").strip()
        count = body.get("count", 5)
        if not query:
            self._send_json({"error": "query is required"}, 400)
            return
        if not isinstance(count, int) or count < 1:
            count = 5
        count = min(count, 30)

        if backend:
            engine = self.engines.get(backend)
            if engine is None:
                self._send_json(
                    {"error": f"Unknown backend '{backend}'"}, 400,
                )
                return
            log.info("Request: query='%s', count=%d, backend=%s", query, count, backend)
            results = engine.search(query, count)
        else:
            ordered = [
                self.engines[n]
                for n in self.engine_order
                if n in self.engines
            ]
            log.info(
                "Request: query='%s', count=%d, mode=%s",
                query, count, config.SEARCH_MODE,
            )
            results, _ = search_with_fallback(query, count, ordered)

        self._send_json(results)
