# feat: Add X/Twitter API as a news source

## Overview

Add X (Twitter) API v2 as a live source in the Iran Crisis Monitor. Tweets from curated OSINT and analysis accounts are fetched, filtered for Iran-relevance using an LLM, and merged into the unified news feed.

## Problem Statement

High-value sources like The Kobeissi Letter publish exclusively on X with no RSS feed. The OSINT accounts listed in the frontend (@AuroraIntel, @sentdefender, etc.) are static links -- their tweets aren't pulled into the live feed. Keyword matching is too crude for these accounts: a tweet about "strikes on Parchin" may not contain the word "iran" but is highly relevant.

## Proposed Solution

1. Fetch recent tweets from curated accounts via X API v2
2. Use an LLM (Claude Haiku via Anthropic API) to score each tweet's relevance to the Iran crisis
3. Merge relevant tweets into the existing `news[]` array in `api/live.py`

## Technical Approach

### Architecture

```
api/live.py (existing)
  fetch_news_feeds()        -- existing RSS pipeline
  fetch_tweets()            -- NEW: X API fetch + LLM filter
  handler.do_GET()          -- merge both into single response
```

No new files or endpoints. Tweets merge into the existing `news[]` array with `type: "tweet"`.

### X API Details

- **Endpoint:** `GET https://api.x.com/2/tweets/search/recent`
- **Auth:** Bearer Token (`X_BEARER_TOKEN` env var)
- **Tier required:** Basic ($200/mo) -- Free tier has no search access
- **Limits:** 450 req/15min, 15,000 tweet reads/month, 512-char queries, 7-day window
- **Library:** Raw `urllib` (matches existing codebase, zero dependencies)

### Monitored Accounts

| Account | Category | Tag |
|---------|----------|-----|
| `KobeissiLetter` | Market analysis | `analysis` |
| `AuroraIntel` | OSINT | `osint` |
| `sentdefender` | OSINT | `osint` |
| `IntelCrab` | OSINT | `osint` |
| `OSINTdefender` | OSINT | `osint` |
| `Global_Mil_Info` | Military intel | `osint` |

### LLM Relevance Filtering

Instead of keyword matching (which misses contextually relevant tweets), use Claude Haiku to batch-assess relevance. Send all fetched tweets in a single prompt:

```python
RELEVANCE_PROMPT = """You are filtering tweets for an Iran crisis monitoring dashboard.
For each tweet, respond with ONLY the tweet number if it is relevant to:
- Iran military/nuclear situation
- US-Iran tensions or strikes
- IRGC, Hezbollah, Houthi activity
- Strait of Hormuz, Persian Gulf tensions
- Iran sanctions, JCPOA, enrichment
- Regional conflict involving Iran or its proxies
- Oil/energy markets directly affected by Iran tensions

Respond with just the relevant tweet numbers, comma-separated. If none are relevant, respond "NONE".

Tweets:
{tweets}"""
```

This costs ~$0.001-0.005 per batch (Haiku pricing on ~20 tweets). At 144 calls/day that's ~$0.15-0.70/day, well under $25/month.

### Caching Strategy

Simple module-level cache, no `since_id` complexity (per reviewer consensus):

- **Cache TTL: 10 minutes** -- 144 calls/day x 20 tweets = 2,880 tweets/day
- **Budget:** ~86K tweets/month vs 15K cap -- **need to verify actual X API counting**. If each tweet in a response counts individually toward the cap, bump TTL to 30 min (48 calls/day = 960 tweets/day = ~29K/month, still over). If each API *request* counts, we're fine.
- **Fallback:** Serve stale cache on any error
- **No `since_id`:** Each fetch replaces the cache entirely. Simpler, no merge bugs.

### Error Handling

Log errors with `print()` (visible in Vercel function logs). Classify errors:
- **401/403:** Bad token -- log loudly, serve cache
- **429:** Rate limited -- serve cache
- **5xx/timeout:** Transient -- serve cache

## Implementation Plan

### 1. Add imports and config (`api/live.py`, top of file)

```python
import urllib.parse
import time

X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
X_ACCOUNTS = [
    ("KobeissiLetter", "analysis"),
    ("AuroraIntel", "osint"),
    ("sentdefender", "osint"),
    ("IntelCrab", "osint"),
    ("OSINTdefender", "osint"),
    ("Global_Mil_Info", "osint"),
]
_tweet_cache = {"items": [], "expires": 0}
TWEET_CACHE_TTL = 600  # 10 minutes
```

### 2. Add `filter_tweets_llm()` function

