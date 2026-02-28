import importlib.util
import unittest
from pathlib import Path


def load_live_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "api" / "live.py"
    spec = importlib.util.spec_from_file_location("live_api", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LiveMarketFilterTests(unittest.TestCase):
    def setUp(self):
        self.live = load_live_module()

    def test_rejects_placeholder_ellipsis_titles(self):
        self.assertFalse(self.live.is_relevant_market_title("US next strikes Iran on...?"))
        self.assertFalse(self.live.is_relevant_market_title("Iran Strike on Israel by…?"))

    def test_rejects_malformed_template_titles(self):
        self.assertFalse(
            self.live.is_relevant_market_title(
                "Odds of Khamenei out by March 31 over__ in February?"
            )
        )

    def test_keeps_relevant_structured_iran_markets(self):
        self.assertTrue(
            self.live.is_relevant_market_title(
                "Will Iran close the Strait of Hormuz by 2027?"
            )
        )
        self.assertTrue(
            self.live.is_relevant_market_title(
                "Will the Iranian regime fall by March 31?"
            )
        )

    def test_rejects_non_iran_markets(self):
        self.assertFalse(self.live.is_relevant_market_title("Will ETH be above $5,000?"))

    def test_extract_ranked_ids_dedupes_and_bounds(self):
        ids = self.live.extract_ranked_ids("3, 1, 3, 99, 2", max_count=3, max_index=5)
        self.assertEqual(ids, [3, 1, 2])

    def test_extract_anthropic_message_text_from_content_blocks(self):
        data = {
            "content": [
                {"type": "text", "text": "3,1"},
                {"type": "tool_use", "id": "x"},
                {"type": "text", "text": "2"},
            ]
        }
        self.assertEqual(self.live.extract_anthropic_message_text(data), "3,1 2")

    def test_select_markets_for_dashboard_respects_llm_order_and_fills(self):
        markets = [
            {"question": "A", "volume": 100},
            {"question": "B", "volume": 90},
            {"question": "C", "volume": 80},
            {"question": "D", "volume": 70},
        ]
        original = self.live.llm_rank_market_ids
        try:
            self.live.llm_rank_market_ids = lambda _mkts, max_keep=6: [3, 1]
            picked = self.live.select_markets_for_dashboard(markets, max_keep=3)
            self.assertEqual([m["question"] for m in picked], ["C", "A", "B"])
        finally:
            self.live.llm_rank_market_ids = original

    def test_select_markets_for_dashboard_falls_back_without_llm_rank(self):
        markets = [
            {"question": "A", "volume": 100},
            {"question": "B", "volume": 90},
            {"question": "C", "volume": 80},
        ]
        original = self.live.llm_rank_market_ids
        try:
            self.live.llm_rank_market_ids = lambda _mkts, max_keep=6: []
            picked = self.live.select_markets_for_dashboard(markets, max_keep=2)
            self.assertEqual([m["question"] for m in picked], ["A", "B"])
        finally:
            self.live.llm_rank_market_ids = original


if __name__ == "__main__":
    unittest.main()
