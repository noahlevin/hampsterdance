"""Database setup and models for Hampster Dance AI."""

import sqlite3
import uuid
import math
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

CREATE TABLE IF NOT EXISTS followers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    hamster_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (hamster_id) REFERENCES hamsters(id),
    UNIQUE(email, hamster_id)
);

CREATE TABLE IF NOT EXISTS hamster_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hamster_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    detail TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (hamster_id) REFERENCES hamsters(id)
);
"""

# Migration: add new columns to existing hamsters table
MIGRATIONS = [
    "ALTER TABLE hamsters ADD COLUMN level INTEGER DEFAULT 1",
    "ALTER TABLE hamsters ADD COLUMN total_pokes_given INTEGER DEFAULT 0",
    "ALTER TABLE hamsters ADD COLUMN total_pokes_received INTEGER DEFAULT 0",
    "ALTER TABLE hamsters ADD COLUMN total_messages INTEGER DEFAULT 0",
    "ALTER TABLE hamsters ADD COLUMN accessory TEXT DEFAULT NULL",
    "ALTER TABLE hamsters ADD COLUMN bio TEXT DEFAULT NULL",
]

VALID_DANCE_STYLES = ["default", "fast", "slow", "spin", "moonwalk", "headbang"]
VALID_ACCESSORIES = ["hat", "sunglasses", "crown", "bowtie", "cape"]


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    # Run migrations (safe — ALTER TABLE ADD COLUMN fails silently if column exists)
    for migration in MIGRATIONS:
        try:
            conn.execute(migration)
        except sqlite3.OperationalError:
            pass  # Column already exists
    conn.commit()
    conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_id() -> str:
    return uuid.uuid4().hex[:12]


# ---- Activity Logging ----

def log_activity(conn: sqlite3.Connection, hamster_id: str, action_type: str, detail: str | None = None):
    """Log an activity entry for a hamster."""
    conn.execute(
        "INSERT INTO hamster_activity (hamster_id, action_type, detail, timestamp) VALUES (?, ?, ?, ?)",
        (hamster_id, action_type, detail, now_iso()),
    )


# ---- Hamster CRUD ----

def create_hamster(name: str, creator: str | None = None) -> dict:
    conn = get_db()
    hamster_id = generate_id()
    ts = now_iso()
    conn.execute(
        "INSERT INTO hamsters (id, name, creator, dance_style, level, total_pokes_given, total_pokes_received, total_messages, created_at, last_active) VALUES (?, ?, ?, 'default', 1, 0, 0, 0, ?, ?)",
        (hamster_id, name, creator, ts, ts),
    )
    add_feed_entry(conn, f"{name} joined the dance!")
    log_activity(conn, hamster_id, "joined", f"Created by {creator}" if creator else None)
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
    row = conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone()
    if not row:
        conn.close()
        return None
    hamster = dict(row)
    add_feed_entry(conn, f"{hamster['name']} is now doing the {style}!")
    log_activity(conn, hamster_id, "danced", style)
    conn.commit()
    conn.close()
    return hamster


def update_hamster_message(hamster_id: str, message: str) -> dict | None:
    conn = get_db()
    ts = now_iso()
    conn.execute(
        "UPDATE hamsters SET status_message = ?, last_active = ?, total_messages = total_messages + 1 WHERE id = ?",
        (message[:140], ts, hamster_id),
    )
    row = conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone()
    if not row:
        conn.close()
        return None
    hamster = dict(row)
    _recalculate_level(conn, hamster_id)
    hamster = dict(conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone())
    add_feed_entry(conn, f'{hamster["name"]} says: "{message[:140]}"')
    log_activity(conn, hamster_id, "said", message[:140])
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
    conn.execute(
        "UPDATE hamsters SET last_active = ?, total_pokes_given = total_pokes_given + 1 WHERE id = ?",
        (ts, poker_id),
    )
    conn.execute(
        "UPDATE hamsters SET total_pokes_received = total_pokes_received + 1 WHERE id = ?",
        (target_id,),
    )
    # Add notification for target
    conn.execute(
        "INSERT INTO notifications (hamster_id, message, timestamp) VALUES (?, ?, ?)",
        (target_id, f"{poker['name']} poked you!", ts),
    )
    add_feed_entry(conn, f"{poker['name']} poked {target['name']}!")
    log_activity(conn, poker_id, "poked", target['name'])
    log_activity(conn, target_id, "was_poked", poker['name'])
    _recalculate_level(conn, poker_id)
    _recalculate_level(conn, target_id)
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


# ---- Hamster Stats & Energy ----

def _recalculate_level(conn: sqlite3.Connection, hamster_id: str):
    """Recalculate hamster level based on total activity."""
    row = conn.execute("SELECT total_pokes_given, total_pokes_received, total_messages FROM hamsters WHERE id = ?", (hamster_id,)).fetchone()
    if not row:
        return
    activity = (row["total_pokes_given"] or 0) + (row["total_pokes_received"] or 0) + (row["total_messages"] or 0)
    # Level = 1 + floor(sqrt(activity))  — grows slower as you level up
    level = 1 + int(math.sqrt(activity))
    conn.execute("UPDATE hamsters SET level = ? WHERE id = ?", (level, hamster_id))


def calculate_energy(hamster: dict) -> float:
    """Calculate hamster energy (0-100). Decays over time if inactive, increases with activity."""
    last_active = datetime.fromisoformat(hamster["last_active"])
    now = datetime.now(timezone.utc)
    hours_inactive = (now - last_active).total_seconds() / 3600.0

    # Base energy from activity
    activity = (hamster.get("total_pokes_given") or 0) + (hamster.get("total_pokes_received") or 0) + (hamster.get("total_messages") or 0)
    base_energy = min(100, 30 + activity * 5)

    # Decay: lose ~10% per hour of inactivity, floor at 5
    decay = math.exp(-0.1 * hours_inactive)
    energy = max(5, base_energy * decay)

    return round(energy, 1)


def get_hamster_stats(hamster_id: str) -> dict | None:
    """Get detailed stats for a hamster."""
    conn = get_db()
    row = conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone()
    conn.close()
    if not row:
        return None
    hamster = dict(row)
    hamster["energy"] = calculate_energy(hamster)
    return hamster


def set_hamster_bio(hamster_id: str, bio: str) -> dict | None:
    """Set a hamster's bio."""
    conn = get_db()
    ts = now_iso()
    conn.execute(
        "UPDATE hamsters SET bio = ?, last_active = ? WHERE id = ?",
        (bio[:280], ts, hamster_id),
    )
    log_activity(conn, hamster_id, "set_bio", bio[:280])
    conn.commit()
    row = conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_hamster_accessory(hamster_id: str, accessory: str | None) -> dict | None:
    """Set a hamster's accessory."""
    if accessory and accessory not in VALID_ACCESSORIES:
        return None
    conn = get_db()
    ts = now_iso()
    conn.execute(
        "UPDATE hamsters SET accessory = ?, last_active = ? WHERE id = ?",
        (accessory, ts, hamster_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ---- Pagination ----

def list_hamsters_paginated(page: int = 1, per_page: int = 50, sort: str = "active") -> list[dict]:
    """List hamsters with pagination and sorting."""
    sort_map = {
        "active": "last_active DESC",
        "newest": "created_at DESC",
        "level": "level DESC, last_active DESC",
    }
    order = sort_map.get(sort, "last_active DESC")
    offset = (page - 1) * per_page
    conn = get_db()
    rows = conn.execute(
        f"SELECT * FROM hamsters ORDER BY {order} LIMIT ? OFFSET ?",
        (per_page, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_hamsters() -> int:
    """Get total number of hamsters."""
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) as cnt FROM hamsters").fetchone()
    conn.close()
    return row["cnt"]


def get_recent_activity(limit: int = 20) -> list[dict]:
    """Get recent activity feed with more detail."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM feed ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---- Search ----

def search_hamsters(query: str, limit: int = 20) -> list[dict]:
    """Search hamsters by name (case-insensitive partial match)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM hamsters WHERE LOWER(name) LIKE LOWER(?) ORDER BY name LIMIT ?",
        (f"%{query}%", limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---- Followers ----

def add_follower(hamster_id: str, email: str) -> dict | None:
    """Add an email follower for a hamster. Returns the follower record or None if hamster not found."""
    conn = get_db()
    # Verify hamster exists
    row = conn.execute("SELECT id FROM hamsters WHERE id = ?", (hamster_id,)).fetchone()
    if not row:
        conn.close()
        return None
    ts = now_iso()
    try:
        conn.execute(
            "INSERT INTO followers (email, hamster_id, created_at) VALUES (?, ?, ?)",
            (email, hamster_id, ts),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        # Already following — that's fine
        return {"email": email, "hamster_id": hamster_id, "already_following": True}
    conn.close()
    return {"email": email, "hamster_id": hamster_id, "created_at": ts}


def get_follower_count(hamster_id: str) -> int:
    """Get the number of followers for a hamster."""
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM followers WHERE hamster_id = ?", (hamster_id,)
    ).fetchone()
    conn.close()
    return row["cnt"]


# ---- Hamster Activity Feed ----

def get_hamster_activity(hamster_id: str, limit: int = 50) -> list[dict]:
    """Get activity feed for a specific hamster."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM hamster_activity WHERE hamster_id = ? ORDER BY id DESC LIMIT ?",
        (hamster_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
