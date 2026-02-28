import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from api import live


class LiveXSourceTests(unittest.TestCase):
    def test_build_x_recent_search_query_uses_whitelist_and_keywords(self):
        query = live.build_x_recent_search_query(
            accounts=["AuroraIntel", "sentdefender"],
            keywords=["iran", "strait of hormuz"],
        )

        self.assertIn("from:auroraintel", query)
        self.assertIn("from:sentdefender", query)
        self.assertIn("iran", query)
        self.assertIn('"strait of hormuz"', query)
        self.assertIn("-is:retweet", query)
        self.assertIn("-is:reply", query)

    def test_fetch_x_source_items_returns_empty_without_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(live, "fetch_x_recent_search") as fetch_mock:
                items = live.fetch_x_source_items()

        self.assertEqual(items, [])
        fetch_mock.assert_not_called()

    def test_is_high_signal_x_post_rejects_low_engagement_noise(self):
        now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
        post = {
            "id": "101",
            "author_id": "u1",
            "text": "Iran update from field reporting in Tehran with new details.",
            "created_at": "2026-02-28T11:30:00Z",
            "public_metrics": {
                "like_count": 1,
                "retweet_count": 0,
                "reply_count": 0,
                "quote_count": 0,
            },
        }
        users = {"u1": {"id": "u1", "username": "auroraintel"}}

        accepted, score = live.is_high_signal_x_post(
            post,
            account_weights=live.X_ACCOUNT_WEIGHTS,
            keywords=live.X_QUERY_KEYWORDS,
            user_by_id=users,
            now=now,
        )

        self.assertFalse(accepted)
        self.assertEqual(score, 0.0)

    def test_normalize_x_post_maps_fields_to_news_schema(self):
        post = {
            "id": "555",
            "author_id": "u1",
            "text": "IRGC movement update near Strait of Hormuz. https://t.co/abc123",
            "created_at": "2026-02-28T10:00:00.000Z",
        }
        users = {"u1": {"id": "u1", "username": "sentdefender"}}

        item = live.normalize_x_post_to_news_item(post, users)

        self.assertEqual(item["id"], "x-555")
        self.assertEqual(item["type"], "osint")
        self.assertEqual(item["tag"], "osint")
        self.assertEqual(item["source"], "@sentdefender")
        self.assertEqual(item["url"], "https://x.com/sentdefender/status/555")
        self.assertTrue(item["time"].endswith("Z"))
        self.assertNotIn("https://", item["title"])

    def test_merge_and_dedupe_news_items_collapses_duplicate_headlines(self):
        rss_items = [
            {
                "id": "rss-1",
                "title": "Iran confirms strike in Tehran",
                "time": "2026-02-28T10:00:00Z",
                "url": "https://example.com/a",
            }
        ]
        x_items = [
            {
                "id": "x-1",
                "title": "Iran confirms strike in Tehran",
                "time": "2026-02-28T10:05:00Z",
                "url": "https://x.com/a/status/1",
            },
            {
                "id": "x-2",
                "title": "IAEA reports disruption at Isfahan facility",
                "time": "2026-02-28T10:06:00Z",
                "url": "https://x.com/a/status/2",
            },
        ]

        merged = live.merge_and_dedupe_news_items(rss_items, x_items, limit=25)

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["id"], "x-2")

    def test_fetch_news_feeds_includes_x_items_sorted_by_recency(self):
        rss_items = [
            {
                "id": "rss-1",
                "title": "Reuters: Iran talks continue",
                "time": "2026-02-28T09:00:00Z",
                "url": "https://example.com/reuters",
            }
        ]
        x_items = [
            {
                "id": "x-1",
                "title": "IRGC launches near Hormuz",
                "time": "2026-02-28T10:00:00Z",
                "url": "https://x.com/auroraintel/status/1",
            }
        ]

        with patch.object(live, "fetch_rss_news_feeds", return_value=rss_items):
            with patch.object(live, "fetch_x_source_items", return_value=x_items):
                merged = live.fetch_news_feeds()

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["id"], "x-1")
        self.assertEqual(merged[1]["id"], "rss-1")

    def test_parse_llm_relevant_indices_parses_numbers_and_dedupes(self):
        parsed = live.parse_llm_relevant_indices("2, 1, 2, 9, nope", total_count=3)
        self.assertEqual(parsed, [1, 0])

    def test_filter_x_items_with_llm_passthrough_without_key(self):
        items = [{"id": "x-1", "title": "One", "source": "@auroraintel"}]
        with patch.dict(os.environ, {}, clear=True):
            filtered = live.filter_x_items_with_llm(items)
        self.assertEqual(filtered, items)

    def test_filter_x_items_with_llm_selects_indices_from_llm_response(self):
        items = [
            {"id": "x-1", "title": "Not relevant", "source": "@auroraintel"},
            {"id": "x-2", "title": "Relevant Iran update", "source": "@sentdefender"},
            {"id": "x-3", "title": "Also relevant", "source": "@intelcrab"},
        ]
        llm_response = {
            "content": [
                {"type": "text", "text": "2, 3"},
            ]
        }
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            with patch.object(live, "fetch_url", return_value=live.json.dumps(llm_response)):
                filtered = live.filter_x_items_with_llm(items)

        self.assertEqual([item["id"] for item in filtered], ["x-2", "x-3"])

    def test_filter_x_items_with_llm_none_response_returns_empty(self):
        items = [
            {"id": "x-1", "title": "Potentially relevant", "source": "@auroraintel"},
            {"id": "x-2", "title": "Potentially relevant", "source": "@sentdefender"},
        ]
        llm_response = {
            "content": [
                {"type": "text", "text": "NONE"},
            ]
        }
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            with patch.object(live, "fetch_url", return_value=live.json.dumps(llm_response)):
                filtered = live.filter_x_items_with_llm(items)

        self.assertEqual(filtered, [])


if __name__ == "__main__":
    unittest.main()
