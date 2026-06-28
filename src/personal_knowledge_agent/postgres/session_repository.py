from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from psycopg.types.json import Jsonb


class PostgresConnection(Protocol):
    def execute(self, query: str, params: Sequence[object] = ()) -> object: ...


@dataclass(frozen=True)
class ConversationSessionRecord:
    session_id: str
    title: str | None
    summary: str | None
    status: str
    current_run_id: str | None
    last_prompt_usage_ratio: float | None
    created_at: str
    updated_at: str


class PostgresConversationSessionRepository:
    def __init__(self, connection: PostgresConnection, user_id: str) -> None:
        _require_text("user_id", user_id)
        self._connection = connection
        self._user_id = user_id.strip()

    def create_session(self, *, session_id: str | None = None, title: str | None = None) -> ConversationSessionRecord:
        clean_session_id = session_id.strip() if session_id is not None else f"sess_{uuid.uuid4().hex}"
        _require_text("session_id", clean_session_id)
        clean_title = _optional_text("title", title)

        cursor = self._connection.execute(
            """
            INSERT INTO conversation_sessions (session_id, user_id, title)
            VALUES (%s, %s, %s)
            RETURNING
              session_id,
              title,
              summary,
              status,
              current_run_id,
              last_prompt_usage_ratio,
              created_at,
              updated_at
            """,
            (clean_session_id, self._user_id, clean_title),
        )
        row = _fetchone(cursor)
        self._commit()
        if row is None:
            return ConversationSessionRecord(
                session_id=clean_session_id,
                title=clean_title,
                summary=None,
                status="idle",
                current_run_id=None,
                last_prompt_usage_ratio=None,
                created_at="",
                updated_at="",
            )
        return _row_to_session(row)

    def list_sessions(self, *, limit: int = 20) -> list[ConversationSessionRecord]:
        cursor = self._connection.execute(
            """
            SELECT
              session_id,
              title,
              summary,
              status,
              current_run_id,
              last_prompt_usage_ratio,
              created_at,
              updated_at
            FROM conversation_sessions
            WHERE user_id = %s
            ORDER BY updated_at DESC, session_id DESC
            LIMIT %s
            """,
            (self._user_id, _safe_limit(limit)),
        )
        return [_row_to_session(row) for row in _fetchall(cursor)]

    def rename_session(self, session_id: str, title: str) -> ConversationSessionRecord | None:
        clean_session_id = _require_text("session_id", session_id)
        clean_title = _require_text("title", title)
        cursor = self._connection.execute(
            """
            UPDATE conversation_sessions
            SET title = %s, updated_at = now()
            WHERE user_id = %s AND session_id = %s
            RETURNING
              session_id,
              title,
              summary,
              status,
              current_run_id,
              last_prompt_usage_ratio,
              created_at,
              updated_at
            """,
            (clean_title, self._user_id, clean_session_id),
        )
        row = _fetchone(cursor)
        self._commit()
        if row is None:
            return None
        return _row_to_session(row)

    def get_session(self, session_id: str) -> ConversationSessionRecord | None:
        clean_session_id = _require_text("session_id", session_id)
        cursor = self._connection.execute(
            """
            SELECT
              session_id,
              title,
              summary,
              status,
              current_run_id,
              last_prompt_usage_ratio,
              created_at,
              updated_at
            FROM conversation_sessions
            WHERE user_id = %s AND session_id = %s
            """,
            (self._user_id, clean_session_id),
        )
        row = _fetchone(cursor)
        if row is None:
            return None
        return _row_to_session(row)

    def append_message(
        self,
        session_id: str,
        message: dict,
        *,
        sequence_no: int | None = None,
        role: str | None = None,
    ) -> int:
        clean_session_id = _require_text("session_id", session_id)
        if not isinstance(message, dict):
            raise ValueError("message must be a dict")
        clean_sequence_no = sequence_no if sequence_no is not None else self._next_sequence_no(clean_session_id)
        if not isinstance(clean_sequence_no, int) or clean_sequence_no < 1:
            raise ValueError("sequence_no must be a positive integer")
        message_role = message.get("role")
        clean_role = _optional_text("role", role) or _require_text(
            "message.role",
            message_role if isinstance(message_role, str) else "",
        )

        self._connection.execute(
            """
            INSERT INTO conversation_messages (user_id, session_id, sequence_no, role, message)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (self._user_id, clean_session_id, clean_sequence_no, clean_role, Jsonb(message)),
        )
        self._connection.execute(
            """
            UPDATE conversation_sessions
            SET updated_at = now()
            WHERE user_id = %s AND session_id = %s
            """,
            (self._user_id, clean_session_id),
        )
        self._commit()
        return clean_sequence_no

    def load_messages(self, session_id: str, *, limit: int | None = None) -> list[dict]:
        clean_session_id = _require_text("session_id", session_id)
        if limit is None:
            cursor = self._connection.execute(
                """
                SELECT message
                FROM conversation_messages
                WHERE user_id = %s AND session_id = %s
                ORDER BY sequence_no ASC
                """,
                (self._user_id, clean_session_id),
            )
        else:
            cursor = self._connection.execute(
                """
                SELECT message
                FROM conversation_messages
                WHERE user_id = %s AND session_id = %s
                ORDER BY sequence_no ASC
                LIMIT %s
                """,
                (self._user_id, clean_session_id, _safe_limit(limit)),
            )
        return [_message_from_value(_row_value(row, 0, "message")) for row in _fetchall(cursor)]

    def count_messages(self, session_id: str) -> int:
        clean_session_id = _require_text("session_id", session_id)
        cursor = self._connection.execute(
            """
            SELECT COUNT(*)
            FROM conversation_messages
            WHERE user_id = %s AND session_id = %s
            """,
            (self._user_id, clean_session_id),
        )
        row = _fetchone(cursor)
        if row is None:
            return 0
        return int(_row_value(row, 0, "count"))

    def update_summary(self, session_id: str, summary: str | None) -> bool:
        clean_session_id = _require_text("session_id", session_id)
        clean_summary = _optional_text("summary", summary)
        cursor = self._connection.execute(
            """
            UPDATE conversation_sessions
            SET summary = %s, updated_at = now()
            WHERE user_id = %s AND session_id = %s
            """,
            (clean_summary, self._user_id, clean_session_id),
        )
        self._commit()
        return _rowcount(cursor) > 0

    def update_prompt_usage_ratio(self, session_id: str, ratio: float | None) -> bool:
        clean_session_id = _require_text("session_id", session_id)
        clean_ratio = _optional_ratio("ratio", ratio)
        cursor = self._connection.execute(
            """
            UPDATE conversation_sessions
            SET last_prompt_usage_ratio = %s, updated_at = now()
            WHERE user_id = %s AND session_id = %s
            """,
            (clean_ratio, self._user_id, clean_session_id),
        )
        self._commit()
        return _rowcount(cursor) > 0

    def mark_running(self, session_id: str, *, run_id: str | None = None) -> bool:
        clean_session_id = _require_text("session_id", session_id)
        clean_run_id = _optional_text("run_id", run_id)
        cursor = self._connection.execute(
            """
            UPDATE conversation_sessions
            SET status = 'running', current_run_id = %s, updated_at = now()
            WHERE user_id = %s AND session_id = %s
            """,
            (clean_run_id, self._user_id, clean_session_id),
        )
        self._commit()
        return _rowcount(cursor) > 0

    def mark_idle(self, session_id: str) -> bool:
        clean_session_id = _require_text("session_id", session_id)
        cursor = self._connection.execute(
            """
            UPDATE conversation_sessions
            SET status = 'idle', current_run_id = NULL, updated_at = now()
            WHERE user_id = %s AND session_id = %s
            """,
            (self._user_id, clean_session_id),
        )
        self._commit()
        return _rowcount(cursor) > 0

    def _next_sequence_no(self, session_id: str) -> int:
        cursor = self._connection.execute(
            """
            SELECT COALESCE(MAX(sequence_no), 0) + 1
            FROM conversation_messages
            WHERE user_id = %s AND session_id = %s
            """,
            (self._user_id, session_id),
        )
        row = _fetchone(cursor)
        if row is None:
            return 1
        return int(_row_value(row, 0, "sequence_no"))

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


def _rowcount(cursor: object) -> int:
    rowcount = getattr(cursor, "rowcount", 0)
    return int(rowcount)


def _row_to_session(row: object) -> ConversationSessionRecord:
    legacy_tuple_row = not isinstance(row, dict) and hasattr(row, "__len__") and len(row) == 7  # type: ignore[arg-type]
    usage_ratio = None if legacy_tuple_row else _optional_float(_row_value(row, 5, "last_prompt_usage_ratio"))
    created_at_index = 5 if legacy_tuple_row else 6
    updated_at_index = 6 if legacy_tuple_row else 7
    return ConversationSessionRecord(
        session_id=_row_value(row, 0, "session_id"),
        title=_row_value(row, 1, "title"),
        summary=_row_value(row, 2, "summary"),
        status=_row_value(row, 3, "status"),
        current_run_id=_row_value(row, 4, "current_run_id"),
        last_prompt_usage_ratio=usage_ratio,
        created_at=_stringify_timestamp(_row_value(row, created_at_index, "created_at")),
        updated_at=_stringify_timestamp(_row_value(row, updated_at_index, "updated_at")),
    )


def _message_from_value(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("stored message must be a dict")
    return value


def _row_value(row: object, index: int, key: str) -> object:
    if isinstance(row, dict):
        return row[key]
    return row[index]  # type: ignore[index]


def _stringify_timestamp(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_text(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    return _require_text(name, value)


def _optional_ratio(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    ratio = float(value)
    if ratio < 0 or ratio > 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return ratio


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _safe_limit(limit: int) -> int:
    if not isinstance(limit, int) or limit < 1:
        return 20
    return min(limit, 100)
