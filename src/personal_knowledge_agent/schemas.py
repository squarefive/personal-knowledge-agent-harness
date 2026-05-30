from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QACard:
    id: str
    question: str
    answer: str
    summary: str
    keywords: list[str]
    source_type: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SearchResult:
    card_id: str
    question: str
    summary: str
    answer_snippet: str
    score: int
    source_type: str
    created_at: str


@dataclass(frozen=True)
class MemoryIndexEntry:
    name: str
    type: str
    description: str
    path: str


@dataclass(frozen=True)
class MemoryIndex:
    entries: list[MemoryIndexEntry] = field(default_factory=list)


@dataclass(frozen=True)
class MemoryDocument:
    name: str
    type: str
    description: str
    path: str
    updated_at: str
    source_type: str
    source_ref: str | None
    content: str


@dataclass(frozen=True)
class SessionSummary:
    current_goal: str = ""
    confirmed_decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CompactRecord:
    artifact_path: str
    summary: str
    relevance: str
    must_keep: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
