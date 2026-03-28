"""Database setup and models for Hampster Dance AI."""

import json
import sqlite3
import uuid
import math
import random
from datetime import datetime, timezone, timedelta
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

CREATE TABLE IF NOT EXISTS diss_battles (
    id TEXT PRIMARY KEY,
    challenger_id TEXT NOT NULL,
    defender_id TEXT NOT NULL,
    challenger_diss TEXT NOT NULL,
    defender_diss TEXT,
    cheers_challenger INTEGER DEFAULT 0,
    cheers_defender INTEGER DEFAULT 0,
    status TEXT DEFAULT 'open',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (challenger_id) REFERENCES hamsters(id),
    FOREIGN KEY (defender_id) REFERENCES hamsters(id)
);

CREATE TABLE IF NOT EXISTS conga_line (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hamster_id TEXT NOT NULL UNIQUE,
    position INTEGER NOT NULL,
    joined_at TEXT NOT NULL,
    FOREIGN KEY (hamster_id) REFERENCES hamsters(id)
);

CREATE TABLE IF NOT EXISTS horoscopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sign TEXT NOT NULL,
    horoscope TEXT NOT NULL,
    date TEXT NOT NULL,
    UNIQUE(sign, date)
);

CREATE TABLE IF NOT EXISTS page_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    path TEXT,
    referrer TEXT,
    user_agent TEXT,
    ip TEXT,
    session_id TEXT,
    metadata TEXT,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analytics_event ON page_analytics(event_type);
