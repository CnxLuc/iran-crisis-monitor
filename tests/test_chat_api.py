import importlib.util
import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path


def load_chat_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "api" / "chat.py"
    spec = importlib.util.spec_from_file_location("chat_api", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_db():
    db = sqlite3.connect(":memory:")
    db.execute(
        """CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analyst TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    db.execute(
        """CREATE TABLE presence (
            analyst TEXT PRIMARY KEY,
            last_seen TEXT NOT NULL,
            color TEXT NOT NULL
        )"""
    )
    db.commit()
    return db


class ChatApiTtlTests(unittest.TestCase):
    def setUp(self):
        self.chat = load_chat_module()

    def test_message_cutoff_iso_is_five_minutes_before_now(self):
        now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
        cutoff = self.chat.message_cutoff_iso(now)
        self.assertEqual(cutoff, "2026-02-28T11:55:00+00:00")

    def test_prune_expired_messages_deletes_only_rows_older_than_ttl(self):
        db = make_db()
        now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
        db.execute(
            "INSERT INTO messages (analyst, text, created_at) VALUES (?,?,?)",
            ("A", "old", "2026-02-28T11:54:59+00:00"),
        )
        db.execute(
            "INSERT INTO messages (analyst, text, created_at) VALUES (?,?,?)",
            ("B", "new", "2026-02-28T11:55:00+00:00"),
        )
        db.commit()

        self.chat.prune_expired_messages(db, now)
        rows = db.execute("SELECT text FROM messages ORDER BY id").fetchall()
        self.assertEqual(rows, [("new",)])

    def test_fetch_messages_ignores_expired_rows(self):
        db = make_db()
        now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
        db.execute(
            "INSERT INTO messages (analyst, text, created_at) VALUES (?,?,?)",
            ("A", "expired", "2026-02-28T11:40:00+00:00"),
        )
        db.execute(
            "INSERT INTO messages (analyst, text, created_at) VALUES (?,?,?)",
            ("B", "fresh", "2026-02-28T11:59:00+00:00"),
        )
        db.commit()

        rows = self.chat.fetch_messages(db, since=None, now=now)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], "fresh")


if __name__ == "__main__":
    unittest.main()
