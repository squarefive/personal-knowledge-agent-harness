from __future__ import annotations

from typing import Protocol

from .agent_memory_models import MemoryDocument, MemoryIndexEntry


class AgentMemoryDocumentRepository(Protocol):
    def read_by_entry(self, entry: MemoryIndexEntry) -> MemoryDocument: ...
