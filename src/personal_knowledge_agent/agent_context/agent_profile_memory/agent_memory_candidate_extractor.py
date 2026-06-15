from __future__ import annotations

import re
from typing import Any

from .agent_memory_models import MemoryCandidate, MemoryIndex

USER_PREFERENCE_MARKERS = ("记住", "以后", "每次", "总是")
PROJECT_DECISION_MARKERS = ("决定", "确认", "必须", "不要", "不允许")


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
        if _contains_any(user_input, USER_PREFERENCE_MARKERS):
            candidates.append(
                MemoryCandidate(
                    name=_candidate_name("user-preference", user_input),
                    type="user",
                    description=_first_sentence(user_input),
                    content=user_input.strip(),
                    source_type="user_explicit",
                    source_ref=None,
                    confidence="high",
                    write_policy="needs_confirmation",
                )
            )
        if _contains_any(user_input, PROJECT_DECISION_MARKERS) and _looks_project_related(
            user_input,
            recent_messages,
        ):
            candidates.append(
                MemoryCandidate(
                    name=_candidate_name("project-decision", user_input),
                    type="project",
                    description=_first_sentence(user_input),
                    content=user_input.strip(),
                    source_type="user_decision",
                    source_ref=None,
                    confidence="high",
                    write_policy="auto_write",
                )
            )
        return _dedupe_against_index(candidates, memory_index)


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


def _looks_project_related(value: str, recent_messages: list[dict[str, Any]] | None) -> bool:
    project_markers = ("项目", "Agent", "agent", "Q&A", "memory", "记忆", "上下文", "工具", "SQLite")
    if _contains_any(value, project_markers):
        return True
    if not recent_messages:
        return False
    session_text = " ".join(_message_text(message) for message in recent_messages)
    return _contains_any(session_text, project_markers)


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    return str(content)


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
