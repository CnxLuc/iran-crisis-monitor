import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


def load_live_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "api" / "live.py"
    spec = importlib.util.spec_from_file_location("live_api", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LiveMarketSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.live = load_live_module()

    def test_fetch_yahoo_quotes_returns_symbol_map(self):
        payload = {
            "quoteResponse": {
                "result": [
                    {"symbol": "CL=F", "regularMarketPrice": 67.4},
                    {"symbol": "GC=F", "regularMarketPrice": 5296.0},
                ]
            }
        }
        with patch.object(self.live, "fetch_url", return_value=json.dumps(payload)):
            quotes = self.live.fetch_yahoo_quotes(["CL=F", "GC=F"])

        self.assertEqual(set(quotes.keys()), {"CL=F", "GC=F"})
        self.assertEqual(quotes["CL=F"]["regularMarketPrice"], 67.4)

    def test_fetch_yahoo_quotes_uses_chart_data_when_quote_endpoint_unavailable(self):
        chart_payload = {
            "chart": {
                "result": [
                    {
                        "meta": {"symbol": "CL=F", "regularMarketPrice": 67.4},
                        "indicators": {"quote": [{"close": [65.0, 67.4]}]},
                    }
                ],
                "error": None,
            }
        }

        def fake_fetch(url, timeout=6, headers=None, data=None):
            if "finance/quote?symbols=" in url:
                return None
            if "finance/chart/CL%3DF?interval=1d&range=2d" in url:
                return json.dumps(chart_payload)
            return None

        with patch.object(self.live, "fetch_url", side_effect=fake_fetch):
            quotes = self.live.fetch_yahoo_quotes(["CL=F"])

        self.assertEqual(set(quotes.keys()), {"CL=F"})
        self.assertAlmostEqual(quotes["CL=F"]["regularMarketPrice"], 67.4)
        self.assertAlmostEqual(quotes["CL=F"]["regularMarketChange"], 2.4, places=3)
        self.assertAlmostEqual(quotes["CL=F"]["regularMarketChangePercent"], 3.6923, places=3)

    def test_fetch_yahoo_quotes_uses_chart_previous_close_when_only_one_close_value(self):
        chart_payload = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": "GC=F",
                            "regularMarketPrice": 5247.9,
                            "chartPreviousClose": 5230.5,
                        },
                        "indicators": {"quote": [{"close": [5247.9]}]},
                    }
                ],
                "error": None,
            }
        }

        def fake_fetch(url, timeout=6, headers=None, data=None):
            if "finance/quote?symbols=" in url:
                return None
            if "finance/chart/GC%3DF?interval=1d&range=2d" in url:
                return json.dumps(chart_payload)
            return None

        with patch.object(self.live, "fetch_url", side_effect=fake_fetch):
            quotes = self.live.fetch_yahoo_quotes(["GC=F"])

        self.assertEqual(set(quotes.keys()), {"GC=F"})
        self.assertAlmostEqual(quotes["GC=F"]["regularMarketChange"], 17.4, places=3)
        self.assertAlmostEqual(quotes["GC=F"]["regularMarketChangePercent"], 0.3327, places=3)

    def test_build_market_snapshot_formats_currency_percent_and_points(self):
        quotes = {
            "CL=F": {
                "symbol": "CL=F",
                "regularMarketPrice": 67.4,
                "regularMarketChangePercent": 8.2,
            },
            "BZ=F": {
                "symbol": "BZ=F",
                "regularMarketPrice": 73.15,
                "regularMarketChangePercent": 7.9,
            },
            "GC=F": {
                "symbol": "GC=F",
                "regularMarketPrice": 5296.0,
                "regularMarketChangePercent": 2.1,
            },
            "BTC-USD": {
                "symbol": "BTC-USD",
                "regularMarketPrice": 63000.0,
                "regularMarketChangePercent": -6.0,
            },
            "LMT": {
                "symbol": "LMT",
                "regularMarketPrice": 470.0,
                "regularMarketChangePercent": 4.8,
            },
            "^VIX": {
                "symbol": "^VIX",
                "regularMarketPrice": 28.4,
                "regularMarketChange": 9.3,
            },
            "^TNX": {
                "symbol": "^TNX",
                "regularMarketPrice": 43.1,
                "regularMarketChange": -1.2,
            },
            "^GSPC": {
                "symbol": "^GSPC",
                "regularMarketPrice": 5100.0,
                "regularMarketChangePercent": -1.8,
            },
        }

        snapshot = self.live.build_market_snapshot(quotes, as_of="2026-03-01T12:00:00Z")

        self.assertEqual(snapshot["asOf"], "2026-03-01T12:00:00Z")
        self.assertEqual(snapshot["indicators"]["wti"]["valueDisplay"], "$67.40")
        self.assertEqual(snapshot["indicators"]["btc"]["changeDisplay"], "▼ -6.0%")
        self.assertEqual(snapshot["indicators"]["vix"]["changeDisplay"], "▲ +9.3 pts")
        self.assertEqual(snapshot["indicators"]["us10y"]["valueDisplay"], "4.31%")
        self.assertEqual(snapshot["indicators"]["us10y"]["changeDisplay"], "▼ -12 bps")
        self.assertEqual(snapshot["indicators"]["sp500"]["direction"], "down")

    def test_build_market_snapshot_handles_missing_quote_fields(self):
        snapshot = self.live.build_market_snapshot(
            {
                "CL=F": {"symbol": "CL=F"},
                "^GSPC": {"symbol": "^GSPC", "regularMarketPrice": 5100.0},
            },
            as_of="2026-03-01T12:00:00Z",
        )

        self.assertNotIn("wti", snapshot["indicators"])
        self.assertIn("sp500", snapshot["indicators"])
        self.assertEqual(snapshot["indicators"]["sp500"]["changeDisplay"], "")

    def test_build_market_snapshot_handles_unscaled_us10y_chart_values(self):
        snapshot = self.live.build_market_snapshot(
            {
                "^TNX": {
                    "symbol": "^TNX",
                    "regularMarketPrice": 3.962,
                    "regularMarketChange": -0.055,
                }
            },
            as_of="2026-03-01T12:00:00Z",
        )

        self.assertEqual(snapshot["indicators"]["us10y"]["valueDisplay"], "3.96%")
        self.assertEqual(snapshot["indicators"]["us10y"]["changeDisplay"], "▼ -6 bps")


if __name__ == "__main__":
    unittest.main()
