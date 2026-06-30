from dataclasses import dataclass, field
from typing import Any

from .constants import ConversationSessionConstants as session_constants


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
    title: str = session_constants.DEFAULT_SESSION_TITLE
    title_source: str = session_constants.TITLE_SOURCE_AUTO
    last_user_message: str | None = None
    event_count: int = 0
    message_count: int = 0
    compacted_until_event_id: int = 0
    summary_status: str = session_constants.SUMMARY_STATUS_NONE
    summary_attempts: int = 0
    last_restore_mode: str = session_constants.RESTORE_MODE_FULL
    summary_error: str | None = None
    last_prompt_usage_ratio: float | None = None


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
