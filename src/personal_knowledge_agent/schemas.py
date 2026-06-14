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
    category: str
    source_type: str
    created_at: str
    updated_at: str
    is_vectorized: int = 0


@dataclass(frozen=True)
class SearchResult:
    card_id: str
    question: str
    summary: str
    answer_snippet: str
    score: int
    source_type: str
    created_at: str
    category: str


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
class SessionMetadata:
    session_id: str
    created_at: str
    updated_at: str
    cwd: str
    model: str
    transcript_path: str
    summary_path: str
    artifacts_dir: str
    title: str = "新会话"
    title_source: str = "auto"
    last_user_message: str | None = None
    event_count: int = 0
    message_count: int = 0
    compacted_until_event_id: int = 0
    summary_status: str = "none"
    summary_attempts: int = 0
    last_restore_mode: str = "full"
    summary_error: str | None = None


@dataclass(frozen=True)
class CompactRecord:
    artifact_path: str
    summary: str
    relevance: str
    must_keep: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SessionRestoreResult:
    messages: list[dict[str, Any]]
    mode: str
    summary: str | None = None
    warning: str | None = None


@dataclass(frozen=True)
class MemoryCandidate:
    name: str
    type: str
    description: str
    content: str
    source_type: str
    source_ref: str | None
    confidence: str
    write_policy: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