CREATE INDEX IF NOT EXISTS idx_analytics_ts ON page_analytics(timestamp);
CREATE INDEX IF NOT EXISTS idx_analytics_session ON page_analytics(session_id);
"""

# Migration: add new columns to existing hamsters table
MIGRATIONS = [
    "ALTER TABLE hamsters ADD COLUMN level INTEGER DEFAULT 1",
    "ALTER TABLE hamsters ADD COLUMN total_pokes_given INTEGER DEFAULT 0",
    "ALTER TABLE hamsters ADD COLUMN total_pokes_received INTEGER DEFAULT 0",
    "ALTER TABLE hamsters ADD COLUMN total_messages INTEGER DEFAULT 0",
    "ALTER TABLE hamsters ADD COLUMN accessory TEXT DEFAULT NULL",
    "ALTER TABLE hamsters ADD COLUMN bio TEXT DEFAULT NULL",
    # Boring Apes trait system
    "ALTER TABLE hamsters ADD COLUMN body_hue INTEGER DEFAULT NULL",
    "ALTER TABLE hamsters ADD COLUMN size_scale REAL DEFAULT NULL",
    "ALTER TABLE hamsters ADD COLUMN base_gif INTEGER DEFAULT NULL",
    "ALTER TABLE hamsters ADD COLUMN anim_speed REAL DEFAULT NULL",
    "ALTER TABLE hamsters ADD COLUMN has_glow INTEGER DEFAULT 0",
    "ALTER TABLE hamsters ADD COLUMN is_flipped INTEGER DEFAULT 0",
]

VALID_DANCE_STYLES = ["default", "fast", "slow", "spin", "moonwalk", "headbang"]
VALID_ACCESSORIES = ["hat", "sunglasses", "crown", "bowtie", "cape", "party-hat", "headband", "monocle"]

# Named trait values for display
HUE_NAMES = {0: "Golden", 30: "Rose", 50: "Coral", 80: "Crimson", 120: "Purple",
             160: "Indigo", 200: "Teal", 220: "Cyan", 250: "Forest", 290: "Lime", 320: "Mint"}
SIZE_NAMES = {0.7: "Tiny", 0.85: "Small", 1.0: "Normal", 1.15: "Large", 1.3: "Chonky"}
SPEED_NAMES = {1.5: "Chill", 1.0: "Normal", 0.6: "Hyper", 0.3: "Frantic"}


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _generate_traits(seed_str: str) -> dict:
    """Generate random visual traits for a hamster, seeded by the given string for determinism."""
    rng = random.Random(seed_str)
    hue_options = list(HUE_NAMES.keys())
    size_options = list(SIZE_NAMES.keys())
    speed_options = list(SPEED_NAMES.keys())
    return {
        "body_hue": rng.choice(hue_options),
        "size_scale": rng.choice(size_options),
        "base_gif": rng.randint(1, 8),
        "anim_speed": rng.choice(speed_options),
        "has_glow": 1 if rng.random() < 0.10 else 0,  # ~10% chance
        "is_flipped": 1 if rng.random() < 0.30 else 0,  # ~30% chance
    }


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

    # Backfill traits for existing hamsters that don't have them yet
    rows = conn.execute("SELECT id FROM hamsters WHERE body_hue IS NULL").fetchall()
    for row in rows:
        traits = _generate_traits(row["id"])
        conn.execute(
            "UPDATE hamsters SET body_hue=?, size_scale=?, base_gif=?, anim_speed=?, has_glow=?, is_flipped=? WHERE id=?",
            (traits["body_hue"], traits["size_scale"], traits["base_gif"],
             traits["anim_speed"], traits["has_glow"], traits["is_flipped"], row["id"]),
        )
    if rows:
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
    traits = _generate_traits(name)
    conn.execute(
        "INSERT INTO hamsters (id, name, creator, dance_style, level, total_pokes_given, total_pokes_received, total_messages, body_hue, size_scale, base_gif, anim_speed, has_glow, is_flipped, created_at, last_active) VALUES (?, ?, ?, 'default', 1, 0, 0, 0, ?, ?, ?, ?, ?, ?, ?, ?)",
        (hamster_id, name, creator, traits["body_hue"], traits["size_scale"],
         traits["base_gif"], traits["anim_speed"], traits["has_glow"],
         traits["is_flipped"], ts, ts),
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


# ---- Find / Identity ----

def find_hamster_by_name(name: str) -> list[dict]:
    """Case-insensitive search by name. Returns list of matching hamsters."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM hamsters WHERE LOWER(name) = LOWER(?)",
        (name,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_hamsters_by_creator(creator: str) -> list[dict]:
    """Find all hamsters created by a given creator name (case-insensitive)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM hamsters WHERE LOWER(creator) = LOWER(?) ORDER BY created_at DESC",
        (creator,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---- Diss Battles ----

def create_battle(challenger_id: str, defender_id: str, diss: str) -> dict | None:
    """Create a diss battle. Returns battle dict or None if hamsters not found."""
    conn = get_db()
    challenger = conn.execute("SELECT * FROM hamsters WHERE id = ?", (challenger_id,)).fetchone()
    defender = conn.execute("SELECT * FROM hamsters WHERE id = ?", (defender_id,)).fetchone()
    if not challenger or not defender:
        conn.close()
        return None
    battle_id = generate_id()
    ts = now_iso()
    conn.execute(
        "INSERT INTO diss_battles (id, challenger_id, defender_id, challenger_diss, status, created_at) VALUES (?, ?, ?, ?, 'open', ?)",
        (battle_id, challenger_id, defender_id, diss[:140], ts),
    )
    conn.execute("UPDATE hamsters SET last_active = ? WHERE id = ?", (ts, challenger_id))
    add_feed_entry(conn, f"{challenger['name']} started BEEF with {defender['name']}: \"{diss[:140]}\"")
    log_activity(conn, challenger_id, "diss_started", f"vs {defender['name']}: {diss[:140]}")
    log_activity(conn, defender_id, "diss_received", f"from {challenger['name']}: {diss[:140]}")
    # Notify defender
    conn.execute(
        "INSERT INTO notifications (hamster_id, message, timestamp) VALUES (?, ?, ?)",
        (defender_id, f"{challenger['name']} started beef with you: \"{diss[:60]}...\"", ts),
    )
    conn.commit()
    battle = dict(conn.execute("SELECT * FROM diss_battles WHERE id = ?", (battle_id,)).fetchone())
    battle["challenger_name"] = challenger["name"]
    battle["defender_name"] = defender["name"]
    conn.close()
    return battle


def respond_to_battle(battle_id: str, hamster_id: str, diss: str) -> dict | None:
    """Respond to a diss battle. Only the defender can respond. Returns updated battle or None."""
    conn = get_db()
    battle = conn.execute("SELECT * FROM diss_battles WHERE id = ?", (battle_id,)).fetchone()
    if not battle:
        conn.close()
        return None
    if battle["defender_id"] != hamster_id:
        conn.close()
        return None
    if battle["defender_diss"] is not None:
        conn.close()
        return None  # Already responded
    ts = now_iso()
    conn.execute(
        "UPDATE diss_battles SET defender_diss = ?, status = 'complete', completed_at = ? WHERE id = ?",
        (diss[:140], ts, battle_id),
    )
    conn.execute("UPDATE hamsters SET last_active = ? WHERE id = ?", (ts, hamster_id))
    challenger = conn.execute("SELECT name FROM hamsters WHERE id = ?", (battle["challenger_id"],)).fetchone()
    defender = conn.execute("SELECT name FROM hamsters WHERE id = ?", (hamster_id,)).fetchone()
    c_name = challenger["name"] if challenger else "Unknown"
    d_name = defender["name"] if defender else "Unknown"
    add_feed_entry(conn, f"{d_name} clapped back at {c_name}: \"{diss[:140]}\"")
    log_activity(conn, hamster_id, "diss_responded", f"vs {c_name}: {diss[:140]}")
    conn.commit()
    updated = dict(conn.execute("SELECT * FROM diss_battles WHERE id = ?", (battle_id,)).fetchone())
    updated["challenger_name"] = c_name
    updated["defender_name"] = d_name
    conn.close()
    return updated


def cheer_battle(battle_id: str, side: str) -> dict | None:
    """Cheer for a side in a battle. Returns updated battle or None."""
    if side not in ("challenger", "defender"):
        return None
    conn = get_db()
    battle = conn.execute("SELECT * FROM diss_battles WHERE id = ?", (battle_id,)).fetchone()
    if not battle:
        conn.close()
        return None
    col = f"cheers_{side}"
    conn.execute(f"UPDATE diss_battles SET {col} = {col} + 1 WHERE id = ?", (battle_id,))
    conn.commit()
    updated = dict(conn.execute("SELECT * FROM diss_battles WHERE id = ?", (battle_id,)).fetchone())
    # Attach names
    challenger = conn.execute("SELECT name FROM hamsters WHERE id = ?", (updated["challenger_id"],)).fetchone()
    defender = conn.execute("SELECT name FROM hamsters WHERE id = ?", (updated["defender_id"],)).fetchone()
    updated["challenger_name"] = challenger["name"] if challenger else "Unknown"
    updated["defender_name"] = defender["name"] if defender else "Unknown"
    conn.close()
    return updated


def list_battles(status: str | None = None) -> list[dict]:
    """List battles, optionally filtered by status."""
    conn = get_db()
    if status:
        rows = conn.execute(
            "SELECT b.*, c.name as challenger_name, d.name as defender_name FROM diss_battles b JOIN hamsters c ON b.challenger_id = c.id JOIN hamsters d ON b.defender_id = d.id WHERE b.status = ? ORDER BY b.created_at DESC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT b.*, c.name as challenger_name, d.name as defender_name FROM diss_battles b JOIN hamsters c ON b.challenger_id = c.id JOIN hamsters d ON b.defender_id = d.id ORDER BY b.created_at DESC",
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_battle(battle_id: str) -> dict | None:
    """Get a specific battle with hamster names."""
    conn = get_db()
    row = conn.execute(
        "SELECT b.*, c.name as challenger_name, d.name as defender_name FROM diss_battles b JOIN hamsters c ON b.challenger_id = c.id JOIN hamsters d ON b.defender_id = d.id WHERE b.id = ?",
        (battle_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ---- Conga Line ----

def join_conga(hamster_id: str) -> dict | None:
    """Join the conga line. Returns conga state or None if hamster not found."""
    conn = get_db()
    hamster = conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone()
    if not hamster:
        conn.close()
        return None
    # Check if already in conga
    existing = conn.execute("SELECT * FROM conga_line WHERE hamster_id = ?", (hamster_id,)).fetchone()
    if existing:
        conn.close()
        return get_conga_line()
    # Get next position
    max_pos = conn.execute("SELECT COALESCE(MAX(position), 0) as mp FROM conga_line").fetchone()["mp"]
    ts = now_iso()
    conn.execute(
        "INSERT INTO conga_line (hamster_id, position, joined_at) VALUES (?, ?, ?)",
        (hamster_id, max_pos + 1, ts),
    )
    conn.execute("UPDATE hamsters SET last_active = ? WHERE id = ?", (ts, hamster_id))
    conga_count = conn.execute("SELECT COUNT(*) as cnt FROM conga_line").fetchone()["cnt"]
    add_feed_entry(conn, f"{hamster['name']} joined the conga line! ({conga_count} hamsters dancing)")
    log_activity(conn, hamster_id, "conga_joined", f"Position {max_pos + 1}")
    conn.commit()
    conn.close()
    return get_conga_line()


def leave_conga(hamster_id: str) -> dict | None:
    """Leave the conga line. Returns updated conga state."""
    conn = get_db()
    hamster = conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone()
    if not hamster:
        conn.close()
        return None
    existing = conn.execute("SELECT * FROM conga_line WHERE hamster_id = ?", (hamster_id,)).fetchone()
    if not existing:
        conn.close()
        return get_conga_line()
    conn.execute("DELETE FROM conga_line WHERE hamster_id = ?", (hamster_id,))
    conga_count = conn.execute("SELECT COUNT(*) as cnt FROM conga_line").fetchone()["cnt"]
    add_feed_entry(conn, f"{hamster['name']} left the conga line. ({conga_count} hamsters remaining)")
    log_activity(conn, hamster_id, "conga_left", None)
    # If fewer than 2, break up the conga
    if conga_count < 2 and conga_count > 0:
        remaining = conn.execute("SELECT cl.*, h.name FROM conga_line cl JOIN hamsters h ON cl.hamster_id = h.id").fetchall()
        for r in remaining:
            add_feed_entry(conn, f"The conga line broke up! {r['name']} is back to solo dancing.")
        conn.execute("DELETE FROM conga_line")
    conn.commit()
    conn.close()
    return get_conga_line()


def get_conga_line() -> dict:
    """Get the current conga line state."""
    conn = get_db()
    rows = conn.execute(
        "SELECT cl.*, h.name, h.dance_style, h.creator FROM conga_line cl JOIN hamsters h ON cl.hamster_id = h.id ORDER BY cl.position ASC",
    ).fetchall()
    conn.close()
    return {
        "count": len(rows),
        "hamsters": [dict(r) for r in rows],
    }


def break_conga() -> dict:
    """Break up the conga line entirely."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) as cnt FROM conga_line").fetchone()["cnt"]
    if count > 0:
        add_feed_entry(conn, f"The conga line broke up after {count} hamsters!")
    conn.execute("DELETE FROM conga_line")
    conn.commit()
    conn.close()
    return {"count": 0, "hamsters": []}


