import pytest

from personal_knowledge_agent.todo_data_access import TodoRepository


def test_create_list_and_update_todos(tmp_path):
    store = TodoRepository(tmp_path / "knowledge.db")

    todo = store.create_todo(
        title="整理 prompt 原则",
        notes="把工具说明留在 schema",
        due_at="明天下午",
    )

    assert todo.id.startswith("todo_")
    assert todo.title == "整理 prompt 原则"
    assert todo.notes == "把工具说明留在 schema"
    assert todo.status == "open"
    assert todo.due_at == "明天下午"

    assert [item.id for item in store.list_todos()] == [todo.id]
    assert [item.id for item in store.list_todos(query="schema")] == [todo.id]

    updated = store.update_todo(todo.id, status="done", notes="")

    assert updated is not None
    assert updated.id == todo.id
    assert updated.status == "done"
    assert updated.notes == ""
    assert updated.updated_at != todo.updated_at
    assert store.list_todos() == []
    assert [item.id for item in store.list_todos(status="done")] == [todo.id]
    assert [item.id for item in store.list_todos(status="all")] == [todo.id]


def test_create_todo_requires_title(tmp_path):
    store = TodoRepository(tmp_path / "knowledge.db")

    with pytest.raises(ValueError, match="title"):
        store.create_todo(title=" ")


def test_update_todo_requires_existing_item_and_patch(tmp_path):
    store = TodoRepository(tmp_path / "knowledge.db")

    assert store.update_todo("todo_missing", status="done") is None

    todo = store.create_todo(title="写测试")
    with pytest.raises(ValueError, match="at least one field"):
        store.update_todo(todo.id)


def test_todo_status_validation(tmp_path):
    store = TodoRepository(tmp_path / "knowledge.db")
    todo = store.create_todo(title="整理待办")

    with pytest.raises(ValueError, match="status"):
        store.update_todo(todo.id, status="archived")

    with pytest.raises(ValueError, match="status"):
        store.list_todos(status="archived")


def test_due_at_can_be_cleared(tmp_path):
    store = TodoRepository(tmp_path / "knowledge.db")
    todo = store.create_todo(title="提交 PR", due_at="周五")

    updated = store.update_todo(todo.id, clear_due_at=True)

    assert updated is not None
    assert updated.due_at is None
