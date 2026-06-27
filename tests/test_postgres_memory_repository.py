from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from personal_knowledge_agent.agent_context.agent_profile_memory import MemoryIndexEntry
from personal_knowledge_agent.agent_tools import AgentMemoryToolHandlers
from personal_knowledge_agent.postgres import PostgresAgentMemoryRepository


NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 6, 27, 13, 0, tzinfo=UTC)


class FakeCursor:
    def __init__(self, row: object | None = None, rows: list[object] | None = None) -> None:
        self._row = row
        self._rows = rows or []

    def fetchone(self) -> object | None:
        return self._row

    def fetchall(self) -> list[object]:
        return self._rows


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.rows: list[dict[str, object]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> FakeCursor:
        sql = " ".join(query.split())
        self.executed.append((sql, params))
        if "SELECT memory_id, title, summary FROM agent_user_memories" in sql:
            user_id = params[0]
            rows = [
                (row["memory_id"], row["title"], row["summary"])
                for row in sorted(
                    self.rows,
                    key=lambda item: (item["updated_at"], item["memory_id"]),
                    reverse=True,
                )
                if row["user_id"] == user_id
            ]
            return FakeCursor(rows=rows)
        if "SELECT memory_id, title, summary, content, updated_at FROM agent_user_memories" in sql:
            user_id, memory_id = params
            row = next(
                (
                    (
                        item["memory_id"],
                        item["title"],
                        item["summary"],
                        item["content"],
                        item["updated_at"],
                    )
                    for item in self.rows
                    if item["user_id"] == user_id and item["memory_id"] == memory_id
                ),
                None,
            )
            return FakeCursor(row=row)
        return FakeCursor()


def test_load_returns_empty_index_for_empty_table() -> None:
    connection = FakeConnection()
    repo = PostgresAgentMemoryRepository(connection, "usr_1")

    index = repo.load()

    assert index.entries == []
    sql, params = connection.executed[0]
    assert "FROM agent_user_memories WHERE user_id = %s" in sql
    assert params == ("usr_1",)


def test_repository_filters_index_and_documents_by_user_id() -> None:
    connection = FakeConnection()
    connection.rows = [
        {
            "user_id": "usr_1",
            "memory_id": "reply-style",
            "title": "回复风格",
            "summary": "先给结论",
            "content": "用户偏好：先给结论。",
            "updated_at": LATER,
        },
        {
            "user_id": "usr_2",
            "memory_id": "reply-style",
            "title": "回复风格",
            "summary": "先给背景",
            "content": "用户偏好：先给背景。",
            "updated_at": NOW,
        },
    ]
    first_repo = PostgresAgentMemoryRepository(connection, "usr_1")
    second_repo = PostgresAgentMemoryRepository(connection, "usr_2")

    first_index = first_repo.load()
    first_memory = first_repo.read_by_entry(first_index.entries[0])
    second_index = second_repo.load()
    second_memory = second_repo.read_by_entry(second_index.entries[0])

    assert first_index.entries[0].name == "reply-style"
    assert first_index.entries[0].type == "user"
    assert first_memory.content == "用户偏好：先给结论。"
    assert second_memory.content == "用户偏好：先给背景。"
    assert connection.executed[1][1] == ("usr_1", "reply-style")
    assert connection.executed[3][1] == ("usr_2", "reply-style")


def test_read_by_entry_hides_cross_user_memory_as_not_found() -> None:
    connection = FakeConnection()
    connection.rows = [
        {
            "user_id": "usr_2",
            "memory_id": "reply-style",
            "title": "回复风格",
            "summary": "先给背景",
            "content": "用户偏好：先给背景。",
            "updated_at": NOW,
        }
    ]
    repo = PostgresAgentMemoryRepository(connection, "usr_1")
    entry = MemoryIndexEntry(
        name="reply-style",
        type="user",
        description="先给背景",
        path="postgres:agent_user_memories/reply-style",
    )

    with pytest.raises(FileNotFoundError, match="memory not found"):
        repo.read_by_entry(entry)


def test_memory_tools_use_bound_postgres_user_without_exposing_user_id() -> None:
    connection = FakeConnection()
    connection.rows = [
        {
            "user_id": "usr_1",
            "memory_id": "reply-style",
            "title": "回复风格",
            "summary": "先给结论",
            "content": "用户偏好：先给结论。",
            "updated_at": NOW,
        },
        {
            "user_id": "usr_2",
            "memory_id": "reply-style",
            "title": "回复风格",
            "summary": "先给背景",
            "content": "用户偏好：先给背景。",
            "updated_at": NOW,
        },
    ]
    repository = PostgresAgentMemoryRepository(connection, "usr_1")
    tools = AgentMemoryToolHandlers(
        memory_index_repository=repository,
        memory_document_repository=repository,
    )

    index = tools.list_memory_index({"limit": 10})
    memory = tools.read_memory({"name": "reply-style"})

    assert index["ok"] is True
    assert index["entries"][0]["name"] == "reply-style"
    assert memory["ok"] is True
    assert memory["memory"]["content"] == "用户偏好：先给结论。"
    serialized = json.dumps({"index": index, "memory": memory}, ensure_ascii=False)
    assert "usr_1" not in serialized
    assert "usr_2" not in serialized
    assert "user_id" not in serialized
