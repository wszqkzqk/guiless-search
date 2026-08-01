import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from guiless_search import config
from guiless_search.server import _MAX_BODY_SIZE, SearchHandler

_RESULTS = [{"link": "https://x.example", "title": "t", "snippet": "s"}]


def make_handler(body: bytes = b"", *, path: str = "/search", headers: dict | None = None) -> SearchHandler:
    handler = object.__new__(SearchHandler)
    handler.path = path
    handler.headers = {"Content-Length": str(len(body)), **(headers or {})}
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    return handler


def status_of(handler) -> int:
    return handler.send_response.call_args[0][0]


def body_of(handler):
    return json.loads(handler.wfile.getvalue())


class RestContractTests(unittest.TestCase):
    def setUp(self):
        self._api_key = config.API_KEY
        config.API_KEY = ""
        engine = SimpleNamespace(
            engine_name="stub", search=Mock(return_value=list(_RESULTS)),
        )
        SearchHandler.engines = {"stub": engine}
        SearchHandler.engine_order = ["stub"]
        self.engine = engine

    def tearDown(self):
        config.API_KEY = self._api_key

    def test_health_needs_no_auth(self):
        config.API_KEY = "secret"
        handler = make_handler(path="/health")
        handler.do_GET()
        self.assertEqual(status_of(handler), 200)
        self.assertEqual(body_of(handler)["status"], "ok")

    def test_auth_rejects_and_accepts(self):
        config.API_KEY = "secret"
        handler = make_handler(b'{"query": "q"}')
        handler.do_POST()
        self.assertEqual(status_of(handler), 401)

        handler = make_handler(
            b'{"query": "q"}', headers={"Authorization": "Bearer secret"},
        )
        handler.do_POST()
        self.assertEqual(status_of(handler), 200)

    def test_non_numeric_content_length(self):
        handler = make_handler(headers={"Content-Length": "abc"})
        handler.do_POST()
        self.assertEqual(status_of(handler), 400)

    def test_negative_content_length(self):
        handler = make_handler(headers={"Content-Length": "-1"})
        handler.do_POST()
        self.assertEqual(status_of(handler), 400)

    def test_oversized_body(self):
        handler = make_handler(headers={"Content-Length": str(_MAX_BODY_SIZE + 1)})
        handler.do_POST()
        self.assertEqual(status_of(handler), 413)

    def test_empty_body(self):
        handler = make_handler()
        handler.do_POST()
        self.assertEqual(status_of(handler), 400)

    def test_invalid_json(self):
        handler = make_handler(b"{")
        handler.do_POST()
        self.assertEqual(status_of(handler), 400)

    def test_non_object_json(self):
        handler = make_handler(b"[1, 2]")
        handler.do_POST()
        self.assertEqual(status_of(handler), 400)

    def test_non_string_query(self):
        handler = make_handler(b'{"query": 123}')
        handler.do_POST()
        self.assertEqual(status_of(handler), 400)

    def test_valid_search(self):
        handler = make_handler(b'{"query": "q", "count": 3}', path="/search/stub")
        handler.do_POST()
        self.assertEqual(status_of(handler), 200)
        self.engine.search.assert_called_once_with("q", 3)
        self.assertEqual(body_of(handler), _RESULTS)

    def test_count_is_clamped(self):
        handler = make_handler(b'{"query": "q", "count": 100}', path="/search/stub")
        handler.do_POST()
        self.engine.search.assert_called_once_with("q", 30)

    def test_unknown_backend(self):
        handler = make_handler(b'{"query": "q"}', path="/search/nope")
        handler.do_POST()
        self.assertEqual(status_of(handler), 400)

    def test_unknown_path(self):
        handler = make_handler(b'{"query": "q"}', path="/other")
        handler.do_POST()
        self.assertEqual(status_of(handler), 404)

    def test_auto_mode_aggregates(self):
        handler = make_handler(b'{"query": "q"}')
        handler.do_POST()
        self.assertEqual(status_of(handler), 200)
        self.assertEqual(body_of(handler), _RESULTS)


class McpContractTests(unittest.TestCase):
    def setUp(self):
        self._api_key = config.API_KEY
        config.API_KEY = ""
        engine = SimpleNamespace(
            engine_name="stub", search=Mock(return_value=list(_RESULTS)),
        )
        SearchHandler.engines = {"stub": engine}
        SearchHandler.engine_order = ["stub"]

    def tearDown(self):
        config.API_KEY = self._api_key

    def _post(self, payload: bytes) -> SearchHandler:
        handler = make_handler(payload, path="/mcp")
        handler.do_POST()
        return handler

    def test_initialize(self):
        handler = self._post(b'{"jsonrpc": "2.0", "id": 1, "method": "initialize"}')
        self.assertEqual(body_of(handler)["result"]["serverInfo"]["name"], "guiless-search")

    def test_tools_call(self):
        handler = self._post(
            b'{"jsonrpc": "2.0", "id": 2, "method": "tools/call",'
            b' "params": {"name": "query", "arguments": {"query": "q", "backend": "stub"}}}'
        )
        result = body_of(handler)["result"]
        self.assertEqual(result["structuredContent"]["backend"], "stub")
        self.assertFalse(result["isError"])

    def test_tools_call_invalid_count(self):
        handler = self._post(
            b'{"jsonrpc": "2.0", "id": 3, "method": "tools/call",'
            b' "params": {"name": "query", "arguments": {"query": "q", "count": 0}}}'
        )
        self.assertEqual(body_of(handler)["error"]["code"], -32602)

    def test_tools_call_unknown_backend(self):
        handler = self._post(
            b'{"jsonrpc": "2.0", "id": 4, "method": "tools/call",'
            b' "params": {"name": "query", "arguments": {"query": "q", "backend": "nope"}}}'
        )
        self.assertEqual(body_of(handler)["error"]["code"], -32602)

    def test_notification_gets_no_response_body(self):
        handler = self._post(b'{"jsonrpc": "2.0", "method": "notifications/initialized"}')
        self.assertEqual(status_of(handler), 204)
        self.assertEqual(handler.wfile.getvalue(), b"")

    def test_parse_error(self):
        handler = self._post(b"{")
        self.assertEqual(body_of(handler)["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
