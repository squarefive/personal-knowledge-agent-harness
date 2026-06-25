from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ...todo_data_access import TodoItem, TodoRepository


class TodoToolHandlers:
    def __init__(self, store: TodoRepository):
        self.store = store

    def create_todo(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            title = self._required_text(arguments, "title")
            notes = self._optional_text(arguments, "notes")
            due_at = self._optional_text(arguments, "due_at")
            todo = self.store.create_todo(title=title, notes=notes, due_at=due_at)
            return {"ok": True, "todo": self._todo_payload(todo)}
        except Exception as exc:
            return self._error("invalid_input", str(exc))

    def list_todos(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            query = self._optional_text(arguments, "query")
            status = self._optional_text(arguments, "status")
            limit = self._optional_limit(arguments, default=20)
            todos = self.store.list_todos(query=query, status=status or "open", limit=limit)
            return {"ok": True, "todos": [self._todo_payload(todo) for todo in todos]}
        except Exception as exc:
            return self._error("invalid_input", str(exc))

    def update_todo(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            todo_id = self._required_text(arguments, "todo_id")
            patch = self._update_patch(arguments)
            todo = self.store.update_todo(todo_id, **patch)
            if todo is None:
                return self._error("not_found", f"todo not found: {todo_id}")
            return {"ok": True, "todo": self._todo_payload(todo)}
        except Exception as exc:
            return self._error("invalid_input", str(exc))

    def definitions(self) -> list[dict[str, Any]]:
        return TODO_TOOL_DEFINITIONS

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
        value = arguments.get("limit", default)
        if not isinstance(value, int) or value < 1:
            return default
        return min(value, 50)

    def _update_patch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        if "title" in arguments:
            patch["title"] = self._required_text(arguments, "title")
        if "notes" in arguments:
            patch["notes"] = self._optional_text(arguments, "notes") or ""
        if "status" in arguments:
            patch["status"] = self._required_text(arguments, "status")
        if "due_at" in arguments:
            due_at = self._optional_text(arguments, "due_at")
            if due_at is None:
                patch["clear_due_at"] = True
            else:
                patch["due_at"] = due_at
                if not due_at:
                    patch["clear_due_at"] = True
        if not patch:
            raise ValueError("at least one field must be provided")
        return patch

    @staticmethod
    def _todo_payload(todo: TodoItem) -> dict[str, Any]:
        payload = asdict(todo)
        payload["todo_id"] = payload.pop("id")
        return payload

    @staticmethod
    def _error(error_code: str, message: str) -> dict[str, Any]:
        return {"ok": False, "error_code": error_code, "message": message}


TODO_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_todo",
            "description": "保存一条本地 todo 待办项。当用户明确要求记录之后要做的行动项、任务或待办时使用；本工具会写入 SQLite todo_items。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "待办标题，应是用户要之后执行的具体行动项；不得把普通聊天、假设或未确认计划保存为待办。",
                    },
                    "notes": {
                        "type": "string",
                        "description": "可选补充说明。只有用户提供额外背景或细节时填写；没有则省略。",
                    },
                    "due_at": {
                        "type": "string",
                        "description": "可选截止时间。第一版只保存用户明确提供的时间文本或 ISO 风格字符串，不做提醒或自然语言时间推断。",
                    },
                },
                "required": ["title"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_todos",
            "description": "查询本地 todo 待办项。当用户要求查看、搜索或核对本地 todo 列表时使用；默认只返回 open 待办。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "可选搜索词，用于匹配待办标题和备注。",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["open", "done", "canceled", "all"],
                        "description": "可选状态过滤。默认 open；用户明确要求全部时使用 all；用户要求已完成或已取消时分别使用 done 或 canceled。",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最大返回数量，工具会限制到允许范围。",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_todo",
            "description": "更新一条本地 todo 待办项。当用户明确要求修改待办标题、备注、截止时间或状态时使用；需要真实 todo_id。",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {
                        "type": "string",
                        "description": "要更新的 todo ID。若用户没有提供明确 ID，应先查询候选并让用户确认，不要凭最近一条待办静默修改。",
                    },
                    "title": {
                        "type": "string",
                        "description": "新的待办标题，提供时必须是非空具体行动项。",
                    },
                    "notes": {
                        "type": "string",
                        "description": "新的补充说明。可为空字符串，用于清空备注。",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["open", "done", "canceled"],
                        "description": "新的待办状态。完成使用 done；取消或不再需要使用 canceled；重新打开使用 open。",
                    },
                    "due_at": {
                        "type": "string",
                        "description": "新的截止时间。空字符串表示清空截止时间；第一版不做提醒或自然语言时间推断。",
                    },
                },
                "required": ["todo_id"],
                "additionalProperties": False,
            },
        },
    },
]
