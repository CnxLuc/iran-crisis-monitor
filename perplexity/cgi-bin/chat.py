#!/usr/bin/env python3
"""Chat API for Iran Crisis Monitor — analyst situation room.

Endpoints (via PATH_INFO):
  GET  /messages?since=<iso_ts>  — fetch messages since timestamp (or last 50)
  POST /messages                 — send a message { "analyst": "...", "text": "..." }
  POST /session                  — create session, get assigned analyst codename
  GET  /online                   — get active analysts (heartbeat within 90s)
  POST /heartbeat                — update presence { "analyst": "..." }
"""
import json
import os
import sys
import sqlite3
import hashlib
import random
from datetime import datetime, timezone, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chat.db")

# CIA-style analyst codenames — first name + last initial format
ANALYST_FIRST = [
    "ACHILLES", "ATLAS", "BANSHEE", "BEACON", "CIPHER", "COBALT",
    "CONDOR", "DAGGER", "DELTA", "FALCON", "GRANITE", "HAWK",
    "IRON", "JACKAL", "KEYSTONE", "LANCER", "MERCURY", "NEXUS",
    "ONYX", "PHANTOM", "RAPTOR", "SABER", "SENTINEL", "SHADOW",
    "SIERRA", "SPECTRE", "STORM", "TEMPEST", "VANGUARD", "VIPER",
    "WARDEN", "ZENITH", "ANVIL", "BASTION", "CROSSBOW", "EMBER",
    "FROSTBITE", "HARBINGER", "JAVELIN", "NOMAD", "ORACLE",
    "PALADIN", "RAVEN", "SPARTAN", "TITAN", "WRAITH"
]

ANALYST_SUFFIX = [
    "ACTUAL", "PRIME", "ALPHA", "BRAVO", "ZERO", "ONE", "SIX", "SEVEN"
]

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        analyst TEXT NOT NULL,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS presence (
        analyst TEXT PRIMARY KEY,
        last_seen TEXT NOT NULL,
        color TEXT NOT NULL
    )""")
    db.commit()
    return db

# Analyst colors for the chat (muted, professional)
COLORS = ["#2563eb", "#dc2626", "#d97706", "#16a34a", "#7c3aed", "#0891b2",
           "#be185d", "#9333ea", "#0d9488", "#b45309", "#4f46e5", "#059669"]

def generate_codename(db):
    """Generate a unique analyst codename."""
    existing = set(r[0] for r in db.execute("SELECT analyst FROM presence").fetchall())
    for _ in range(100):
        name = random.choice(ANALYST_FIRST) + "-" + random.choice(ANALYST_SUFFIX)
        if name not in existing:
            return name
    # Fallback with number
    return random.choice(ANALYST_FIRST) + "-" + str(random.randint(10, 99))

def get_color_for_analyst(analyst):
    """Deterministic color from codename."""
    h = int(hashlib.md5(analyst.encode()).hexdigest()[:8], 16)
    return COLORS[h % len(COLORS)]

def handle_get_messages(db, query_string):
    since = None
    if "since=" in query_string:
        since = query_string.split("since=")[1].split("&")[0]

    if since:
        rows = db.execute(
            "SELECT id, analyst, text, created_at FROM messages WHERE created_at > ? ORDER BY created_at ASC LIMIT 100",
            (since,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, analyst, text, created_at FROM messages ORDER BY id DESC LIMIT 50"
        ).fetchall()
        rows = list(reversed(rows))

    messages = []
    for row in rows:
        messages.append({
            "id": row[0],
            "analyst": row[1],
            "text": row[2],
            "time": row[3],
            "color": get_color_for_analyst(row[1])
        })
    return messages

def handle_post_message(db, body):
    analyst = body.get("analyst", "UNKNOWN")
    text = body.get("text", "").strip()
    if not text:
        return {"error": "Empty message"}, 400
    if len(text) > 500:
        text = text[:500]
    now = datetime.now(timezone.utc).isoformat()
    db.execute("INSERT INTO messages (analyst, text, created_at) VALUES (?,?,?)",
               (analyst, text, now))
    db.commit()
    # Update presence
    color = get_color_for_analyst(analyst)
    db.execute("INSERT OR REPLACE INTO presence (analyst, last_seen, color) VALUES (?,?,?)",
               (analyst, now, color))
    db.commit()
    return {"status": "ok", "time": now}

def handle_create_session(db):
    codename = generate_codename(db)
    color = get_color_for_analyst(codename)
    now = datetime.now(timezone.utc).isoformat()
    db.execute("INSERT OR REPLACE INTO presence (analyst, last_seen, color) VALUES (?,?,?)",
               (codename, now, color))
    db.commit()
    return {"analyst": codename, "color": color}

def handle_get_online(db):
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
    rows = db.execute(
        "SELECT analyst, last_seen, color FROM presence WHERE last_seen > ? ORDER BY analyst",
        (cutoff,)
    ).fetchall()
    return [{"analyst": r[0], "color": r[2], "lastSeen": r[1]} for r in rows]

def handle_heartbeat(db, body):
    analyst = body.get("analyst", "")
    if not analyst:
        return {"error": "No analyst"}, 400
    now = datetime.now(timezone.utc).isoformat()
    color = get_color_for_analyst(analyst)
    db.execute("INSERT OR REPLACE INTO presence (analyst, last_seen, color) VALUES (?,?,?)",
               (analyst, now, color))
    db.commit()
    # Cleanup old presences (>10 min)
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    db.execute("DELETE FROM presence WHERE last_seen < ?", (old,))
    # Cleanup old messages (>24h)
    day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    db.execute("DELETE FROM messages WHERE created_at < ?", (day_ago,))
    db.commit()
    return {"status": "ok"}

def main():
    method = os.environ.get("REQUEST_METHOD", "GET")
    path = os.environ.get("PATH_INFO", "")
    query = os.environ.get("QUERY_STRING", "")

    # Handle CORS preflight
    if method == "OPTIONS":
        print("Status: 200")
        print("Content-Type: application/json")
        print("Access-Control-Allow-Origin: *")
        print("Access-Control-Allow-Methods: GET, POST, OPTIONS")
        print("Access-Control-Allow-Headers: Content-Type")
        print()
        print('{}')
        return

    db = get_db()
    status = 200
    result = {}

    try:
        body = {}
        if method == "POST":
            length = int(os.environ.get("CONTENT_LENGTH", 0) or 0)
            if length > 0:
                body = json.loads(sys.stdin.read(length))

        if path == "/messages" and method == "GET":
            result = handle_get_messages(db, query)
        elif path == "/messages" and method == "POST":
            r = handle_post_message(db, body)
            if isinstance(r, tuple):
                result, status = r
            else:
                result = r
                status = 201
        elif path == "/session" and method == "POST":
            result = handle_create_session(db)
            status = 201
        elif path == "/online" and method == "GET":
            result = handle_get_online(db)
        elif path == "/heartbeat" and method == "POST":
            r = handle_heartbeat(db, body)
            if isinstance(r, tuple):
                result, status = r
            else:
                result = r
        else:
            result = {"error": "Not found", "path": path, "method": method}
            status = 404
    except Exception as e:
        result = {"error": str(e)}
        status = 500
    finally:
        db.close()

    print(f"Status: {status}")
    print("Content-Type: application/json")
    print("Access-Control-Allow-Origin: *")
    print("Access-Control-Allow-Methods: GET, POST, OPTIONS")
    print("Access-Control-Allow-Headers: Content-Type")
    print("Cache-Control: no-cache")
    print()
    print(json.dumps(result))

if __name__ == "__main__":
    main()
