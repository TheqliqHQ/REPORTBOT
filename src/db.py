"""
SQLite database helpers.
- Creates tables if missing.
- Auto-migrates missing columns on existing DBs.
- Tiny query helper `q` to execute SQL with parameters.
"""
import os
from pathlib import Path
import sqlite3
from pathlib import Path
from typing import Iterable, Any

# Database file lives at project/src/../bot.db
DB_PATH = Path(os.getenv("BOT_DB_PATH") or (Path(__file__).resolve().parent.parent / "bot.db"))


def connect() -> sqlite3.Connection:
    """
    Create a SQLite connection with row_factory returning dict-like rows.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    """
    Idempotent migration: add a column if it doesn't already exist.
    """
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = {row["name"] for row in cur.fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        conn.commit()


def init_db() -> None:
    """
    Initialize database schema if not present and apply lightweight migrations.
    """
    conn = connect()
    cur = conn.cursor()
    cur.executescript(
        """
        PRAGMA journal_mode = WAL;

        -- Telegram users that interacted with the bot
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id    INTEGER UNIQUE,   -- telegram user id
            boss_chat_id  INTEGER,          -- optional boss chat override
            tz            TEXT,             -- optional timezone override
            created_at    TEXT              -- when the user first interacted
            -- (boss_thread_id / updated_at are added via migration below)
        );

        -- Per-user ordered list of usernames to enforce when sending
        CREATE TABLE IF NOT EXISTS username_orders (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id     INTEGER UNIQUE,
            usernames_json TEXT,           -- JSON array of strings
            updated_at     TEXT
        );

        -- A session groups multiple screenshots (one per day)
        CREATE TABLE IF NOT EXISTS sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id INTEGER,
            date_str   TEXT,               -- DD/MM/YYYY
            status     TEXT,               -- 'open' | 'closed'
            created_at TEXT,
            closed_at  TEXT
        );

        -- One row per uploaded image
        CREATE TABLE IF NOT EXISTS items (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id           INTEGER,
            order_index          INTEGER,   -- 1-based index in the order list
            username             TEXT,
            followers_raw        TEXT,      -- raw OCR string
            followers_normalized TEXT,      -- normalized "80,200" style
            image_file_id        TEXT,      -- Telegram file id to re-send
            ocr_confidence       REAL,      -- 0..1
            corrected            INTEGER,   -- 0/1 flag if user edited
            created_at           TEXT
        );
        """
    )
    conn.commit()

    # ---- Lightweight migrations (safe to run every start) ----
    # Needed for posting into a specific forum topic (e.g., "Work Proof")
    _add_column_if_missing(conn, "users", "boss_thread_id", "INTEGER")
    # Commands like /set_boss_here and /set_topic_here update this
    _add_column_if_missing(conn, "users", "updated_at", "TEXT")

    conn.close()


def q(conn: sqlite3.Connection, sql: str, params: Iterable[Any] | None = None) -> sqlite3.Cursor:
    """
    Execute a parameterized SQL query and return the cursor.
    """
    cur = conn.cursor()
    cur.execute(sql, tuple(params or []))
    return cur
