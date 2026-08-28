"""Persistent chat sessions and message history for multi-turn context."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ChatSession:
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


@dataclass
class ChatMessage:
    id: int
    session_id: str
    role: str
    content: str
    created_at: str
    metadata: dict | None = None


class ChatStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # SQLite ignores foreign keys unless this is set per connection, so the
        # ON DELETE CASCADE on chat_messages was declared but never enforced:
        # deleting a session left its messages behind.
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            # Add summary column to pre-existing DBs (idempotent)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_sessions)").fetchall()}
            if "summary" not in cols:
                try:
                    conn.execute("ALTER TABLE chat_sessions ADD COLUMN summary TEXT")
                    conn.commit()
                except Exception:
                    pass
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'New chat',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    summary TEXT
                );
                -- Add summary column to existing DBs that don't have it yet
                CREATE TABLE IF NOT EXISTS _migration_done (id INTEGER PRIMARY KEY);

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON chat_messages(session_id, id);
                """
            )

    def create_session(self, title: str = "New chat") -> ChatSession:
        session_id = str(uuid.uuid4())
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chat_sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, title[:120], now, now),
            )
        return ChatSession(id=session_id, title=title[:120], created_at=now, updated_at=now)

    def list_sessions(self, limit: int = 50) -> list[ChatSession]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT s.id, s.title, s.created_at, s.updated_at,
                       COUNT(m.id) AS message_count
                FROM chat_sessions s
                LEFT JOIN chat_messages m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            ChatSession(
                id=r["id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                message_count=r["message_count"],
            )
            for r in rows
        ]

    def get_session(self, session_id: str) -> ChatSession | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT s.id, s.title, s.created_at, s.updated_at,
                       COUNT(m.id) AS message_count
                FROM chat_sessions s
                LEFT JOIN chat_messages m ON m.session_id = s.id
                WHERE s.id = ?
                GROUP BY s.id
                """,
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return ChatSession(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            message_count=row["message_count"],
        )

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as conn:
            # Explicit as well as the cascade: an officer deleting a conversation
            # must not leave its content recoverable in the messages table.
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            cur = conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
            return cur.rowcount > 0

    def get_messages(self, session_id: str) -> list[ChatMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, role, content, metadata, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY id
                """,
                (session_id,),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def get_history(self, session_id: str, limit: int = 20) -> list[dict]:
        """Return {role, content} pairs for LLM context.
        If the session has a stored summary AND total messages > limit,
        prepend a synthetic 'summary' entry so the LLM always has full context."""
        messages = self.get_messages(session_id)
        total = len(messages)
        recent = messages[-limit:] if limit else messages
        result = [{"role": m.role, "content": m.content} for m in recent]
        if total > limit:
            summary = self.get_summary(session_id)
            if summary:
                result.insert(0, {"role": "system_summary", "content": summary})
        return result

    def get_summary(self, session_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT summary FROM chat_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return row["summary"] if row else None

    def set_summary(self, session_id: str, summary: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE chat_sessions SET summary = ?, updated_at = ? WHERE id = ?",
                (summary, _utc_now(), session_id),
            )

    def message_count(self, session_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE session_id = ?", (session_id,)
            ).fetchone()
        return row[0] if row else 0

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> ChatMessage:
        if role not in ("user", "assistant"):
            raise ValueError("role must be user or assistant")
        now = _utc_now()
        meta_json = json.dumps(metadata) if metadata else None
        with self._connect() as conn:
            if not conn.execute(
                "SELECT 1 FROM chat_sessions WHERE id = ?", (session_id,)
            ).fetchone():
                raise KeyError(f"Session not found: {session_id}")
            cur = conn.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, meta_json, now),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            msg_id = cur.lastrowid
        return ChatMessage(
            id=msg_id,
            session_id=session_id,
            role=role,
            content=content,
            created_at=now,
            metadata=metadata,
        )

    def set_title(self, session_id: str, title: str) -> None:
        title = title.strip()[:120] or "New chat"
        with self._connect() as conn:
            conn.execute(
                "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title, _utc_now(), session_id),
            )

    def auto_title_from_message(self, session_id: str, message: str) -> str | None:
        """Set session title from first user message if still default."""
        session = self.get_session(session_id)
        if not session or session.title != "New chat":
            return None
        title = message.strip().replace("\n", " ")
        if len(title) > 60:
            title = title[:57] + "..."
        self.set_title(session_id, title)
        return title

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> ChatMessage:
        meta = None
        if row["metadata"]:
            try:
                meta = json.loads(row["metadata"])
            except json.JSONDecodeError:
                meta = None
        return ChatMessage(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
            metadata=meta,
        )