```python
def filter_tweets_llm(tweets):
    """Use Claude Haiku to filter tweets for Iran relevance."""
    if not ANTHROPIC_API_KEY or not tweets:
        return tweets  # pass through if no API key

    numbered = "\n".join(f"{i+1}. @{t['source']}: {t['excerpt']}" for i, t in enumerate(tweets))
    prompt = RELEVANCE_PROMPT.format(tweets=numbered)

    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": prompt}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            text = result["content"][0]["text"].strip()
            if text == "NONE":
                return []
            indices = [int(x.strip()) - 1 for x in text.split(",") if x.strip().isdigit()]
            return [tweets[i] for i in indices if 0 <= i < len(tweets)]
    except Exception as e:
        print(f"[LLM filter] Error: {e}")
        return tweets  # pass through on error -- better to show than hide
```

### 3. Add `fetch_tweets()` function

```python
def fetch_tweets():
    """Fetch recent tweets from monitored X accounts, filter with LLM."""
    if not X_BEARER_TOKEN:
        return []

    now = time.time()
    if _tweet_cache["items"] and now < _tweet_cache["expires"]:
        return _tweet_cache["items"]

    accounts_q = " OR ".join(f"from:{a[0]}" for a in X_ACCOUNTS)
    query = f"({accounts_q}) -is:retweet lang:en"

    params = {
        "query": query,
        "max_results": "20",
        "tweet.fields": "created_at,author_id",
        "user.fields": "username",
        "expansions": "author_id",
        "sort_order": "recency",
    }

    url = f"https://api.x.com/2/tweets/search/recent?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {X_BEARER_TOKEN}",
        "User-Agent": "IranCrisisMonitor/1.0",
    })

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[X API] HTTP {e.code}")
        return _tweet_cache.get("items", [])
    except Exception as e:
        print(f"[X API] Error: {e}")
        return _tweet_cache.get("items", [])

    if "data" not in data:
        return _tweet_cache.get("items", [])

    # Build user lookup
    users = {}
    for u in data.get("includes", {}).get("users", []):
        users[u["id"]] = u

    tag_map = {a[0].lower(): a[1] for a in X_ACCOUNTS}
    items = []
    for tw in data["data"]:
        try:
            author = users.get(tw.get("author_id"), {})
            username = author.get("username", "unknown")
            text = tw.get("text", "")
            tag = tag_map.get(username.lower(), "osint")

            items.append({
                "id": f"x_{tw['id']}",
                "type": "tweet",
                "tag": tag,
                "source": f"@{username}",
                "title": text[:120],
                "excerpt": text[:180],
                "url": f"https://x.com/{username}/status/{tw['id']}",
                "time": tw.get("created_at", ""),
                "timestamp": tw.get("created_at", ""),
            })
        except (KeyError, TypeError):
            continue

    # LLM relevance filter
    items = filter_tweets_llm(items)

    _tweet_cache["items"] = items
    _tweet_cache["expires"] = now + TWEET_CACHE_TTL
    return items
```

### 4. Merge into `do_GET()` response (~line 346)

```python
tweets = fetch_tweets()
all_news = news + tweets
all_news.sort(key=lambda x: x.get("time", ""), reverse=True)
news = all_news[:25]
```

No keyword filtering needed -- the LLM has already assessed relevance.

### 5. Vercel environment setup

```bash
vercel env add X_BEARER_TOKEN
vercel env add ANTHROPIC_API_KEY
```

## Acceptance Criteria

- [ ] `api/live.py` fetches tweets from X API v2 when `X_BEARER_TOKEN` is set
- [ ] Tweets are filtered for Iran relevance using Claude Haiku
- [ ] Tweets merge into the existing `news[]` array, sorted by time
- [ ] Module-level cache prevents excessive API calls (10-min TTL)
- [ ] Graceful degradation: missing tokens or API failures don't break RSS feed
- [ ] Errors are logged with `print()` and classified by type
- [ ] No new pip dependencies (stdlib `urllib` only)

## Dependencies & Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| X Basic tier $200/mo | Ongoing cost | 10-min cache keeps calls manageable |
| Anthropic API cost | ~$15-25/mo | Haiku is very cheap, batch prompts |
| LLM adds latency | Slower response | 5s timeout, pass-through on failure |
| Rate limiting (429) | Lost tweets | Serve stale cache, RSS unaffected |
| Cold starts reset cache | Extra API calls | Acceptable -- fresh data on restart |

## What This Doesn't Include

- No persistent/external cache (module-level is sufficient for v1)
- No tweet threading, media display, or conversation expansion
- No frontend changes (tweets render with existing item styling)

## References

- Existing feed logic: `api/live.py:149-204`
- Iran keywords: `api/live.py:27-38`
- Response structure: `api/live.py:357-378`
- X API Search Recent: https://docs.x.com/x-api/posts/search-recent-posts
- Anthropic Messages API: https://docs.anthropic.com/en/api/messages
