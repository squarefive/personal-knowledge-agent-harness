from __future__ import annotations

from typing import Protocol

from .agent_memory_models import MemoryIndex


class AgentMemoryIndexRepository(Protocol):
    def load(self) -> MemoryIndex: ...
