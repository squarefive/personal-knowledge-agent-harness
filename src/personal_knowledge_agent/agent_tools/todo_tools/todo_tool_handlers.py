from __future__ import annotations

from dataclasses import asdict
from typing import Any, Protocol

from ...todo_data_access import TodoItem
from .constants import TodoToolConstants as todo_constants


class TodoStore(Protocol):
    def create_todo(
        self,
        *,
        title: str,
        notes: str | None = None,
        due_at: str | None = None,
    ) -> TodoItem: ...

    def list_todos(
        self,
        *,
        query: str | None = None,
        status: str | None = todo_constants.DEFAULT_STATUS,
        limit: int = todo_constants.DEFAULT_LIMIT,
    ) -> list[TodoItem]: ...

    def update_todo(
        self,
        todo_id: str,
        *,
        title: str | None = None,
        notes: str | None = None,
        status: str | None = None,
        due_at: str | None = None,
        clear_due_at: bool = False,
    ) -> TodoItem | None: ...


class TodoToolHandlers:
    def __init__(self, store: TodoStore):
        self.store = store

    def create_todo(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            title = self._required_text(arguments, todo_constants.ARG_TITLE)
            notes = self._optional_text(arguments, todo_constants.ARG_NOTES)
            due_at = self._optional_text(arguments, todo_constants.ARG_DUE_AT)
            todo = self.store.create_todo(title=title, notes=notes, due_at=due_at)
            return {todo_constants.FIELD_OK: True, todo_constants.FIELD_TODO: self._todo_payload(todo)}
        except Exception as exc:
            return self._error(todo_constants.ERROR_INVALID_INPUT, str(exc))

    def list_todos(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            query = self._optional_text(arguments, todo_constants.ARG_QUERY)
            status = self._optional_text(arguments, todo_constants.ARG_STATUS)
            limit = self._optional_limit(arguments, default=todo_constants.DEFAULT_LIMIT)
            todos = self.store.list_todos(query=query, status=status or todo_constants.DEFAULT_STATUS, limit=limit)
            return {
                todo_constants.FIELD_OK: True,
                todo_constants.FIELD_TODOS: [self._todo_payload(todo) for todo in todos],
            }
        except Exception as exc:
            return self._error(todo_constants.ERROR_INVALID_INPUT, str(exc))

    def update_todo(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            todo_id = self._required_text(arguments, todo_constants.ARG_TODO_ID)
            patch = self._update_patch(arguments)
            todo = self.store.update_todo(todo_id, **patch)
            if todo is None:
                return self._error(todo_constants.ERROR_NOT_FOUND, f"todo not found: {todo_id}")
            return {todo_constants.FIELD_OK: True, todo_constants.FIELD_TODO: self._todo_payload(todo)}
        except Exception as exc:
            return self._error(todo_constants.ERROR_INVALID_INPUT, str(exc))

    def definitions(self) -> list[dict[str, Any]]:
        return todo_constants.TODO_TOOL_DEFINITIONS

    @staticmethod
    def _required_text(arguments: dict[str, Any], name: str) -> str:
        value = arguments.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _optional_text(arguments: dict[str, Any], name: str) -> str | None:
        if name not in arguments or arguments.get(name) is None:
            return None
        value = arguments.get(name)
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        return value.strip()

    @staticmethod
    def _optional_limit(arguments: dict[str, Any], default: int) -> int:
        value = arguments.get(todo_constants.ARG_LIMIT, default)
        if not isinstance(value, int) or value < 1:
            return default
        return min(value, todo_constants.MAX_LIMIT)

    def _update_patch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        if todo_constants.ARG_TITLE in arguments:
            patch[todo_constants.PATCH_TITLE] = self._required_text(arguments, todo_constants.ARG_TITLE)
        if todo_constants.ARG_NOTES in arguments:
            patch[todo_constants.PATCH_NOTES] = self._optional_text(arguments, todo_constants.ARG_NOTES) or ""
        if todo_constants.ARG_STATUS in arguments:
            patch[todo_constants.PATCH_STATUS] = self._required_text(arguments, todo_constants.ARG_STATUS)
        if todo_constants.ARG_DUE_AT in arguments:
            due_at = self._optional_text(arguments, todo_constants.ARG_DUE_AT)
            if due_at is None:
                patch[todo_constants.PATCH_CLEAR_DUE_AT] = True
            else:
                patch[todo_constants.PATCH_DUE_AT] = due_at
                if not due_at:
                    patch[todo_constants.PATCH_CLEAR_DUE_AT] = True
        if not patch:
            raise ValueError("at least one field must be provided")
        return patch

    @staticmethod
    def _todo_payload(todo: TodoItem) -> dict[str, Any]:
        payload = asdict(todo)
        payload[todo_constants.FIELD_TODO_ID] = payload.pop(todo_constants.TODO_MODEL_ID_FIELD)
        return payload

    @staticmethod
    def _error(error_code: str, message: str) -> dict[str, Any]:
        return {
            todo_constants.FIELD_OK: False,
            todo_constants.FIELD_ERROR_CODE: error_code,
            todo_constants.FIELD_MESSAGE: message,
        }
