from __future__ import annotations

from typing import Protocol

from .agent_memory_models import MemoryIndex

AGENT_MEMORY_TYPES = {"user", "feedback", "project", "reference"}


class AgentMemoryIndexRepository(Protocol):
    def load(self) -> MemoryIndex: ...
