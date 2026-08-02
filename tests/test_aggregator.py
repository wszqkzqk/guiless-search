import unittest

from guiless_search.aggregator import aggregate_results, normalize_url


class NormalizeUrlTests(unittest.TestCase):
    def test_strips_tracking_params_and_normalizes(self):
        self.assertEqual(
            normalize_url("HTTPS://WWW.Example.COM/a/?utm_source=g&id=2"),
            "https://example.com/a?id=2",
        )

    def test_tracking_only_query_is_dropped(self):
        self.assertEqual(
            normalize_url("https://example.com/?gclid=9"),
            "https://example.com/",
        )

    def test_keeps_real_params(self):
        self.assertEqual(
            normalize_url("https://example.com/p?id=1&id=2"),
            "https://example.com/p?id=1&id=2",
        )


class AggregateResultsTests(unittest.TestCase):
    def test_cross_engine_agreement_ranks_first(self):
        results = {
            "bing": [
                {"link": "https://b.example/2", "title": "B", "snippet": "sb"},
                {"link": "https://a.example/1?utm_source=n", "title": "A2", "snippet": "sa"},
            ],
            "google": [
                {"link": "https://a.example/1", "title": "A", "snippet": "sa"},
            ],
        }
        out = aggregate_results(results, 10, ["google", "bing"])
        self.assertEqual(
            [r["link"] for r in out],
            ["https://a.example/1", "https://b.example/2"],
        )

    def test_engine_order_breaks_ties(self):
        results = {
            "sogou": [{"link": "https://s.example/1", "title": "S", "snippet": ""}],
            "bing": [{"link": "https://b.example/1", "title": "B", "snippet": ""}],
        }
        out = aggregate_results(results, 10, ["bing", "sogou"])
        self.assertEqual(
            [r["link"] for r in out],
            ["https://b.example/1", "https://s.example/1"],
        )

    def test_longest_title_and_snippet_win(self):
        results = {
            "google": [{"link": "https://a.example/1", "title": "short", "snippet": ""}],
            "bing": [
                {"link": "https://a.example/1", "title": "a much longer title",
                 "snippet": "snip"},
            ],
        }
        out = aggregate_results(results, 10, ["google", "bing"])
        self.assertEqual(out[0]["title"], "a much longer title")
        self.assertEqual(out[0]["snippet"], "snip")

    def test_count_limits_output(self):
        results = {
            "google": [
                {"link": f"https://e.example/{i}", "title": "t", "snippet": ""}
                for i in range(5)
            ],
        }
        self.assertEqual(len(aggregate_results(results, 3, ["google"])), 3)


if __name__ == "__main__":
    unittest.main()
