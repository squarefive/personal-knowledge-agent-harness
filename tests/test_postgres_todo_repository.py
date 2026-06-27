from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from personal_knowledge_agent.postgres import PostgresTodoRepository


NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=1)
TODO_ROW = (
    "todo_1",
    "Ship postgres todo repository",
    "Keep it data-access only.",
    "open",
    None,
    NOW,
    LATER,
)


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
        self.next_row: object | None = None
        self.next_rows: list[object] = []
        self.rows_by_call: list[object | None] = []
        self.commit_count = 0

    def execute(self, query: str, params: tuple[object, ...] = ()) -> FakeCursor:
        self.executed.append((" ".join(query.split()), params))
        if self.rows_by_call:
            return FakeCursor(row=self.rows_by_call.pop(0), rows=self.next_rows)
        return FakeCursor(row=self.next_row, rows=self.next_rows)

    def commit(self) -> None:
        self.commit_count += 1


def test_create_todo_writes_user_id_and_returns_todo_item() -> None:
    connection = FakeConnection()
    connection.next_row = TODO_ROW
    repo = PostgresTodoRepository(connection, "usr_1")

    todo = repo.create_todo(
        title=" Ship postgres todo repository ",
        notes=" Keep it data-access only. ",
        due_at=" 2026-06-28T09:00:00+08:00 ",
    )

    assert todo.id == "todo_1"
    assert todo.created_at == NOW.isoformat()
    sql, params = connection.executed[0]
    assert "INSERT INTO todo_items" in sql
    assert "user_id" in sql
    assert "RETURNING todo_id" in sql
    assert str(params[0]).startswith("todo_")
    assert params[1:] == (
        "usr_1",
        "Ship postgres todo repository",
        "Keep it data-access only.",
        "open",
        "2026-06-28T09:00:00+08:00",
    )
    assert connection.commit_count == 1


def test_read_todo_filters_by_user_id_and_returns_none_for_cross_user_miss() -> None:
    connection = FakeConnection()
    repo = PostgresTodoRepository(connection, "usr_1")

    todo = repo.read_todo("todo_other")

    assert todo is None
    sql, params = connection.executed[0]
    assert "FROM todo_items WHERE user_id = %s AND todo_id = %s" in sql
    assert params == ("usr_1", "todo_other")


def test_list_todos_filters_by_user_id_status_query_and_limit_with_params() -> None:
    connection = FakeConnection()
    connection.next_rows = [TODO_ROW]
    repo = PostgresTodoRepository(connection, "usr_1")

    todos = repo.list_todos(query=" postgres ", status="done", limit=3)

    assert [todo.id for todo in todos] == ["todo_1"]
    sql, params = connection.executed[0]
    assert "WHERE user_id = %s AND status = %s AND (title ILIKE %s OR notes ILIKE %s)" in sql
    assert "LIMIT %s" in sql
    assert params == ("usr_1", "done", "%postgres%", "%postgres%", 3)


def test_list_todos_all_status_is_query_sentinel_and_keeps_query_parameterized() -> None:
    connection = FakeConnection()
    repo = PostgresTodoRepository(connection, "usr_1")

    todos = repo.list_todos(query="%'; drop table todo_items; --", status="all", limit=500)

    assert todos == []
    sql, params = connection.executed[0]
    assert "status = %s" not in sql
    assert "title ILIKE %s" in sql
    assert params == ("usr_1", "%%'; drop table todo_items; --%", "%%'; drop table todo_items; --%", 50)


def test_update_todo_reads_and_updates_with_user_id_scope() -> None:
    connection = FakeConnection()
    connection.rows_by_call = [TODO_ROW, {**_todo_dict(TODO_ROW), "status": "done"}]
    repo = PostgresTodoRepository(connection, "usr_1")

    updated = repo.update_todo("todo_1", status=" done ")

    assert updated is not None
    assert updated.status == "done"
    read_sql, read_params = connection.executed[0]
    update_sql, update_params = connection.executed[1]
    assert "WHERE user_id = %s AND todo_id = %s" in read_sql
    assert read_params == ("usr_1", "todo_1")
    assert "UPDATE todo_items SET title = %s, notes = %s, status = %s, due_at = %s, updated_at = now()" in update_sql
    assert "WHERE user_id = %s AND todo_id = %s" in update_sql
    assert update_params == (
        "Ship postgres todo repository",
        "Keep it data-access only.",
        "done",
        None,
        "usr_1",
        "todo_1",
    )
    assert connection.commit_count == 1


def test_update_todo_returns_none_for_cross_user_miss_without_update() -> None:
    connection = FakeConnection()
    repo = PostgresTodoRepository(connection, "usr_1")

    updated = repo.update_todo("todo_other", status="done")

    assert updated is None
    assert len(connection.executed) == 1
    sql, params = connection.executed[0]
    assert "WHERE user_id = %s AND todo_id = %s" in sql
    assert params == ("usr_1", "todo_other")
    assert connection.commit_count == 0


def test_update_todo_clear_due_at_sets_due_at_to_null() -> None:
    due_row = {**_todo_dict(TODO_ROW), "due_at": LATER}
    cleared_row = {**due_row, "due_at": None}
    connection = FakeConnection()
    connection.rows_by_call = [due_row, cleared_row]
    repo = PostgresTodoRepository(connection, "usr_1")

    updated = repo.update_todo("todo_1", clear_due_at=True)

    assert updated is not None
    assert updated.due_at is None
    sql, params = connection.executed[1]
    assert "due_at = %s" in sql
    assert params[3] is None
    assert params[-2:] == ("usr_1", "todo_1")


def test_update_todo_due_at_empty_string_clears_due_at_like_sqlite_repository() -> None:
    due_row = {**_todo_dict(TODO_ROW), "due_at": LATER}
    cleared_row = {**due_row, "due_at": None}
    connection = FakeConnection()
    connection.rows_by_call = [due_row, cleared_row]
    repo = PostgresTodoRepository(connection, "usr_1")

    updated = repo.update_todo("todo_1", due_at=" ")

    assert updated is not None
    assert updated.due_at is None
    assert connection.executed[1][1][3] is None


def test_invalid_create_title_rejects_without_sql() -> None:
    connection = FakeConnection()
    repo = PostgresTodoRepository(connection, "usr_1")

    with pytest.raises(ValueError, match="title must be a non-empty string"):
        repo.create_todo(title=" ")

    assert connection.executed == []


def test_invalid_update_status_rejects_without_sql() -> None:
    connection = FakeConnection()
    repo = PostgresTodoRepository(connection, "usr_1")

    with pytest.raises(ValueError, match="status must be open, done, or canceled"):
        repo.update_todo("todo_1", status="all")

    assert connection.executed == []


def test_invalid_list_status_rejects_without_sql() -> None:
    connection = FakeConnection()
    repo = PostgresTodoRepository(connection, "usr_1")

    with pytest.raises(ValueError, match="status must be open, done, canceled, or all"):
        repo.list_todos(status="blocked")

    assert connection.executed == []


def _todo_dict(row: tuple[object, ...]) -> dict[str, object]:
    return {
        "todo_id": row[0],
        "title": row[1],
        "notes": row[2],
        "status": row[3],
        "due_at": row[4],
        "created_at": row[5],
        "updated_at": row[6],
    }
