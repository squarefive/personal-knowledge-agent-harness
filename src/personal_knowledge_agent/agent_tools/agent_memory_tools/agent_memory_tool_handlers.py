from __future__ import annotations

from dataclasses import asdict
from typing import Any, Protocol

from ...agent_context.agent_profile_memory import (
    MemoryDocument,
    MemoryIndex,
    MemoryIndexEntry,
)


class MemoryIndexRepository(Protocol):
    def load(self) -> MemoryIndex: ...


class MemoryDocumentRepository(Protocol):
    def read_by_entry(self, entry: MemoryIndexEntry) -> MemoryDocument: ...


class AgentMemoryToolHandlers:
    def __init__(
        self,
        *,
        memory_index_repository: MemoryIndexRepository,
        memory_document_repository: MemoryDocumentRepository,
    ):
        self.memory_index_repository = memory_index_repository
        self.memory_document_repository = memory_document_repository

    def list_memory_index(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            limit = self._optional_limit(arguments, default=50)
            index = self.memory_index_repository.load()
            return {"ok": True, "entries": [asdict(entry) for entry in index.entries[:limit]]}
        except Exception as exc:
            return self._error("invalid_memory_index", str(exc))

    def read_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            name = self._required_text(arguments, "name")
            index = self.memory_index_repository.load()
            entry = next((item for item in index.entries if item.name == name), None)
            if entry is None:
                return self._error("not_found", f"memory not found: {name}")
            memory = self.memory_document_repository.read_by_entry(entry)
            return {"ok": True, "memory": asdict(memory)}
        except Exception as exc:
            return self._error("invalid_memory", str(exc))

    def definitions(self) -> list[dict[str, Any]]:
        return AGENT_MEMORY_TOOL_DEFINITIONS

    @staticmethod
    def _required_text(arguments: dict[str, Any], name: str) -> str:
        value = arguments.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _optional_limit(arguments: dict[str, Any], default: int) -> int:
        value = arguments.get("limit", default)
        if not isinstance(value, int) or value < 1:
            return default
        return min(value, 50)

    @staticmethod
    def _error(error_code: str, message: str) -> dict[str, Any]:
        return {"ok": False, "error_code": error_code, "message": message}


AGENT_MEMORY_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_memory_index",
            "description": "列出 Agent memory 索引。Agent memory 只用于理解用户偏好、项目约束和协作上下文，不能作为 Q&A 知识库事实来源。",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "最大返回数量，工具会限制到允许范围。",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "按 memory name 读取 Agent memory 全文。仅用于理解用户偏好、项目约束和协作上下文；不得把 memory 内容作为 Q&A 卡片来源或当前用户个人知识库事实依据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "来自 memory index 的 memory name。",
                    }
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
]

__all__ = ["AgentMemoryToolHandlers"]
