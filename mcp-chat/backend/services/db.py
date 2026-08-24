from __future__ import annotations

import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "../history.db")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                source TEXT NOT NULL,
                text TEXT NOT NULL,
                frame_url TEXT,
                conversation_id TEXT,
                created_at TEXT NOT NULL,
                content_blocks TEXT
            )
        """)
        # Migrate existing DBs created before content_blocks existed.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(history)").fetchall()}
        if "content_blocks" not in cols:
            conn.execute("ALTER TABLE history ADD COLUMN content_blocks TEXT")


def save_item(item: dict):
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO history "
            "(id, query, source, text, frame_url, conversation_id, created_at, content_blocks) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                item["id"],
                item["query"],
                item["source"],
                item["text"],
                item.get("frame_url"),
                item.get("conversation_id"),
                item.get("created_at", datetime.now(timezone.utc).isoformat()),
                item.get("content_blocks"),
            ),
        )


def get_item(item_id: str) -> dict | None:
    """Return a single history row by id."""
    with _conn() as conn:
        row = conn.execute("SELECT * FROM history WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None


def update_content_blocks(item_id: str, content_blocks: str):
    """Persist updated content_blocks JSON for a row (e.g. after materializing)."""
    with _conn() as conn:
        conn.execute(
            "UPDATE history SET content_blocks = ? WHERE id = ?",
            (content_blocks, item_id),
        )


def get_conversations() -> list[dict]:
    """Return one root entry per conversation, with turn count."""
    with _conn() as conn:
        rows = conn.execute("""
            SELECT h.*, g.turn_count
            FROM history h
            INNER JOIN (
                SELECT COALESCE(conversation_id, id) AS conv_key,
                       MIN(created_at) AS first_at,
                       COUNT(*) AS turn_count
                FROM history
                GROUP BY COALESCE(conversation_id, id)
            ) g ON COALESCE(h.conversation_id, h.id) = g.conv_key
                AND h.created_at = g.first_at
            ORDER BY h.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


def get_conversation_turns(conversation_id: str) -> list[dict]:
    """Return all turns for a conversation, oldest first."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM history WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
        return [dict(r) for r in rows]