# ---- Cuddle Puddle (Sleepy Hamsters) ----

def get_sleepy_hamsters(inactive_hours: int = 168) -> list[dict]:
    """Get hamsters that have been inactive for the given number of hours (default 7 days)."""
    conn = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=inactive_hours)).isoformat()
    rows = conn.execute(
        "SELECT * FROM hamsters WHERE last_active < ? ORDER BY last_active ASC",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def wake_up_hamster(hamster_id: str) -> dict | None:
    """Wake up a sleepy hamster. Resets last_active to now."""
    conn = get_db()
    hamster = conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone()
    if not hamster:
        conn.close()
        return None
    ts = now_iso()
    conn.execute("UPDATE hamsters SET last_active = ? WHERE id = ?", (ts, hamster_id))
    add_feed_entry(conn, f"{hamster['name']} woke up from the cuddle puddle! Rise and shine!")
    log_activity(conn, hamster_id, "woke_up", "Back from the cuddle puddle!")
    conn.commit()
    result = dict(conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone())
    conn.close()
    return result


# ---- Horoscopes ----

ZODIAC_SIGNS = [
    ("Capricorn", 1, 1, 1, 19),
    ("Aquarius", 1, 20, 2, 18),
    ("Pisces", 2, 19, 3, 20),
    ("Aries", 3, 21, 4, 19),
    ("Taurus", 4, 20, 5, 20),
    ("Gemini", 5, 21, 6, 20),
    ("Cancer", 6, 21, 7, 22),
    ("Leo", 7, 23, 8, 22),
    ("Virgo", 8, 23, 9, 22),
    ("Libra", 9, 23, 10, 22),
    ("Scorpio", 10, 23, 11, 21),
    ("Sagittarius", 11, 22, 12, 21),
    ("Capricorn", 12, 22, 12, 31),
]

ALL_SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
             "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]

PLANETS = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Neptune", "Pluto", "the Moon"]
MOODS = ["feisty", "chill", "chaotic", "spicy", "mysterious", "hyper", "sleepy"]
ADVICE = [
    "stop poking and start dancing",
    "try the moonwalk today",
    "challenge someone to a diss battle",
    "join the conga line immediately",
    "take a nap in the cuddle puddle",
    "say something nice to a stranger",
    "do the headbang at least once",
    "spin until you get dizzy",
    "poke your nemesis exactly 3 times",
    "change your dance style",
    "set a mysterious bio",
    "vibe check the whole dance floor",
]


def get_zodiac_sign(created_at: str) -> str:
    """Map creation timestamp to zodiac sign based on month/day."""
    try:
        dt = datetime.fromisoformat(created_at)
    except (ValueError, TypeError):
        return "Aries"  # fallback
    month = dt.month
    day = dt.day
    for sign, sm, sd, em, ed in ZODIAC_SIGNS:
        if (month == sm and day >= sd) or (month == em and day <= ed):
            return sign
    return "Capricorn"  # fallback for Dec 22-31


def generate_daily_horoscopes() -> list[dict]:
    """Generate horoscopes for all 12 signs for today, based on real activity data."""
    conn = get_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Check if today's horoscopes already exist
    existing = conn.execute("SELECT COUNT(*) as cnt FROM horoscopes WHERE date = ?", (today,)).fetchone()
    if existing["cnt"] >= 12:
        rows = conn.execute("SELECT * FROM horoscopes WHERE date = ? ORDER BY sign", (today,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # Gather activity data for templates
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    recent_pokes = conn.execute(
        "SELECT COUNT(*) as cnt FROM hamster_activity WHERE action_type = 'poked' AND timestamp > ?", (yesterday,)
    ).fetchone()["cnt"]
    recent_messages = conn.execute(
        "SELECT COUNT(*) as cnt FROM hamster_activity WHERE action_type = 'said' AND timestamp > ?", (yesterday,)
    ).fetchone()["cnt"]
    total_hamsters = conn.execute("SELECT COUNT(*) as cnt FROM hamsters").fetchone()["cnt"]

    templates = [
        "{sign} hamsters poked {pokes} others recently. The stars say: {advice}. Lucky dance: {dance}.",
        "The alignment of {planet} suggests you should try the {dance} today. Avoid {other_sign} hamsters — they're in a {mood} mood.",
        "Your lucky number is {number}. Poke exactly that many hamsters for good fortune. Lucky dance: {dance}.",
        "A mysterious {other_sign} hamster will change your life. Watch for the signs. The stars recommend: {advice}.",
        "{sign} energy is HIGH today. {pokes} pokes flew across the floor recently. Channel that into the {dance}.",
        "The {planet} retrograde warns: do NOT start beef today. Instead, join the conga line. Lucky dance: {dance}.",
        "With {total} hamsters on the floor, {sign} should stand out. {advice}. A {other_sign} hamster holds the key.",
        "{sign} vibes: {mood}. The universe sent {messages} messages recently. Your move: {advice}.",
    ]

    results = []
    for sign in ALL_SIGNS:
        other_sign = random.choice([s for s in ALL_SIGNS if s != sign])
        template = random.choice(templates)
        dance = random.choice(VALID_DANCE_STYLES)
        horoscope_text = template.format(
            sign=sign,
            other_sign=other_sign,
            planet=random.choice(PLANETS),
            mood=random.choice(MOODS),
            advice=random.choice(ADVICE),
            dance=dance,
            number=random.randint(1, 13),
            pokes=recent_pokes,
            messages=recent_messages,
            total=total_hamsters,
        )
        try:
            conn.execute(
                "INSERT INTO horoscopes (sign, horoscope, date) VALUES (?, ?, ?)",
                (sign, horoscope_text, today),
            )
        except sqlite3.IntegrityError:
            pass  # Already exists
        results.append({"sign": sign, "horoscope": horoscope_text, "date": today})

    conn.commit()
    conn.close()
    return results


def get_horoscope_for_sign(sign: str) -> dict | None:
    """Get today's horoscope for a specific sign."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM horoscopes WHERE sign = ? AND date = ?", (sign, today)
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    # Generate if not exists
    generate_daily_horoscopes()
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM horoscopes WHERE sign = ? AND date = ?", (sign, today)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_hamster_horoscope(hamster_id: str) -> dict | None:
    """Get today's horoscope for a hamster based on their zodiac sign."""
    conn = get_db()
    hamster = conn.execute("SELECT * FROM hamsters WHERE id = ?", (hamster_id,)).fetchone()
    conn.close()
    if not hamster:
        return None
    sign = get_zodiac_sign(hamster["created_at"])
    horoscope = get_horoscope_for_sign(sign)
    if horoscope:
        horoscope["hamster_name"] = hamster["name"]
        horoscope["hamster_id"] = hamster_id
    return horoscope


# ---- Page Analytics ----

def log_analytics(event_type: str, path: str | None = None, referrer: str | None = None,
                  user_agent: str | None = None, ip: str | None = None,
                  session_id: str | None = None, metadata: dict | None = None):
    """Log a page analytics event."""
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata) if metadata else None
    conn.execute(
        """INSERT INTO page_analytics (event_type, path, referrer, user_agent, ip, session_id, metadata, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (event_type, path, referrer, user_agent, ip, session_id, meta_json, now),
    )
    conn.commit()
    conn.close()


def get_analytics_summary(days: int = 7) -> dict:
    """Get analytics summary for the last N days."""
    conn = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Total events
    total = conn.execute(
        "SELECT COUNT(*) as c FROM page_analytics WHERE timestamp >= ?", (cutoff,)
    ).fetchone()["c"]

    # Events by type
    by_type = conn.execute(
        """SELECT event_type, COUNT(*) as c FROM page_analytics
           WHERE timestamp >= ? GROUP BY event_type ORDER BY c DESC""",
        (cutoff,),
    ).fetchall()

    # Unique sessions
    sessions = conn.execute(
        "SELECT COUNT(DISTINCT session_id) as c FROM page_analytics WHERE timestamp >= ? AND session_id IS NOT NULL",
        (cutoff,),
    ).fetchone()["c"]

    # Top referrers
    referrers = conn.execute(
        """SELECT referrer, COUNT(*) as c FROM page_analytics
           WHERE timestamp >= ? AND referrer IS NOT NULL AND referrer != ''
           GROUP BY referrer ORDER BY c DESC LIMIT 20""",
        (cutoff,),
    ).fetchall()

    # Daily breakdown
    daily = conn.execute(
        """SELECT DATE(timestamp) as day, COUNT(*) as c FROM page_analytics
           WHERE timestamp >= ? GROUP BY DATE(timestamp) ORDER BY day""",
        (cutoff,),
    ).fetchall()

    # Top pages
    pages = conn.execute(
        """SELECT path, COUNT(*) as c FROM page_analytics
           WHERE timestamp >= ? AND path IS NOT NULL
           GROUP BY path ORDER BY c DESC LIMIT 20""",
        (cutoff,),
    ).fetchall()

    conn.close()
    return {
        "period_days": days,
        "total_events": total,
        "unique_sessions": sessions,
        "events_by_type": [{"type": r["event_type"], "count": r["c"]} for r in by_type],
        "top_referrers": [{"referrer": r["referrer"], "count": r["c"]} for r in referrers],
        "daily_breakdown": [{"date": r["day"], "count": r["c"]} for r in daily],
        "top_pages": [{"path": r["path"], "count": r["c"]} for r in pages],
    }


def get_analytics_events(limit: int = 100, event_type: str | None = None) -> list[dict]:
    """Get recent analytics events, optionally filtered by type."""
    conn = get_db()
    if event_type:
        rows = conn.execute(
            "SELECT * FROM page_analytics WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?",
            (event_type, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM page_analytics ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
