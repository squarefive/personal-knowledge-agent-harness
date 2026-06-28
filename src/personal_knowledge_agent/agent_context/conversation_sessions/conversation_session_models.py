from dataclasses import dataclass, field
from typing import Any


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
class RuntimeCompactionResult:
    messages: list[dict[str, Any]]
    session_summary: str
    mode: str
    warning: str | None = None
