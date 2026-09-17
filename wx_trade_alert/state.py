from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from .models import IncomingMessage, TradeSignal


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_wxid TEXT NOT NULL,
                    local_id INTEGER NOT NULL,
                    sort_seq INTEGER NOT NULL,
                    msg_type TEXT NOT NULL,
                    sender_username TEXT NOT NULL,
                    create_time REAL NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(chat_wxid, local_id, sort_seq)
                );
                CREATE INDEX IF NOT EXISTS ix_messages_status ON messages(status, id);
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL,
                    signal_json TEXT NOT NULL,
                    alerted INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(message_id) REFERENCES messages(id)
                );
                CREATE INDEX IF NOT EXISTS ix_signals_fingerprint ON signals(fingerprint, created_at);
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER NOT NULL,
                    success INTEGER NOT NULL,
                    detail TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(signal_id) REFERENCES signals(id)
                );
                CREATE TABLE IF NOT EXISTS context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )
            conn.execute("UPDATE messages SET status='pending' WHERE status='processing'")

    def enqueue(self, message: IncomingMessage) -> bool:
        now = time.time()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO messages
                (chat_wxid, local_id, sort_seq, msg_type, sender_username, create_time,
                 content, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (
                    message.chat_wxid,
                    message.local_id,
                    message.sort_seq,
                    message.msg_type,
                    message.sender_username,
                    message.create_time,
                    message.content,
                    now,
                    now,
                ),
            )
            return cur.rowcount == 1

    def claim_next(self) -> sqlite3.Row | None:
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM messages WHERE status='pending' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE messages SET status='processing', attempts=attempts+1, updated_at=? WHERE id=?",
                (time.time(), row["id"]),
            )
            return row

    def mark_done(self, message_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE messages SET status='done', error='', updated_at=? WHERE id=?",
                (time.time(), message_id),
            )

    def mark_failed(self, message_id: int, error: str, retry: bool = False) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE messages SET status=?, error=?, updated_at=? WHERE id=?",
                ("pending" if retry else "failed", error[:1000], time.time(), message_id),
            )

    def add_context(self, text: str, keep: int, created_at: float | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO context(text, created_at) VALUES (?, ?)",
                (text, created_at if created_at is not None else time.time()),
            )
            conn.execute(
                "DELETE FROM context WHERE id NOT IN (SELECT id FROM context ORDER BY id DESC LIMIT ?)",
                (keep,),
            )

    def get_context(self, limit: int, max_age_seconds: int | None = None) -> list[str]:
        cutoff = 0.0 if max_age_seconds is None else time.time() - max_age_seconds
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT text FROM context WHERE created_at>=? ORDER BY id DESC LIMIT ?",
                (cutoff, limit),
            ).fetchall()
        return [row["text"] for row in reversed(rows)]

    def record_signal(self, message_id: int, signal: TradeSignal) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO signals(message_id, fingerprint, signal_json, created_at) VALUES (?, ?, ?, ?)",
                (message_id, signal.fingerprint(), signal.to_json(), time.time()),
            )
            return int(cur.lastrowid)

    def is_duplicate(self, fingerprint: str, within_seconds: int) -> bool:
        cutoff = time.time() - within_seconds
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM signals WHERE fingerprint=? AND alerted=1 AND created_at>=? LIMIT 1",
                (fingerprint, cutoff),
            ).fetchone()
        return row is not None

    def mark_alerted(self, signal_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE signals SET alerted=1 WHERE id=?", (signal_id,))

    def calls_in_last_hour(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM calls WHERE created_at>=?",
                (time.time() - 3600,),
            ).fetchone()
        return int(row["n"])

    def record_call(self, signal_id: int, success: bool, detail: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO calls(signal_id, success, detail, created_at) VALUES (?, ?, ?, ?)",
                (signal_id, int(success), detail[:1000], time.time()),
            )

    def status_counts(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT status, COUNT(*) n FROM messages GROUP BY status").fetchall()
        return {row["status"]: int(row["n"]) for row in rows}
