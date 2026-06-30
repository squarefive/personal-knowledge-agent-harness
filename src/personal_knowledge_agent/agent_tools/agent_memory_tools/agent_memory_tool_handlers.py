from __future__ import annotations

from dataclasses import asdict
from typing import Any, Protocol

from ...agent_context.agent_profile_memory import (
    MemoryDocument,
    MemoryIndex,
    MemoryIndexEntry,
)
from .constants import AgentMemoryToolConstants as memory_tool_constants


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
            limit = self._optional_limit(arguments, default=memory_tool_constants.DEFAULT_LIMIT)
            index = self.memory_index_repository.load()
            return {
                memory_tool_constants.FIELD_OK: True,
                memory_tool_constants.FIELD_ENTRIES: [asdict(entry) for entry in index.entries[:limit]],
            }
        except Exception as exc:
            return self._error(memory_tool_constants.ERROR_INVALID_MEMORY_INDEX, str(exc))

    def read_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            name = self._required_text(arguments, memory_tool_constants.ARG_NAME)
            index = self.memory_index_repository.load()
            entry = next((item for item in index.entries if item.name == name), None)
            if entry is None:
                return self._error(memory_tool_constants.ERROR_NOT_FOUND, f"memory not found: {name}")
            memory = self.memory_document_repository.read_by_entry(entry)
            return {memory_tool_constants.FIELD_OK: True, memory_tool_constants.FIELD_MEMORY: asdict(memory)}
        except Exception as exc:
            return self._error(memory_tool_constants.ERROR_INVALID_MEMORY, str(exc))

    def definitions(self) -> list[dict[str, Any]]:
        return memory_tool_constants.AGENT_MEMORY_TOOL_DEFINITIONS

    @staticmethod
    def _required_text(arguments: dict[str, Any], name: str) -> str:
        value = arguments.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _optional_limit(arguments: dict[str, Any], default: int) -> int:
        value = arguments.get(memory_tool_constants.ARG_LIMIT, default)
        if not isinstance(value, int) or value < 1:
            return default
        return min(value, memory_tool_constants.MAX_LIMIT)

    @staticmethod
    def _error(error_code: str, message: str) -> dict[str, Any]:
        return {
            memory_tool_constants.FIELD_OK: False,
            memory_tool_constants.FIELD_ERROR_CODE: error_code,
            memory_tool_constants.FIELD_MESSAGE: message,
        }

__all__ = ["AgentMemoryToolHandlers"]
