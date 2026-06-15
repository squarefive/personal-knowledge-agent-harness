from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from .agent_memory_candidate_extractor import AgentMemoryCandidateExtractor
from .agent_memory_models import MemoryIndex


class AgentMemoryTurnFinalizer:
    def __init__(self, memory_extractor: AgentMemoryCandidateExtractor | None = None):
        self.memory_extractor = memory_extractor

    def finalize(
        self,
        *,
        run_id: str,
        user_input: str,
        final_answer: str,
        memory_index: MemoryIndex | None,
        recent_messages: list[dict[str, Any]],
        emit: Callable[..., None],
    ) -> None:
        if self.memory_extractor is None:
            return
        candidates = self.memory_extractor.extract(
            user_input=user_input,
            final_answer=final_answer,
            memory_index=memory_index,
            recent_messages=recent_messages,
        )
        if candidates:
            emit(
                run_id,
                "memory_candidates_generated",
                candidates=[asdict(candidate) for candidate in candidates],
            )
