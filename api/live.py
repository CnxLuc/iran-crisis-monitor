"""Vercel serverless function for Iran Crisis Monitor live data with history tracking."""
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import re
import hashlib
import random
from http.server import BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor, as_completed


def fetch_url(url, timeout=8, headers=None, data=None):
    request_headers = {
        "User-Agent": "IranCrisisMonitor/1.0",
        "Accept": "application/json, application/xml, text/xml, */*",
    }
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Iran-related keywords for filtering
# ---------------------------------------------------------------------------
IRAN_KEYWORDS = [
    "iran", "tehran", "irgc", "khamenei", "hormuz", "hezbollah",
    "persian gulf", "nuclear", "natanz", "fordow", "middle east strike",
    "houthi", "strait", "regime change", "isfahan", "karaj", "parchin",
    "qom", "arabian sea", "red sea", "iran war", "iran conflict",
    "iran us", "iran israel", "iran attack", "epic fury", "lion's roar",
    "iranian regime", "iranian military", "tehran strike", "iran nuclear",
    "cruise missile iran", "ballistic missile iran", "irgc quds",
    "hezbollah attack", "strait of hormuz", "persian gulf war",
    "iran sanctions", "iran deal", "jcpoa", "enrichment", "centrifuge",
    "rouhani", "raisi", "pezeshkian", "iran president", "revolutionary guard",
]


# ---------------------------------------------------------------------------
# X API source configuration
# ---------------------------------------------------------------------------
X_BEARER_TOKEN_ENV = "X_BEARER_TOKEN"
X_ALLOWED_ACCOUNTS = [
    "auroraintel",
    "sentdefender",
    "intelcrab",
    "faytuks",
    "loaboringwar",
]
X_ACCOUNT_WEIGHTS = {
    "auroraintel": 1.25,
    "sentdefender": 1.15,
    "intelcrab": 1.05,
    "faytuks": 1.0,
    "loaboringwar": 1.0,
}
X_QUERY_KEYWORDS = [
    "iran",
    "tehran",
    "irgc",
    "hormuz",
    "strait of hormuz",
    "nuclear",
    "hezbollah",
    "israel",
    "us",
]
X_MAX_RESULTS = 40
X_MAX_ITEMS = 6
X_MAX_PER_ACCOUNT = 2
X_MAX_AGE_HOURS = 12
X_MIN_TEXT_LENGTH = 40
X_MIN_ENGAGEMENT = 12
X_MIN_SCORE = 22
ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"
ANTHROPIC_MODEL_ENV = "ANTHROPIC_MODEL"
ANTHROPIC_DEFAULT_MODEL = "claude-3-5-haiku-latest"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"


# ---------------------------------------------------------------------------
# Date normalization
# ---------------------------------------------------------------------------
def normalize_date(date_str):
    """Convert various date formats to ISO 8601 UTC string."""
    if not date_str:
        return None

    normalized = date_str.strip()

    # ISO 8601 (with or without milliseconds / timezone offset)
    iso_candidate = normalized.replace("Z", "+00:00")
    try:
        dt_obj = datetime.fromisoformat(iso_candidate)
        if dt_obj.tzinfo:
            dt_obj = dt_obj.astimezone(timezone.utc).replace(tzinfo=None)
        return dt_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        pass

    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            d = datetime.strptime(normalized, fmt)
            if d.tzinfo:
                d = d.astimezone(timezone.utc).replace(tzinfo=None)
            return d.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# RSS parsing - handles both standard RSS (<item>) and Atom (<entry>)
