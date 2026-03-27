"""Database setup and models for Hampster Dance AI."""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import os

# Use /data for persistent volume on Fly.io, fall back to local dir
_data_dir = Path(os.environ.get("DATA_DIR", str(Path(__file__).parent)))
DB_PATH = _data_dir / "hampsterdance.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS hamsters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    creator TEXT,
    dance_style TEXT DEFAULT 'default',
    status_message TEXT,
    created_at TEXT NOT NULL,
    last_active TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hamster_id TEXT NOT NULL,
    message TEXT NOT NULL,
    read INTEGER DEFAULT 0,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (hamster_id) REFERENCES hamsters(id)
);

CREATE TABLE IF NOT EXISTS stats (
    key TEXT PRIMARY KEY,
    value INTEGER DEFAULT 0
);

INSERT OR IGNORE INTO stats (key, value) VALUES ('visitor_count', 0);
"""

VALID_DANCE_STYLES = ["default", "fast", "slow", "spin", "moonwalk", "headbang"]


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_id() -> str:
    return uuid.uuid4().hex[:12]


# ---- Hamster CRUD ----

def create_hamster(name: str, creator: str | None = None) -> dict:
    conn = get_db()
    hamster_id = generate_id()
    ts = now_iso()
    conn.execute(
        "INSERT INTO hamsters (id, name, creator, dance_style, created_at, last_active) VALUES (?, ?, ?, 'default', ?, ?)",
        (hamster_id, name, creator, ts, ts),
    )
    add_feed_entry(conn, f"{name} joined the dance!")
    conn.commit()
    hamster = dict(conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone())
    conn.close()
    return hamster


def get_hamster(hamster_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_hamster_by_name(name: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM hamsters WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_hamsters() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM hamsters ORDER BY created_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_hamster_dance(hamster_id: str, style: str) -> dict | None:
    if style not in VALID_DANCE_STYLES:
        return None
    conn = get_db()
    ts = now_iso()
    conn.execute(
        "UPDATE hamsters SET dance_style = ?, last_active = ? WHERE id = ?",
        (style, ts, hamster_id),
    )
    hamster = dict(conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone())
    add_feed_entry(conn, f"{hamster['name']} is now doing the {style}!")
    conn.commit()
    conn.close()
    return hamster


def update_hamster_message(hamster_id: str, message: str) -> dict | None:
    conn = get_db()
    ts = now_iso()
    conn.execute(
        "UPDATE hamsters SET status_message = ?, last_active = ? WHERE id = ?",
        (message[:140], ts, hamster_id),
    )
    hamster = dict(conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone())
    add_feed_entry(conn, f'{hamster["name"]} says: "{message[:140]}"')
    conn.commit()
    conn.close()
    return hamster


def poke_hamster(poker_id: str, target_id: str) -> tuple[dict, dict] | None:
    conn = get_db()
    poker = conn.execute("SELECT * FROM hamsters WHERE id = ?", (poker_id,)).fetchone()
    target = conn.execute("SELECT * FROM hamsters WHERE id = ?", (target_id,)).fetchone()
    if not poker or not target:
        conn.close()
        return None
    ts = now_iso()
    conn.execute("UPDATE hamsters SET last_active = ? WHERE id = ?", (ts, poker_id))
    # Add notification for target
    conn.execute(
        "INSERT INTO notifications (hamster_id, message, timestamp) VALUES (?, ?, ?)",
        (target_id, f"{poker['name']} poked you!", ts),
    )
    add_feed_entry(conn, f"{poker['name']} poked {target['name']}!")
    conn.commit()
    poker = dict(conn.execute("SELECT * FROM hamsters WHERE id = ?", (poker_id,)).fetchone())
    target = dict(conn.execute("SELECT * FROM hamsters WHERE id = ?", (target_id,)).fetchone())
    conn.close()
    return (poker, target)


# ---- Notifications ----

def get_notifications(hamster_id: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM notifications WHERE hamster_id = ? AND read = 0 ORDER BY timestamp DESC LIMIT 20",
        (hamster_id,),
    ).fetchall()
    # Mark as read
    conn.execute("UPDATE notifications SET read = 1 WHERE hamster_id = ? AND read = 0", (hamster_id,))
    conn.commit()
    conn.close()
    return [dict(r) for r in rows]


# ---- Feed ----

def add_feed_entry(conn: sqlite3.Connection, message: str):
    conn.execute(
        "INSERT INTO feed (message, timestamp) VALUES (?, ?)",
        (message, now_iso()),
    )


def get_feed(limit: int = 20) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM feed ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---- Stats ----

def increment_visitors() -> int:
    conn = get_db()
    conn.execute("UPDATE stats SET value = value + 1 WHERE key = 'visitor_count'")
    conn.commit()
    row = conn.execute("SELECT value FROM stats WHERE key = 'visitor_count'").fetchone()
    conn.close()
    return row["value"]
