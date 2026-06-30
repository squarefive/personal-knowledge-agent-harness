from __future__ import annotations

import re
from typing import Any

from .agent_memory_models import MemoryCandidate, MemoryIndex
from .constants import AgentProfileMemoryConstants as memory_constants


class AgentMemoryCandidateExtractor:
    def extract(
        self,
        *,
        user_input: str,
        final_answer: str,
        memory_index: MemoryIndex | None = None,
        recent_messages: list[dict[str, Any]] | None = None,
    ) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []
        if _contains_any(user_input, memory_constants.USER_PREFERENCE_MARKERS):
            candidates.append(
                MemoryCandidate(
                    name=_candidate_name(memory_constants.MEMORY_CANDIDATE_NAME_PREFIX_USER_PREFERENCE, user_input),
                    type=memory_constants.MEMORY_TYPE_USER,
                    description=_first_sentence(user_input),
                    content=user_input.strip(),
                    source_type=memory_constants.MEMORY_CANDIDATE_SOURCE_TYPE_USER_EXPLICIT,
                    source_ref=None,
                    confidence=memory_constants.MEMORY_CANDIDATE_CONFIDENCE_HIGH,
                    write_policy=memory_constants.MEMORY_CANDIDATE_WRITE_POLICY_NEEDS_CONFIRMATION,
                )
            )
        return _dedupe_against_index(candidates, memory_index)


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


def _candidate_name(prefix: str, content: str) -> str:
    ascii_words = re.findall(r"[A-Za-z0-9]+", content.lower())
    suffix = "-".join(ascii_words[:5])
    if not suffix:
        suffix = str(abs(hash(content)) % 100000)
    return f"{prefix}-{suffix}"


def _first_sentence(value: str) -> str:
    stripped = value.strip()
    for separator in ("。", "\n"):
        if separator in stripped:
            return stripped.split(separator, 1)[0].strip()
    return stripped[:80]


def _dedupe_against_index(
    candidates: list[MemoryCandidate],
    memory_index: MemoryIndex | None,
) -> list[MemoryCandidate]:
    if memory_index is None:
        return candidates
    existing_names = {entry.name for entry in memory_index.entries}
    return [candidate for candidate in candidates if candidate.name not in existing_names]
