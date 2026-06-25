from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .todo_models import TodoItem

TODO_STATUSES = {"open", "done", "canceled"}
TODO_QUERY_STATUSES = {*TODO_STATUSES, "all"}


class TodoRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize_schema()

    def initialize_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS todo_items (
                  id TEXT PRIMARY KEY,
                  title TEXT NOT NULL,
                  notes TEXT NOT NULL DEFAULT '',
                  status TEXT NOT NULL CHECK (status IN ('open', 'done', 'canceled')),
                  due_at TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_todo_items_status_updated_at
                ON todo_items(status, updated_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_todo_items_created_at
                ON todo_items(created_at DESC)
                """
            )

    def create_todo(
        self,
        *,
        title: str,
        notes: str | None = None,
        due_at: str | None = None,
    ) -> TodoItem:
        clean_title = self._required_text("title", title)
        clean_notes = self._optional_text(notes, default="")
        clean_due_at = self._optional_nullable_text(due_at)
        now = self._now()
        todo = TodoItem(
            id=f"todo_{uuid.uuid4().hex}",
            title=clean_title,
            notes=clean_notes,
            status="open",
            due_at=clean_due_at,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO todo_items (
                  id, title, notes, status, due_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    todo.id,
                    todo.title,
                    todo.notes,
                    todo.status,
                    todo.due_at,
                    todo.created_at,
                    todo.updated_at,
                ),
            )
        return todo

    def read_todo(self, todo_id: str) -> TodoItem | None:
        clean_id = self._required_text("todo_id", todo_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM todo_items WHERE id = ?",
                (clean_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_todo(row)

    def list_todos(
        self,
        *,
        query: str | None = None,
        status: str | None = "open",
        limit: int = 20,
    ) -> list[TodoItem]:
        clean_query = self._optional_nullable_text(query)
        clean_status = self.validate_query_status(status)
        safe_limit = self._safe_limit(limit, default=20)
        clauses: list[str] = []
        params: list[str | int] = []
        if clean_status != "all":
            clauses.append("status = ?")
            params.append(clean_status)
        if clean_query is not None:
            pattern = f"%{clean_query}%"
            clauses.append("(title LIKE ? OR notes LIKE ?)")
            params.extend([pattern, pattern])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM todo_items{where} ORDER BY updated_at DESC, created_at DESC LIMIT ?"
        params.append(safe_limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_todo(row) for row in rows]

    def update_todo(
        self,
        todo_id: str,
        *,
        title: str | None = None,
        notes: str | None = None,
        status: str | None = None,
        due_at: str | None = None,
        clear_due_at: bool = False,
    ) -> TodoItem | None:
        clean_id = self._required_text("todo_id", todo_id)
        current = self.read_todo(clean_id)
        if current is None:
            return None
        if title is None and notes is None and status is None and due_at is None and not clear_due_at:
            raise ValueError("at least one field must be provided")

        next_title = current.title if title is None else self._required_text("title", title)
        next_notes = current.notes if notes is None else self._optional_text(notes, default="")
        next_status = current.status if status is None else self.validate_status(status)
        next_due_at = None if clear_due_at else (current.due_at if due_at is None else self._optional_nullable_text(due_at))
        updated_at = self._now()

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE todo_items
                SET title = ?, notes = ?, status = ?, due_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_title,
                    next_notes,
                    next_status,
                    next_due_at,
                    updated_at,
                    clean_id,
                ),
            )
        return self.read_todo(clean_id)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_todo(row: sqlite3.Row) -> TodoItem:
        return TodoItem(
            id=row["id"],
            title=row["title"],
            notes=row["notes"],
            status=row["status"],
            due_at=row["due_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _required_text(name: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _optional_text(value: str | None, *, default: str) -> str:
        if value is None:
            return default
        if not isinstance(value, str):
            raise ValueError("value must be a string")
        return value.strip()

    @staticmethod
    def _optional_nullable_text(value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("value must be a string")
        clean = value.strip()
        return clean if clean else None

    @staticmethod
    def validate_status(status: str) -> str:
        if not isinstance(status, str) or not status.strip():
            raise ValueError("status must be a non-empty string")
        clean = status.strip()
        if clean not in TODO_STATUSES:
            raise ValueError("status must be open, done, or canceled")
        return clean

    @classmethod
    def validate_query_status(cls, status: str | None) -> str:
        if status is None:
            return "open"
        if not isinstance(status, str) or not status.strip():
            raise ValueError("status must be a non-empty string")
        clean = status.strip()
        if clean not in TODO_QUERY_STATUSES:
            raise ValueError("status must be open, done, canceled, or all")
        return clean

    @staticmethod
    def _safe_limit(limit: int, *, default: int) -> int:
        if not isinstance(limit, int) or limit < 1:
            return default
        return min(limit, 50)
