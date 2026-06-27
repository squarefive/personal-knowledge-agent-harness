from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from ..agent_context.agent_profile_memory import (
    MemoryDocument,
    MemoryIndex,
    MemoryIndexEntry,
)


class PostgresConnection(Protocol):
    """Small DB-API surface used by the user memory repository."""

    def execute(self, query: str, params: Sequence[object] = ()) -> object: ...


class PostgresAgentMemoryRepository:
    """Reads user-preference memory rows scoped to one authenticated user."""

    def __init__(self, connection: PostgresConnection, user_id: str) -> None:
        _require_text("user_id", user_id)
        self._connection = connection
        self._user_id = user_id.strip()

    def load(self) -> MemoryIndex:
        cursor = self._connection.execute(
            """
            SELECT memory_id, title, summary
            FROM agent_user_memories
            WHERE user_id = %s
            ORDER BY updated_at DESC, memory_id DESC
            """,
            (self._user_id,),
        )
        return MemoryIndex(entries=[_row_to_index_entry(row) for row in _fetchall(cursor)])

    def read_by_entry(self, entry: MemoryIndexEntry) -> MemoryDocument:
        memory_id = _require_text("memory_id", entry.name)
        cursor = self._connection.execute(
            """
            SELECT memory_id, title, summary, content, updated_at
            FROM agent_user_memories
            WHERE user_id = %s AND memory_id = %s
            """,
            (self._user_id, memory_id),
        )
        row = _fetchone(cursor)
        if row is None:
            raise FileNotFoundError(f"memory not found: {memory_id}")
        return _row_to_document(row)


def _row_to_index_entry(row: object) -> MemoryIndexEntry:
    memory_id, title, summary = _row_values(row, "memory_id", "title", "summary")
    return MemoryIndexEntry(
        name=str(memory_id),
        type="user",
        description=str(summary or title),
        path=f"postgres:agent_user_memories/{memory_id}",
    )


def _row_to_document(row: object) -> MemoryDocument:
    memory_id, title, summary, content, updated_at = _row_values(
        row,
        "memory_id",
        "title",
        "summary",
        "content",
        "updated_at",
    )
    return MemoryDocument(
        name=str(memory_id),
        type="user",
        description=str(summary or title),
        path=f"postgres:agent_user_memories/{memory_id}",
        updated_at=_format_datetime(updated_at),
        source_type="user_preference",
        source_ref=None,
        content=str(content),
    )


def _row_values(row: object, *keys: str) -> tuple[object, ...]:
    if isinstance(row, dict):
        return tuple(row[key] for key in keys)
    return tuple(row[index] for index in range(len(keys)))  # type: ignore[index]


def _fetchone(cursor: object) -> object | None:
    fetchone = getattr(cursor, "fetchone", None)
    if callable(fetchone):
        return fetchone()
    return None


def _fetchall(cursor: object) -> list[object]:
    fetchall = getattr(cursor, "fetchall", None)
    if callable(fetchall):
        return list(fetchall())
    return []


def _format_datetime(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


__all__ = ["PostgresAgentMemoryRepository"]
