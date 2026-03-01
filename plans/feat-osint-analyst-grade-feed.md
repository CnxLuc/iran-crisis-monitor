# feat: Make feed analyst-grade with LLM filtering on RSS items

## Problem

The feed currently shows items like **"Man accuses Israel of war crimes as he holds remains of girl killed in Iran"** (Al Jazeera) — an emotional civilian casualty story that provides zero actionable intelligence. A CIA analyst or serious OSINT monitor needs to understand *what is happening operationally and strategically*, not consume human interest coverage.

**Root cause:** RSS items pass through only a keyword check (`any(kw in text for kw in IRAN_KEYWORDS)`) at `api/live.py:314`. Any article mentioning "Iran" gets through — opinion pieces, human interest stories, emotional coverage, duplicate wire rewrites. X posts already go through multi-stage scoring + Claude Haiku LLM filtering, but RSS items get no semantic filtering at all.

## Proposed Solution

Add LLM relevance filtering to RSS items, using the same pattern already proven for X posts, but with an analyst-grade prompt that prioritizes actionable intelligence.

## Changes

### 1. Add `filter_rss_items_with_llm()` in `api/live.py`

Create a new function following the exact pattern of `filter_x_items_with_llm()` (line 530), but with an analyst-oriented prompt.

**New prompt** (the key change):

```
You are an intelligence analyst filtering news for an Iran crisis monitoring dashboard used by national security professionals.

INCLUDE items about:
- Military movements, strikes, deployments, force posture changes
- Nuclear program developments (enrichment levels, IAEA inspections, facility activity)
- IRGC operations, Quds Force activity, proxy group coordination
- Strait of Hormuz / Persian Gulf naval activity and shipping disruptions
- Diplomatic signals: backchannel talks, ultimatums, ceasefire proposals, sanctions changes
- Regime stability: leadership statements, internal power shifts, protests with strategic implications
- Escalation indicators: rhetoric shifts, military readiness changes, evacuation orders
- Economic warfare: oil sanctions enforcement, SWIFT access, energy market disruptions
- Regional spillover: Hezbollah/Houthi/militia activation linked to Iran
- Cyber operations and information warfare attributed to state actors

EXCLUDE items that are:
- Civilian casualty stories without operational/strategic context
- Human interest or emotional coverage (vigils, funerals, personal stories)
- Opinion/editorial pieces without new factual information
- Duplicate wire rewrites of the same underlying event (keep the most informative version)
- Domestic politics of other countries unless directly about Iran policy decisions
- Cultural, sports, or entertainment news that happens to mention Iran

Reply with ONLY article numbers to KEEP, comma-separated, or NONE.
```

**Implementation details:**
- Model: Same as X filtering — `claude-3-5-haiku-latest` (fast, cheap)
- Temperature: 0
- Max tokens: 200 (RSS batches may be larger than X batches)
- Timeout: 8 seconds (slightly more than X's 6s since batch is bigger)
- Error handling: Passthrough (show unfiltered if LLM fails — same pattern as X)
- Input format: numbered list of `"SOURCE: title — excerpt"` for each item

### 2. Wire into `fetch_rss_news_feeds()` at line 341

After fetching and deduplicating RSS items (line 372), pass them through the new LLM filter before returning:

```python
def fetch_rss_news_feeds():
    # ... existing fetch + dedupe logic ...
    unique = merge_and_dedupe_news_items(all_items, [], limit=25)
    filtered, rss_llm_meta = filter_rss_items_with_llm(unique, return_meta=True)
    return filtered, rss_llm_meta  # return meta for debug
```

### 3. Expose RSS LLM debug metadata in API response

Add `rssLlm` to the existing `meta` block (same pattern as `xDebug.xLlm`):

```json
{
  "meta": {
    "rssLlm": {
      "inputCount": 18,
      "outputCount": 11,
      "llmEnabled": true,
      "llmApplied": true,
      "result": "filtered_indices",
      "model": "claude-3-5-haiku-latest"
    }
  }
}
```

### 4. Add more OSINT-grade X accounts

Expand the X allowlist with accounts known in the OSINT community for Iran/Middle East coverage:

```python
X_ALLOWED_ACCOUNTS = [
    "auroraintel",
    "sentdefender",
    "intelcrab",
    "faytuks",
    "loaboringwar",
    # New additions
    "osaborningwar",     # OSINT aggregator, Middle East focus
    "liveuamap",         # Conflict mapping, real-time strike tracking
    "intikiintel",       # Iran/MENA OSINT
    "thomas_falkner",    # Iran military analysis
    "faboringwar",       # Middle East military tracking
]
```

Add corresponding weights (new accounts start at 1.0 until proven).

### 5. Update X LLM prompt to match analyst tone

Align the X filtering prompt (line 503-508) with the same analyst-grade criteria used for RSS, so both filters use consistent intelligence standards.

### 6. Add tests

New test file `tests/test_live_rss_llm_filter.py`:
- Test that emotional/human interest articles are excluded by prompt design
- Test LLM response parsing (same pattern as existing X tests)
- Test passthrough on API failure
- Test debug metadata structure

## Files to modify

| File | Change |
|------|--------|
| `api/live.py` | Add `filter_rss_items_with_llm()`, `build_rss_llm_prompt()`, wire into `fetch_rss_news_feeds()`, add X accounts, update X prompt |
| `tests/test_live_rss_llm_filter.py` | New test file for RSS LLM filtering |
| `tests/test_live_x_source.py` | Update tests for new X accounts and updated prompt |

## What this does NOT change

- Frontend rendering — no UI changes needed
- Market filtering — already has LLM ranking
- X scoring pipeline — keeps existing engagement + account weight scoring
- Fallback data — untouched
- Caching strategy — unchanged

## Cost impact

- One additional Claude Haiku call per `/api/live` request (~18 RSS items × ~50 tokens each = ~900 input tokens + ~100 output tokens)
- At Haiku pricing this is negligible (~$0.0001/request)
- Total LLM calls per refresh: 3 (RSS filter + X filter + market ranking) — up from 2

## Acceptance Criteria

- [ ] RSS items go through LLM relevance filtering before appearing in feed
- [ ] Human interest / emotional stories like the Al Jazeera example are filtered out
- [ ] Analyst-grade prompt prioritizes operational, strategic, and diplomatic intelligence
- [ ] Debug metadata for RSS LLM filtering visible in API response `meta` block
- [ ] Graceful degradation: if LLM fails, unfiltered RSS items still show (passthrough)
- [ ] Existing X filtering continues to work unchanged
- [ ] All existing tests pass
- [ ] New tests cover RSS LLM filter happy path + error cases
