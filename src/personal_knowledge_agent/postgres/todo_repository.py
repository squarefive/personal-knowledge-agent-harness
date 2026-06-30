from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from personal_knowledge_agent.todo_data_access.todo_models import TodoItem
from .constants import PostgresConstants as postgres_constants


class PostgresConnection(Protocol):
    def execute(self, query: str, params: Sequence[object] = ()) -> object: ...


class PostgresTodoRepository:
    def __init__(self, connection: PostgresConnection, user_id: str) -> None:
        _require_text("user_id", user_id)
        self._connection = connection
        self._user_id = user_id.strip()

    def create_todo(
        self,
        *,
        title: str,
        notes: str | None = None,
        due_at: str | None = None,
    ) -> TodoItem:
        clean_title = _require_text("title", title)
        clean_notes = _optional_text(notes, default="")
        clean_due_at = _optional_nullable_text(due_at)
        todo_id = f"todo_{uuid.uuid4().hex}"

        cursor = self._connection.execute(
            """
            INSERT INTO todo_items (
              todo_id,
              user_id,
              title,
              notes,
              status,
              due_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING
              todo_id,
              title,
              notes,
              status,
              due_at,
              created_at,
              updated_at
            """,
                (todo_id, self._user_id, clean_title, clean_notes, postgres_constants.TODO_STATUS_OPEN, clean_due_at),
        )
        row = _fetchone(cursor)
        self._commit()
        if row is None:
            return TodoItem(
                id=todo_id,
                title=clean_title,
                notes=clean_notes,
                status=postgres_constants.TODO_STATUS_OPEN,
                due_at=clean_due_at,
                created_at="",
                updated_at="",
            )
        return _row_to_todo(row)

    def read_todo(self, todo_id: str) -> TodoItem | None:
        clean_id = _require_text("todo_id", todo_id)
        cursor = self._connection.execute(
            """
            SELECT
              todo_id,
              title,
              notes,
              status,
              due_at,
              created_at,
              updated_at
            FROM todo_items
            WHERE user_id = %s AND todo_id = %s
            """,
            (self._user_id, clean_id),
        )
        row = _fetchone(cursor)
        if row is None:
            return None
        return _row_to_todo(row)

    def list_todos(
        self,
        *,
        query: str | None = None,
        status: str | None = postgres_constants.TODO_STATUS_OPEN,
        limit: int = postgres_constants.DEFAULT_TODO_LIMIT,
    ) -> list[TodoItem]:
        clean_query = _optional_nullable_text(query)
        clean_status = validate_query_status(status)
        safe_limit = _safe_limit(limit, default=postgres_constants.DEFAULT_TODO_LIMIT)

        clauses = ["user_id = %s"]
        params: list[object] = [self._user_id]
        if clean_status != postgres_constants.TODO_QUERY_STATUS_ALL:
            clauses.append("status = %s")
            params.append(clean_status)
        if clean_query is not None:
            pattern = f"%{clean_query}%"
            clauses.append("(title ILIKE %s OR notes ILIKE %s)")
            params.extend([pattern, pattern])

        cursor = self._connection.execute(
            f"""
            SELECT
              todo_id,
              title,
              notes,
              status,
              due_at,
              created_at,
              updated_at
            FROM todo_items
            WHERE {" AND ".join(clauses)}
            ORDER BY updated_at DESC, created_at DESC, todo_id DESC
            LIMIT %s
            """,
            (*params, safe_limit),
        )
        return [_row_to_todo(row) for row in _fetchall(cursor)]

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
        clean_id = _require_text("todo_id", todo_id)
        next_title = _optional_required_text("title", title)
        next_notes = _optional_text(notes, default=None)
        next_status = validate_status(status) if status is not None else None
        next_due_at = _optional_nullable_text(due_at)

        current = self.read_todo(clean_id)
        if current is None:
            return None
        if title is None and notes is None and status is None and due_at is None and not clear_due_at:
            raise ValueError("at least one field must be provided")

        final_title = current.title if next_title is None else next_title
        final_notes = current.notes if next_notes is None else next_notes
        final_status = current.status if next_status is None else next_status
        final_due_at = None if clear_due_at else (current.due_at if due_at is None else next_due_at)

        cursor = self._connection.execute(
            """
            UPDATE todo_items
            SET
              title = %s,
              notes = %s,
              status = %s,
              due_at = %s,
              updated_at = now()
            WHERE user_id = %s AND todo_id = %s
            RETURNING
              todo_id,
              title,
              notes,
              status,
              due_at,
              created_at,
              updated_at
            """,
            (
                final_title,
                final_notes,
                final_status,
                final_due_at,
                self._user_id,
                clean_id,
            ),
        )
        row = _fetchone(cursor)
        self._commit()
        if row is None:
            return None
        return _row_to_todo(row)

    def _commit(self) -> None:
        commit = getattr(self._connection, "commit", None)
        if callable(commit):
            commit()


def _fetchone(cursor: object) -> object | None:
    fetchone = getattr(cursor, "fetchone")
    return fetchone()


def _fetchall(cursor: object) -> list[object]:
    fetchall = getattr(cursor, "fetchall")
    return list(fetchall())


def _row_to_todo(row: object) -> TodoItem:
    return TodoItem(
        id=_row_value(row, 0, "todo_id"),
        title=_row_value(row, 1, "title"),
        notes=_row_value(row, 2, "notes") or "",
        status=_row_value(row, 3, "status"),
        due_at=_optional_stringify_timestamp(_row_value(row, 4, "due_at")),
        created_at=_stringify_timestamp(_row_value(row, 5, "created_at")),
        updated_at=_stringify_timestamp(_row_value(row, 6, "updated_at")),
    )


def _row_value(row: object, index: int, key: str) -> object:
    if isinstance(row, dict):
        return row[key]
    return row[index]  # type: ignore[index]


def _stringify_timestamp(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _optional_stringify_timestamp(value: object) -> str | None:
    if value is None:
        return None
    return _stringify_timestamp(value)


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_required_text(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    return _require_text(name, value)


def _optional_text(value: str | None, *, default: str | None) -> str | None:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError("value must be a string")
    return value.strip()


def _optional_nullable_text(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("value must be a string")
    clean = value.strip()
    return clean if clean else None


def validate_status(status: str) -> str:
    if not isinstance(status, str) or not status.strip():
        raise ValueError("status must be a non-empty string")
    clean = status.strip()
    if clean not in postgres_constants.TODO_STATUSES:
        raise ValueError("status must be open, done, or canceled")
    return clean


def validate_query_status(status: str | None) -> str:
    if status is None:
        return postgres_constants.TODO_STATUS_OPEN
    if not isinstance(status, str) or not status.strip():
        raise ValueError("status must be a non-empty string")
    clean = status.strip()
    if clean not in postgres_constants.TODO_QUERY_STATUSES:
        raise ValueError("status must be open, done, canceled, or all")
    return clean


def _safe_limit(limit: int, *, default: int) -> int:
    if not isinstance(limit, int) or limit < 1:
        return default
    return min(limit, postgres_constants.MAX_TODO_LIMIT)
