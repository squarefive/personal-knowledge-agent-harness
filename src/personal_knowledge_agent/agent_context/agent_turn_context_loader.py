from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .agent_profile_memory import (
    AgentMemoryDocumentRepository,
    AgentMemoryIndexRepository,
    MemoryDocument,
    MemoryIndex,
    MemoryIndexEntry,
)

MAX_SELECTED_MEMORY_DOCUMENTS = 3


@dataclass
class TurnContext:
    memory_index: MemoryIndex | None
    selected_memories: list[MemoryDocument]


class TurnContextLoader:
    def __init__(
        self,
        *,
        memory_index_store: AgentMemoryIndexRepository | None = None,
        memory_store: AgentMemoryDocumentRepository | None = None,
    ):
        self.memory_index_store = memory_index_store
        self.memory_store = memory_store

    def load(
        self,
        *,
        user_input: str,
        recent_messages: list[dict[str, Any]],
    ) -> TurnContext:
        memory_index = self._load_memory_index()
        if memory_index is None or self.memory_store is None:
            return TurnContext(memory_index=memory_index, selected_memories=[])

        selected_entries = self._select_memory_entries(
            user_input=user_input,
            memory_index=memory_index,
            recent_messages=recent_messages,
        )
        selected_memories: list[MemoryDocument] = []
        for entry in selected_entries:
            try:
                selected_memories.append(self.memory_store.read_by_entry(entry))
            except Exception:
                continue
        return TurnContext(memory_index=memory_index, selected_memories=selected_memories)

    def _load_memory_index(self) -> MemoryIndex | None:
        if self.memory_index_store is None:
            return None
        try:
            return self.memory_index_store.load()
        except Exception:
            return MemoryIndex()

    @staticmethod
    def _select_memory_entries(
        *,
        user_input: str,
        memory_index: MemoryIndex,
        recent_messages: list[dict[str, Any]] | None = None,
        limit: int = MAX_SELECTED_MEMORY_DOCUMENTS,
    ) -> list[MemoryIndexEntry]:
        query_parts = [user_input]
        if recent_messages:
            query_parts.extend(_message_text(message) for message in recent_messages)
        query = " ".join(part for part in query_parts if part).lower()
        if not query:
            return []

        scored: list[tuple[int, MemoryIndexEntry]] = []
        for entry in memory_index.entries:
            haystack = " ".join([entry.name, entry.type, entry.description, entry.path]).lower()
            score = 0
            for token in _query_tokens(query):
                if token in haystack:
                    score += 1
            if entry.name.lower() in query:
                score += 2
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored[:limit]]


def _query_tokens(query: str) -> list[str]:
    return [token for token in query.replace("/", " ").replace("-", " ").split() if token]


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    return str(content)
