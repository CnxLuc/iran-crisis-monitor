"""Vercel serverless function for Situation Room chat."""
import json
import sqlite3
import hashlib
import random
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DB_PATH = "/tmp/chat.db"

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
ANALYST_SUFFIX = ["ACTUAL", "PRIME", "ALPHA", "BRAVO", "ZERO", "ONE", "SIX", "SEVEN"]
COLORS = ["#2563eb", "#dc2626", "#d97706", "#16a34a", "#7c3aed", "#0891b2",
           "#be185d", "#9333ea", "#0d9488", "#b45309", "#4f46e5", "#059669"]

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

def get_color(analyst):
    h = int(hashlib.md5(analyst.encode()).hexdigest()[:8], 16)
    return COLORS[h % len(COLORS)]

def generate_codename(db):
    existing = set(r[0] for r in db.execute("SELECT analyst FROM presence").fetchall())
    for _ in range(100):
        name = random.choice(ANALYST_FIRST) + "-" + random.choice(ANALYST_SUFFIX)
        if name not in existing:
            return name
    return random.choice(ANALYST_FIRST) + "-" + str(random.randint(10, 99))


class handler(BaseHTTPRequestHandler):
    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache")

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _get_action(self):
        """Get action from query param or path info."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        # First check ?action= param
        if "action" in params:
            return "/" + params["action"][0]
        # Then check path info after /api/chat.py
        path = parsed.path
        for prefix in ["/api/chat.py", "/api/chat"]:
            if path.startswith(prefix):
                rest = path[len(prefix):]
                if rest:
                    return rest
        return ""

    def _get_query_params(self):
        parsed = urlparse(self.path)
        return parse_qs(parsed.query)

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                raw = self.rfile.read(length)
                return json.loads(raw.decode("utf-8"))
        except:
            pass
        return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        action = self._get_action()
        db = get_db()
        try:
            if action == "/messages":
                params = self._get_query_params()
                since = params.get("since", [None])[0]
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
                result = [{"id": r[0], "analyst": r[1], "text": r[2], "time": r[3], "color": get_color(r[1])} for r in rows]
                self._json_response(result)

            elif action == "/online":
                cutoff = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
                rows = db.execute(
                    "SELECT analyst, last_seen, color FROM presence WHERE last_seen > ? ORDER BY analyst",
                    (cutoff,)
                ).fetchall()
                self._json_response([{"analyst": r[0], "color": r[2], "lastSeen": r[1]} for r in rows])

            else:
                self._json_response({"error": "Not found", "action": action}, 404)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)
        finally:
            db.close()

    def do_POST(self):
        action = self._get_action()
        body = self._read_body()
        db = get_db()
        try:
            if action == "/messages":
                analyst = body.get("analyst", "UNKNOWN")
                text = body.get("text", "").strip()
                if not text:
                    self._json_response({"error": "Empty message"}, 400)
                    return
                if len(text) > 500:
                    text = text[:500]
                now = datetime.now(timezone.utc).isoformat()
                db.execute("INSERT INTO messages (analyst, text, created_at) VALUES (?,?,?)", (analyst, text, now))
                color = get_color(analyst)
                db.execute("INSERT OR REPLACE INTO presence (analyst, last_seen, color) VALUES (?,?,?)", (analyst, now, color))
                db.commit()
                self._json_response({"status": "ok", "time": now}, 201)

            elif action == "/session":
                codename = generate_codename(db)
                color = get_color(codename)
                now = datetime.now(timezone.utc).isoformat()
                db.execute("INSERT OR REPLACE INTO presence (analyst, last_seen, color) VALUES (?,?,?)", (codename, now, color))
                db.commit()
                self._json_response({"analyst": codename, "color": color}, 201)

            elif action == "/heartbeat":
                analyst = body.get("analyst", "")
                if not analyst:
                    self._json_response({"error": "No analyst"}, 400)
                    return
                now = datetime.now(timezone.utc).isoformat()
                color = get_color(analyst)
                db.execute("INSERT OR REPLACE INTO presence (analyst, last_seen, color) VALUES (?,?,?)", (analyst, now, color))
                old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
                db.execute("DELETE FROM presence WHERE last_seen < ?", (old,))
                day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                db.execute("DELETE FROM messages WHERE created_at < ?", (day_ago,))
                db.commit()
                self._json_response({"status": "ok"})

            else:
                self._json_response({"error": "Not found", "action": action}, 404)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)
        finally:
            db.close()