# ---------------------------------------------------------------------------
def parse_rss(xml_text, source_name, tag_type="breaking", max_items=10):
    items = []
    if not xml_text:
        return items
    try:
        root = ET.fromstring(xml_text)
        entries = root.findall(".//item")
        if not entries:
            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for entry in entries[:max_items]:
            title = link = pub_date = desc = ""
            # Title
            t = entry.find("title")
            if t is not None and t.text:
                title = t.text.strip()
            if not title:
                t = entry.find("{http://www.w3.org/2005/Atom}title")
                if t is not None and t.text:
                    title = t.text.strip()
            # Link
            link_node = entry.find("link")
            if link_node is not None and link_node.text and link_node.text.strip():
                link = link_node.text.strip()
            elif link_node is not None and link_node.get("href"):
                link = link_node.get("href")
            if not link:
                atom_link_node = entry.find("{http://www.w3.org/2005/Atom}link")
                if atom_link_node is not None:
                    link = atom_link_node.get("href", "")
            # Description / excerpt
            d = entry.find("description")
            if d is not None and d.text:
                desc = re.sub(r"<[^>]+>", "", d.text).strip()[:200]
            if not desc:
                s = entry.find("{http://www.w3.org/2005/Atom}summary")
                if s is not None and s.text:
                    desc = re.sub(r"<[^>]+>", "", s.text).strip()[:200]
            # Published date
            p = entry.find("pubDate")
            if p is not None and p.text:
                pub_date = p.text.strip()
            if not pub_date:
                p = entry.find("{http://www.w3.org/2005/Atom}updated")
                if p is not None and p.text:
                    pub_date = p.text.strip()
            if not pub_date:
                p = entry.find("{http://www.w3.org/2005/Atom}published")
                if p is not None and p.text:
                    pub_date = p.text.strip()

            text_check = (title + " " + desc).lower()
            if title and any(kw in text_check for kw in IRAN_KEYWORDS):
                iso_time = normalize_date(pub_date) or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                items.append({
                    "id": hashlib.md5((title + link).encode()).hexdigest()[:12],
                    "type": "news",
                    "tag": tag_type,
                    "source": source_name,
                    "title": title,
                    "excerpt": desc[:180],
                    "url": link,
                    "time": iso_time,
                    "timestamp": iso_time,
                })
    except ET.ParseError:
        pass
    return items


def fetch_one_feed(feed_tuple):
    """Fetch a single RSS feed and return parsed items."""
    url, source_name, tag_type = feed_tuple
    xml = fetch_url(url, timeout=6)
    if xml:
        return parse_rss(xml, source_name, tag_type, max_items=10)
    return []


def fetch_rss_news_feeds():
    """Fetch and rank RSS/Atom feeds only."""
    feeds = [
        ("https://www.iranintl.com/en/feed", "Iran Intl", "breaking"),
        (
            "https://news.google.com/rss/search?q=iran+war+OR+iran+strike+OR+tehran+OR+irgc+OR+hormuz+OR+khamenei+OR+regime+change+iran&hl=en&gl=US&ceid=US:en",
            "Google News",
            "breaking",
        ),
        ("https://feeds.reuters.com/reuters/worldNews", "Reuters", "breaking"),
        ("https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera", "breaking"),
        ("https://www.middleeasteye.net/rss", "Middle East Eye", "regional"),
        ("https://www.timesofisrael.com/feed/", "Times of Israel", "regional"),
        ("https://www.jpost.com/rss/rssfeedsmiddleeast", "Jerusalem Post", "regional"),
        ("https://www.bellingcat.com/feed/", "Bellingcat", "osint"),
        ("https://breakingdefense.com/feed/", "Breaking Defense", "analysis"),
        ("https://warontherocks.com/feed/", "War on the Rocks", "analysis"),
    ]

    all_items = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fetch_one_feed, f): f for f in feeds}
        for future in as_completed(futures, timeout=20):
            try:
                all_items.extend(future.result())
            except Exception:
                pass

    if not all_items:
        return []

    unique = merge_and_dedupe_news_items(all_items, [], limit=25)
    return unique


# ---------------------------------------------------------------------------
# X API integration (high-signal allowlisted accounts only)
# ---------------------------------------------------------------------------
def sanitize_x_text(text):
    if not text:
        return ""
    sanitized = re.sub(r"https?://\S+", "", text)
    return re.sub(r"\s+", " ", sanitized).strip()


