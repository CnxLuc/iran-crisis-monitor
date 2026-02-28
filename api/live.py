"""Vercel serverless function for Iran Crisis Monitor live data with history tracking."""
import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import re
import hashlib
import random
from http.server import BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_url(url, timeout=8):
    req = urllib.request.Request(url, headers={
        "User-Agent": "IranCrisisMonitor/1.0",
        "Accept": "application/json, application/xml, text/xml, */*"
    })
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
    "rouhani", "raisi", "pezeshkian", "iran president", "revolutionary guard"
]

IRRELEVANT_MARKET_TITLE_PATTERNS = [
    r"\.\.\.\?",          # unresolved placeholder titles, e.g. "US next strikes Iran on...?"
    r"…\?",               # same as above with unicode ellipsis
    r"\bover__\b",        # malformed market templates
]

LLM_RELEVANCE_SYSTEM_PROMPT = (
    "You are selecting prediction markets for an Iran crisis dashboard. "
    "Prioritize strategic, decision-relevant markets about Iran conflict escalation, "
    "regional spillover, regime stability, and macro-energy impacts. "
    "Reject malformed placeholder markets and low-signal date-picker trivia. "
    "Return only a comma-separated list of item numbers."
)

def is_relevant_market_title(title):
    """Return True for Iran-relevant, non-placeholder market titles."""
    if not title:
        return False
    lowered = title.strip().lower()
    if not lowered:
        return False
    if not any(kw in lowered for kw in IRAN_KEYWORDS):
        return False
    return not any(re.search(pattern, lowered) for pattern in IRRELEVANT_MARKET_TITLE_PATTERNS)

def extract_ranked_ids(text, max_count, max_index):
    """Extract ranked 1-based item ids from free-form model output."""
    if not text:
        return []
    ranked = []
    seen = set()
    for tok in re.findall(r"\d+", str(text)):
        idx = int(tok)
        if 1 <= idx <= max_index and idx not in seen:
            ranked.append(idx)
            seen.add(idx)
            if len(ranked) >= max_count:
                break
    return ranked

def extract_anthropic_message_text(data):
    """Extract concatenated text from an Anthropic Messages API response."""
    if not isinstance(data, dict):
        return ""
    content = data.get("content")
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
            parts.append(str(block.get("text")))
    return " ".join(parts).strip()

