import os
import io
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import urllib.error

from api import live


class LiveXSourceTests(unittest.TestCase):
    def test_load_x_accounts_from_markdown_extracts_handles(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as fh:
            fh.write(
                "# Test\n"
                "- [@Alpha_one](https://x.com/Alpha_one)\n"
                "- [@BetaTwo](https://x.com/BetaTwo)\n"
            )
            tmp_path = fh.name

        try:
            handles = live.load_x_accounts_from_markdown(tmp_path)
        finally:
            os.unlink(tmp_path)

        self.assertEqual(handles, ["alpha_one", "betatwo"])

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

    def test_is_low_signal_story_rejects_human_interest_without_tripwires(self):
        item = {
            "title": "Man accuses Israel of war crimes as he holds remains of girl killed in Iran",
            "excerpt": "A human story from the scene of the strike.",
        }
        self.assertTrue(live.is_low_signal_story(item))

    def test_is_major_impact_story_accepts_us_servicemembers_killed(self):
        item = {
            "title": "Three US servicemembers killed in drone attack on outpost",
            "excerpt": "Pentagon confirms fatalities and retaliatory options under review.",
        }
        self.assertTrue(live.is_major_impact_story(item))

    def test_is_major_impact_story_rejects_generic_tension_update(self):
        item = {
            "title": "Regional tensions continue after overnight developments",
            "excerpt": "Officials monitor situation as diplomacy remains uncertain.",
        }
        self.assertFalse(live.is_major_impact_story(item))

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

    def test_parse_rss_decodes_double_encoded_html_entities(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Iran&amp;#039;s escalation prompts response</title>
      <description>US Central Command said five others were &amp;#039;seriously wounded&amp;#039;.</description>
      <link>https://example.com/story</link>
      <pubDate>Sat, 28 Feb 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""
        items = live.parse_rss(xml, "Reuters", "breaking", max_items=5)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Iran's escalation prompts response")
        self.assertIn("'seriously wounded'", items[0]["excerpt"])
        self.assertNotIn("&#039;", items[0]["title"] + items[0]["excerpt"])

    def test_merge_and_dedupe_news_items_collapses_duplicate_headlines_keep_newest(self):
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
        self.assertEqual(merged[1]["id"], "x-1")
        self.assertEqual(merged[0]["id"], "x-2")

    def test_merge_and_dedupe_news_items_sorts_strictly_by_recency(self):
        rss_items = [
            {
                "id": "rss-older",
                "title": "Iran update older",
                "time": "2026-02-28T08:00:00Z",
                "url": "https://example.com/older",
            },
            {
                "id": "rss-newer",
                "title": "Iran update newer",
                "time": "2026-02-28T11:00:00Z",
                "url": "https://example.com/newer",
            },
        ]
        x_items = [
            {
                "id": "x-mid",
                "title": "IRGC movement update",
                "time": "2026-02-28T10:00:00Z",
                "url": "https://x.com/a/status/77",
                "source": "@auroraintel",
                "type": "osint",
                "tag": "osint",
            },
        ]

        merged = live.merge_and_dedupe_news_items(rss_items, x_items, limit=25)
        self.assertEqual([item["id"] for item in merged], ["rss-newer", "x-mid", "rss-older"])

    def test_fetch_news_feeds_includes_x_items_sorted_by_recency(self):
        rss_items = [
            {
                "id": "rss-1",
                "title": "Reuters: IRGC missile strike triggers new US sanctions",
                "time": "2026-02-28T09:00:00Z",
                "url": "https://example.com/reuters",
            }
        ]
        x_items = [
            {
                "id": "x-1",
                "title": "Three US servicemembers killed in attack near Jordan border",
                "time": "2026-02-28T10:00:00Z",
                "url": "https://x.com/auroraintel/status/1",
            }
        ]

        with patch.object(live, "fetch_rss_news_feeds", return_value=rss_items):
            with patch.object(
                live,
                "fetch_x_source_items",
                return_value=(x_items, {"xStatus": "ok"}),
            ):
                merged = live.fetch_news_feeds()

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["id"], "x-1")
        self.assertEqual(merged[1]["id"], "rss-1")

    def test_fetch_news_feeds_filters_out_non_major_updates(self):
        rss_items = [
            {
                "id": "rss-low",
                "title": "Regional tensions continue as leaders issue statements",
                "time": "2026-02-28T09:30:00Z",
                "url": "https://example.com/low",
            },
            {
                "id": "rss-high",
                "title": "US sanctions IRGC commanders after missile launch on base",
                "time": "2026-02-28T09:20:00Z",
                "url": "https://example.com/high",
            },
        ]
        with patch.object(live, "fetch_rss_news_feeds", return_value=rss_items):
            with patch.object(live, "fetch_x_source_items", return_value=([], {"xStatus": "ok"})):
                merged = live.fetch_news_feeds()

        self.assertEqual([item["id"] for item in merged], ["rss-high"])

    def test_fetch_news_feeds_return_debug_includes_x_counters(self):
        rss_items = [
            {
                "id": "rss-1",
                "title": "IAEA says Iran accelerates enrichment at Fordow",
                "time": "2026-02-28T09:00:00Z",
                "url": "https://a",
            }
        ]
        x_items = [
            {
                "id": "x-1",
                "title": "US servicemembers killed in drone attack; retaliation expected",
                "time": "2026-02-28T10:00:00Z",
                "url": "https://b",
            }
        ]
        x_debug = {
            "xEnabled": True,
            "xFetched": 4,
            "xPassedScore": 2,
            "xSelectedBeforeLlm": 1,
            "xAfterLlm": 1,
            "xDroppedByLlm": 0,
            "xStatus": "ok",
        }
        with patch.object(live, "fetch_rss_news_feeds", return_value=rss_items):
            with patch.object(live, "fetch_x_source_items", return_value=(x_items, x_debug)):
                merged, debug = live.fetch_news_feeds(return_debug=True)

        self.assertEqual(len(merged), 2)
        self.assertEqual(debug["rssCount"], 1)
        self.assertEqual(debug["mergedCount"], 2)
        self.assertEqual(debug["x"]["xFetched"], 4)

    def test_fetch_x_source_items_return_debug_no_token(self):
        with patch.dict(os.environ, {}, clear=True):
            items, debug = live.fetch_x_source_items(return_debug=True)

        self.assertEqual(items, [])
        self.assertEqual(debug["xStatus"], "no_x_token")
        self.assertFalse(debug["xEnabled"])

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
        fake_response = MagicMock()
        fake_response.read.return_value = live.json.dumps(llm_response).encode("utf-8")
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_response
        fake_context.__exit__.return_value = False
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            with patch("urllib.request.urlopen", return_value=fake_context):
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
        fake_response = MagicMock()
        fake_response.read.return_value = live.json.dumps(llm_response).encode("utf-8")
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_response
        fake_context.__exit__.return_value = False
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            with patch("urllib.request.urlopen", return_value=fake_context):
                filtered = live.filter_x_items_with_llm(items)

        self.assertEqual(filtered, [])

    def test_filter_x_items_with_llm_http_error_exposes_status(self):
        items = [{"id": "x-1", "title": "Relevant Iran update", "source": "@auroraintel"}]
        http_err = urllib.error.HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"error":"invalid api key"}'),
        )
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=http_err):
                _, meta = live.filter_x_items_with_llm(items, return_meta=True)

        self.assertEqual(meta["result"], "http_401_passthrough")
        self.assertEqual(meta["httpStatus"], 401)


if __name__ == "__main__":
    unittest.main()