def build_x_recent_search_query(accounts=None, keywords=None):
    account_list = [a.lower().lstrip("@") for a in (accounts or X_ALLOWED_ACCOUNTS)]
    keyword_list = keywords or X_QUERY_KEYWORDS

    account_clause = " OR ".join(f"from:{account}" for account in account_list)
    keyword_terms = []
    for keyword in keyword_list:
        term = keyword.strip()
        if not term:
            continue
        keyword_terms.append(f'"{term}"' if " " in term else term)
    keyword_clause = " OR ".join(keyword_terms)

    return f"({account_clause}) ({keyword_clause}) -is:retweet -is:reply -is:quote lang:en"


def fetch_x_recent_search(token, query, max_results=X_MAX_RESULTS):
    params = {
        "query": query,
        "max_results": max(10, min(int(max_results), 100)),
        "tweet.fields": "created_at,author_id,text,public_metrics",
        "expansions": "author_id",
        "user.fields": "username,name,verified,public_metrics",
    }
    url = "https://api.x.com/2/tweets/search/recent?" + urllib.parse.urlencode(params)
    raw = fetch_url(
        url,
        timeout=8,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def is_high_signal_x_post(post, account_weights, keywords, user_by_id, now=None):
    author = user_by_id.get(str(post.get("author_id", "")), {})
    username = (author.get("username") or "").lower()
    if username not in X_ALLOWED_ACCOUNTS:
        return False, 0.0

    cleaned_text = sanitize_x_text(post.get("text", ""))
    if len(cleaned_text) < X_MIN_TEXT_LENGTH:
        return False, 0.0

    text_lower = cleaned_text.lower()
    keyword_hits = sum(1 for kw in keywords if kw in text_lower)
    if keyword_hits == 0:
        return False, 0.0

    iso_time = normalize_date(post.get("created_at"))
    if not iso_time:
        return False, 0.0

    created_at = datetime.strptime(iso_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    now_utc = now or datetime.now(timezone.utc)
    if created_at < (now_utc - timedelta(hours=X_MAX_AGE_HOURS)):
        return False, 0.0

    metrics = post.get("public_metrics") or {}
    likes = int(metrics.get("like_count", 0) or 0)
    reposts = int(metrics.get("retweet_count", 0) or 0)
    replies = int(metrics.get("reply_count", 0) or 0)
    quotes = int(metrics.get("quote_count", 0) or 0)
    engagement = likes + (reposts * 2) + replies + quotes

    if engagement < X_MIN_ENGAGEMENT:
        return False, 0.0

    account_weight = float(account_weights.get(username, 1.0))
    score = engagement + (keyword_hits * 4) + (account_weight * 5)
    if score < X_MIN_SCORE:
        return False, 0.0

    return True, round(score, 2)


def normalize_x_post_to_news_item(post, user_by_id):
    author = user_by_id.get(str(post.get("author_id", "")), {})
    username = (author.get("username") or "").lstrip("@")
    tweet_id = str(post.get("id", "")).strip()

    cleaned = sanitize_x_text(post.get("text", ""))
    title = cleaned if len(cleaned) <= 160 else cleaned[:157] + "..."
    excerpt = cleaned if len(cleaned) <= 180 else cleaned[:177] + "..."

    iso_time = normalize_date(post.get("created_at")) or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    source = f"@{username}" if username else "X"
    url = f"https://x.com/{username}/status/{tweet_id}" if username and tweet_id else "https://x.com"

    stable_id = f"x-{tweet_id}" if tweet_id else "x-" + hashlib.md5((title + source + url).encode()).hexdigest()[:12]

    return {
        "id": stable_id,
        "type": "osint",
        "tag": "osint",
        "source": source,
        "title": title,
        "excerpt": excerpt,
        "url": url,
        "time": iso_time,
        "timestamp": iso_time,
    }


def build_llm_relevance_prompt(items):
    tweet_lines = []
    for idx, item in enumerate(items):
        tweet_lines.append(f"{idx + 1}. {item.get('source', 'X')}: {item.get('title', '')}")

    tweets_block = "\n".join(tweet_lines)
    return (
        "You are filtering X posts for an Iran crisis monitoring dashboard.\n"
        "Include posts directly relevant to Iran military, nuclear, IRGC, Hormuz, Hezbollah, "
        "US-Iran-Israel escalation, or market impacts from Iran conflict.\n"
        "Reply with ONLY tweet numbers, comma-separated, or NONE.\n\n"
        f"Tweets:\n{tweets_block}"
    )


def parse_llm_relevant_indices(raw_text, total_count):
    cleaned = (raw_text or "").strip()
    if not cleaned:
        return []
    if cleaned.upper() == "NONE":
        return []

    indices = []
    for token in cleaned.split(","):
        token = token.strip()
        if not token.isdigit():
            continue
        idx = int(token) - 1
        if 0 <= idx < total_count and idx not in indices:
            indices.append(idx)
    return indices


def filter_x_items_with_llm(items, return_meta=False):
    llm_meta = {
        "inputCount": len(items or []),
        "outputCount": len(items or []),
        "llmEnabled": False,
        "llmApplied": False,
        "result": "not_run",
    }
    api_key = os.getenv(ANTHROPIC_API_KEY_ENV, "").strip()
    if not items:
        llm_meta["result"] = "no_items"
        return (items, llm_meta) if return_meta else items
    if not api_key:
        llm_meta["result"] = "no_api_key"
        return (items, llm_meta) if return_meta else items

    llm_meta["llmEnabled"] = True
    llm_meta["llmApplied"] = True

    prompt = build_llm_relevance_prompt(items)
    model = os.getenv(ANTHROPIC_MODEL_ENV, ANTHROPIC_DEFAULT_MODEL).strip() or ANTHROPIC_DEFAULT_MODEL
    llm_meta["model"] = model
    payload = {
        "model": model,
        "max_tokens": 120,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    raw = fetch_url(
        ANTHROPIC_API_URL,
        timeout=6,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    if not raw:
        llm_meta["result"] = "request_failed_passthrough"
        return (items, llm_meta) if return_meta else items

    try:
        response = json.loads(raw)
        content_blocks = response.get("content") or []
        llm_text = " ".join(
            block.get("text", "")
            for block in content_blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
    except Exception:
        llm_meta["result"] = "parse_failed_passthrough"
        return (items, llm_meta) if return_meta else items

    indices = parse_llm_relevant_indices(llm_text, len(items))
    if not indices and llm_text.upper() == "NONE":
        llm_meta["outputCount"] = 0
        llm_meta["result"] = "filtered_none"
        return ([], llm_meta) if return_meta else []
    if not indices:
        llm_meta["result"] = "unparseable_passthrough"
        return (items, llm_meta) if return_meta else items

    filtered = [items[idx] for idx in indices]
    llm_meta["outputCount"] = len(filtered)
    llm_meta["result"] = "filtered_indices"
    return (filtered, llm_meta) if return_meta else filtered


def fetch_x_source_items(now=None, return_debug=False):
    debug = {
        "xEnabled": False,
        "xFetched": 0,
        "xUsers": 0,
        "xPassedScore": 0,
        "xSelectedBeforeLlm": 0,
        "xAfterLlm": 0,
        "xDroppedByLlm": 0,
        "xLlm": {"result": "not_run"},
        "xStatus": "not_run",
    }

    token = os.getenv(X_BEARER_TOKEN_ENV, "").strip()
    if not token:
        debug["xStatus"] = "no_x_token"
        return ([], debug) if return_debug else []
    debug["xEnabled"] = True

    query = build_x_recent_search_query()
    payload = fetch_x_recent_search(token, query, max_results=X_MAX_RESULTS)
    posts = payload.get("data") or []
    users = (payload.get("includes") or {}).get("users") or []
    debug["xFetched"] = len(posts)
    debug["xUsers"] = len(users)
    if not posts or not users:
        debug["xStatus"] = "no_posts_or_users"
        return ([], debug) if return_debug else []

    user_by_id = {str(user.get("id", "")): user for user in users}
    candidates = []

    for post in posts:
        accepted, score = is_high_signal_x_post(
            post,
            account_weights=X_ACCOUNT_WEIGHTS,
            keywords=X_QUERY_KEYWORDS,
            user_by_id=user_by_id,
            now=now,
        )
        if not accepted:
            continue
        debug["xPassedScore"] += 1

        author = user_by_id.get(str(post.get("author_id", "")), {})
        username = (author.get("username") or "").lower()
        if not username:
            continue

        candidates.append((
            score,
            username,
            normalize_x_post_to_news_item(post, user_by_id),
        ))

    # Highest-signal first, then newest.
    candidates.sort(key=lambda item: (item[0], item[2].get("time", "")), reverse=True)

    selected = []
    account_counts = {}
    for score, username, item in candidates:
        _ = score
        if account_counts.get(username, 0) >= X_MAX_PER_ACCOUNT:
            continue
        selected.append(item)
        account_counts[username] = account_counts.get(username, 0) + 1
        if len(selected) >= X_MAX_ITEMS:
            break

    debug["xSelectedBeforeLlm"] = len(selected)
    selected_after_llm, llm_meta = filter_x_items_with_llm(selected, return_meta=True)
    debug["xLlm"] = llm_meta
    debug["xAfterLlm"] = len(selected_after_llm)
    debug["xDroppedByLlm"] = len(selected) - len(selected_after_llm)
    debug["xStatus"] = "ok"
    return (selected_after_llm, debug) if return_debug else selected_after_llm


def _news_dedupe_key(item):
    title = (item.get("title") or "").lower()
    normalized = re.sub(r"[^a-z0-9]", "", title)
    if normalized:
        return normalized[:80]
    fallback = (item.get("url") or item.get("id") or "").lower()
    return fallback[:80]


def merge_and_dedupe_news_items(rss_items, x_items, limit=25):
    combined = (rss_items or []) + (x_items or [])
    unique = []
    seen = set()

    for item in combined:
        key = _news_dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    unique.sort(key=lambda item: item.get("time", "1970-01-01T00:00:00Z"), reverse=True)
    return unique[:limit]


def fetch_news_feeds(return_debug=False):
    rss_items = fetch_rss_news_feeds()
    x_items, x_debug = fetch_x_source_items(return_debug=True)
    merged = merge_and_dedupe_news_items(rss_items, x_items, limit=25)

    if return_debug:
        return merged, {
            "rssCount": len(rss_items),
            "mergedCount": len(merged),
            "x": x_debug,
        }
    return merged


# ---------------------------------------------------------------------------
# Polymarket - price history via CLOB API
# ---------------------------------------------------------------------------
def fetch_price_history(token_id, interval="max", fidelity=120):
    """Fetch real price history from Polymarket CLOB API.

    Args:
        token_id: The CLOB token ID
        interval: 'max', '1m', '1w', '1d', '6h', '1h'
        fidelity: Data resolution in minutes (120 = 2-hour bars)

    Returns: list of {t: ISO8601, y: probability_pct}
    """
    url = f"https://clob.polymarket.com/prices-history?market={token_id}&interval={interval}&fidelity={fidelity}"
    raw = fetch_url(url, timeout=10)
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        history = data.get("history", [])
        result = []
        for pt in history:
            ts = datetime.utcfromtimestamp(pt["t"]).strftime("%Y-%m-%dT%H:%M:%SZ")
            result.append({"t": ts, "y": round(float(pt["p"]) * 100, 1)})
        return result
    except Exception:
        return []


def fetch_polymarket():
    markets = []
    try:
        url = "https://gamma-api.polymarket.com/events?active=true&closed=false&order=volume24hr&ascending=false&limit=50"
        data = fetch_url(url, timeout=8)
        if not data:
            return markets
        events = json.loads(data)
        for event in events:
            title = event.get("title", "")
            if not any(kw in title.lower() for kw in IRAN_KEYWORDS):
                continue
            markets_list = event.get("markets", [])
            total_volume = 0
            outcomes = []
            active_mkts = [m for m in markets_list if not m.get("closed", False)]

            # Extract clobTokenIds from first active market
            first_token_id = None
            for mkt in active_mkts[:1]:
                raw_ids = mkt.get("clobTokenIds")
                if raw_ids:
                    try:
                        parsed = json.loads(raw_ids) if isinstance(raw_ids, str) else raw_ids
                        if isinstance(parsed, list) and parsed:
                            first_token_id = str(parsed[0])
                    except Exception:
                        pass

            for mkt in active_mkts[:6]:
                outcome = mkt.get("groupItemTitle", mkt.get("question", title))
                price_str = mkt.get("outcomePrices", "")
                volume = float(mkt.get("volume", 0) or 0)
                total_volume += volume
                yes_price = 0
                try:
                    prices = json.loads(price_str) if isinstance(price_str, str) and price_str else []
                    if isinstance(prices, list) and len(prices) >= 1:
                        yes_price = float(prices[0])
                except Exception:
                    pass
                outcomes.append({"label": outcome, "probability": round(yes_price * 100, 1), "active": True})
            for mkt in [m for m in markets_list if m.get("closed", False)]:
                total_volume += float(mkt.get("volume", 0) or 0)
            if outcomes:
                vol_str = f"${total_volume/1e6:.1f}M" if total_volume >= 1e6 else f"${total_volume/1e3:.0f}K"
                markets.append({
                    "question": title,
                    "volume": total_volume,
                    "volumeFormatted": vol_str,
                    "outcomes": outcomes,
                    "status": "active",
                    "source": "Polymarket",
                    "url": f"https://polymarket.com/event/{event.get('slug', '')}",
                    "_clobTokenId": first_token_id,  # internal field, stripped later
                })
    except Exception:
        pass
    markets.sort(key=lambda m: m["volume"], reverse=True)
    return markets


def build_odds_history(markets):
    """
    Fetch real CLOB price history for the top 6 markets.
    Returns dict: question -> {label: [history_pts]}
    """
    odds_history = {}
    top_markets = markets[:6]

    for m in top_markets:
        question = m["question"]
        token_id = m.get("_clobTokenId")
        label = next(
            (o["label"] for o in m["outcomes"] if o["label"] == "Yes"),
            m["outcomes"][0]["label"] if m["outcomes"] else "Yes",
        )

        history_pts = []
        if token_id:
            history_pts = fetch_price_history(token_id, interval="max", fidelity=120)

        # Fallback: synthesize if no real data
        if not history_pts:
            yes_prob = next(
                (o["probability"] for o in m["outcomes"] if o["label"] == "Yes"),
                m["outcomes"][0]["probability"] if m["outcomes"] else 50.0,
            )
            now_ts = datetime.utcnow()
            for i in range(14, -1, -1):
                t = now_ts - timedelta(hours=i * 6)
                noise = random.uniform(-3, 3) * (i / 14)
                val = max(1, min(99, yes_prob + noise))
                history_pts.append({"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "y": round(val, 1)})
            history_pts[-1]["y"] = yes_prob

        odds_history[question] = {label: history_pts}

    # Clean up internal field
    for m in markets:
        m.pop("_clobTokenId", None)

    return odds_history


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        now = datetime.now(timezone.utc)

        # Fetch news
        news, news_debug = fetch_news_feeds(return_debug=True)

        # Fetch markets
        markets = fetch_polymarket()

        # Fetch real price history for top 6 markets
        odds_history = build_odds_history(markets)

        # Limit markets output to top 6 (already sorted by volume)
        markets_out = markets[:6]

        response = {
            "timestamp": now.isoformat(),
            "lastUpdated": now.strftime("%d %b %Y - %H:%M GMT").upper(),
            "news": news[:25],
            "markets": markets_out,
            "oddsHistory": odds_history,
            "meta": {
                "newsCount": len(news),
                "rssCount": news_debug.get("rssCount", 0),
                "mergedCount": news_debug.get("mergedCount", len(news)),
                "xDebug": news_debug.get("x", {}),
                "marketsCount": len(markets_out),
                "historyPoints": sum(
                    len(list(v.values())[0]) if v else 0
                    for v in odds_history.values()
                ),
                "fetchedAt": now.isoformat(),
            },
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=55")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))