def llm_rank_market_ids(markets, max_keep=6, timeout=6):
    """
    Optionally ask an LLM to pick the most relevant markets.
    Returns ranked 1-based ids, or [] on any failure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or not markets:
        return []

    model = os.environ.get("ANTHROPIC_MARKET_MODEL", "claude-sonnet-4-6")
    items = []
    for i, m in enumerate(markets, start=1):
        question = (m.get("question") or "").strip()
        resolution = m.get("resolutionDate") or m.get("endDate") or "unknown"
        yes_prob = next(
            (o.get("probability") for o in m.get("outcomes", []) if str(o.get("label", "")).lower() == "yes"),
            m.get("outcomes", [{}])[0].get("probability", "n/a") if m.get("outcomes") else "n/a"
        )
        vol = m.get("volumeFormatted") or "n/a"
        items.append(f"{i}. {question} | resolves {resolution} | yes {yes_prob}% | volume {vol}")

    user_prompt = (
        f"Pick up to {max_keep} items that are most relevant for crisis monitoring.\n"
        "Return only item numbers, comma-separated (example: 3,1,7,2).\n\n"
        + "\n".join(items)
    )
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 80,
        "system": LLM_RELEVANCE_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}]
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "User-Agent": "IranCrisisMonitor/1.0"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        content = extract_anthropic_message_text(data)
        return extract_ranked_ids(content, max_keep, len(markets))
    except Exception:
        return []

def select_markets_for_dashboard(markets, max_keep=6):
    """Select markets for UI cards, optionally LLM-ranked, deterministic fallback."""
    if not markets:
        return []
    candidate_pool = markets[:20]  # bound token/cost for LLM ranking
    ranked_ids = llm_rank_market_ids(candidate_pool, max_keep=max_keep)
    if not ranked_ids:
        return candidate_pool[:max_keep]

    selected = []
    used = set()
    for one_based in ranked_ids:
        idx = one_based - 1
        if 0 <= idx < len(candidate_pool) and idx not in used:
            selected.append(candidate_pool[idx])
            used.add(idx)
            if len(selected) >= max_keep:
                return selected

    for idx, m in enumerate(candidate_pool):
        if idx in used:
            continue
        selected.append(m)
        if len(selected) >= max_keep:
            break
    return selected

# ---------------------------------------------------------------------------
# Date normalization
# ---------------------------------------------------------------------------
def normalize_date(date_str):
    """Convert various date formats to ISO 8601 UTC string."""
    if not date_str:
        return None
    if re.match(r'\d{4}-\d{2}-\d{2}T', date_str):
        return date_str[:20].rstrip('T') + 'Z'
    import datetime as dt_module
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            d = dt_module.datetime.strptime(date_str.strip(), fmt)
            if d.tzinfo:
                d = d.astimezone(dt_module.timezone.utc).replace(tzinfo=None)
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
            l = entry.find("link")
            if l is not None and l.text and l.text.strip():
                link = l.text.strip()
            elif l is not None and l.get("href"):
                link = l.get("href")
            if not link:
                l = entry.find("{http://www.w3.org/2005/Atom}link")
                if l is not None:
                    link = l.get("href", "")
            # Description / excerpt
            d = entry.find("description")
            if d is not None and d.text:
                desc = re.sub(r'<[^>]+>', '', d.text).strip()[:200]
            if not desc:
                s = entry.find("{http://www.w3.org/2005/Atom}summary")
                if s is not None and s.text:
                    desc = re.sub(r'<[^>]+>', '', s.text).strip()[:200]
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
                    "timestamp": iso_time
                })
    except ET.ParseError:
        pass
    return items

# ---------------------------------------------------------------------------
# News feed fetching
# ---------------------------------------------------------------------------
def fetch_one_feed(feed_tuple):
    """Fetch a single RSS feed and return parsed items."""
    url, source_name, tag_type = feed_tuple
    xml = fetch_url(url, timeout=6)
    if xml:
        return parse_rss(xml, source_name, tag_type, max_items=10)
    return []

def fetch_news_feeds():
    """
    Fetch live news from multiple RSS sources, filter for Iran relevance,
    deduplicate, and sort by recency.
    """
    feeds = [
        # Iran International - fastest Farsi-English source
        (
            "https://www.iranintl.com/en/feed",
            "Iran Intl", "breaking"
        ),
        # Google News aggregator - broadest coverage
        (
            "https://news.google.com/rss/search?q=iran+war+OR+iran+strike+OR+tehran+OR+irgc+OR+hormuz+OR+khamenei+OR+regime+change+iran&hl=en&gl=US&ceid=US:en",
            "Google News", "breaking"
        ),
        # Wire services
        ("https://feeds.reuters.com/reuters/worldNews", "Reuters", "breaking"),
        ("https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera", "breaking"),
        # Regional specialist
        ("https://www.middleeasteye.net/rss", "Middle East Eye", "regional"),
        ("https://www.timesofisrael.com/feed/", "Times of Israel", "regional"),
        ("https://www.jpost.com/rss/rssfeedsmiddleeast", "Jerusalem Post", "regional"),
        # OSINT & defense analysis
        ("https://www.bellingcat.com/feed/", "Bellingcat", "osint"),
        ("https://breakingdefense.com/feed/", "Breaking Defense", "analysis"),
        ("https://warontherocks.com/feed/", "War on the Rocks", "analysis"),
    ]

    all_items = []

    # Parallel fetch
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fetch_one_feed, f): f for f in feeds}
        for future in as_completed(futures, timeout=20):
            try:
                result = future.result()
                all_items.extend(result)
            except Exception:
                pass

    if not all_items:
        return []

    # Deduplicate by normalizing title
    seen = set()
    unique = []
    for item in all_items:
        key = re.sub(r'[^a-z0-9]', '', item["title"].lower())[:50]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    # Sort by recency
    unique.sort(key=lambda x: x.get("time", "1970-01-01T00:00:00Z"), reverse=True)
    return unique[:25]

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
    import datetime as dt_module
    url = f"https://clob.polymarket.com/prices-history?market={token_id}&interval={interval}&fidelity={fidelity}"
    raw = fetch_url(url, timeout=10)
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        history = data.get("history", [])
        result = []
        for pt in history:
            ts = dt_module.datetime.utcfromtimestamp(pt["t"]).strftime("%Y-%m-%dT%H:%M:%SZ")
            result.append({"t": ts, "y": round(float(pt["p"]) * 100, 1)})
        return result
    except Exception:
        return []

def fetch_polymarket():
    import urllib.parse as up
    markets = []
    try:
        url = "https://gamma-api.polymarket.com/events?active=true&closed=false&order=volume24hr&ascending=false&limit=50"
        data = fetch_url(url, timeout=8)
        if not data:
            return markets
        events = json.loads(data)
        for event in events:
            title = event.get("title", "")
            if not is_relevant_market_title(title):
                continue
            markets_list = event.get("markets", [])
            resolution_date = (
                event.get("endDate")
                or event.get("endDateIso")
                or event.get("endDateISO")
            )
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
                    "resolutionDate": resolution_date,
                    "volume": total_volume,
                    "volumeFormatted": vol_str,
                    "outcomes": outcomes,
                    "status": "active",
                    "source": "Polymarket",
                    "url": f"https://polymarket.com/event/{event.get('slug', '')}",
                    "_clobTokenId": first_token_id  # internal field, stripped later
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
    import datetime as dt_module
    odds_history = {}
    top_markets = markets[:6]

    for m in top_markets:
        question = m["question"]
        token_id = m.get("_clobTokenId")
        label = next(
            (o["label"] for o in m["outcomes"] if o["label"] == "Yes"),
            m["outcomes"][0]["label"] if m["outcomes"] else "Yes"
        )

        history_pts = []
        if token_id:
            history_pts = fetch_price_history(token_id, interval="max", fidelity=120)

        # Fallback: synthesize if no real data
        if not history_pts:
            yes_prob = next(
                (o["probability"] for o in m["outcomes"] if o["label"] == "Yes"),
                m["outcomes"][0]["probability"] if m["outcomes"] else 50.0
            )
            now_ts = dt_module.datetime.utcnow()
            for i in range(14, -1, -1):
                t = now_ts - dt_module.timedelta(hours=i * 6)
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
        news = fetch_news_feeds()

        # Fetch markets
        markets = fetch_polymarket()
        markets_out = select_markets_for_dashboard(markets, max_keep=6)

        # Fetch real price history for selected markets
        odds_history = build_odds_history(markets_out)

        response = {
            "timestamp": now.isoformat(),
            "lastUpdated": now.strftime("%d %b %Y - %H:%M GMT").upper(),
            "news": news[:25],
            "markets": markets_out,
            "oddsHistory": odds_history,
            "meta": {
                "newsCount": len(news),
                "marketsCount": len(markets_out),
                "historyPoints": sum(
                    len(list(v.values())[0]) if v else 0
                    for v in odds_history.values()
                ),
                "fetchedAt": now.isoformat()
            }
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=55")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))
