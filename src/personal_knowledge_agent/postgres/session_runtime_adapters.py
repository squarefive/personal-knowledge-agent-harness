from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..agent_context.conversation_sessions import CompactRecord, RuntimeCompactionResult, SessionMetadata, utc_now
from ..agent_context.conversation_sessions.session_utils import (
    DEFAULT_SESSION_TITLE,
    _recent_messages,
    _recovery_notice,
    _summary,
    _summary_input,
)
from .session_repository import ConversationSessionRecord, PostgresConversationSessionRepository

DEFAULT_TOOL_RESULT_THRESHOLD_CHARS = 8000
DEFAULT_RECENT_MESSAGES_COUNT = 12
SESSION_TITLE_PREVIEW_CHARS = 30


class PostgresConversationTranscriptAdapter:
    """Adapts PostgreSQL conversation messages to the runtime transcript interface."""

    def __init__(self, repository: PostgresConversationSessionRepository, session_id: str) -> None:
        self._repository = repository
        self.session_id = session_id

    def append_message(self, message: dict[str, Any]) -> int:
        return self._repository.append_message(self.session_id, message)

    def load_messages(self) -> list[dict[str, Any]]:
        return self._repository.load_messages(self.session_id)

    def event_count(self) -> int:
        return self._repository.count_messages(self.session_id)


class PostgresSessionMetadataAdapter:
    """Adapts PostgreSQL conversation session rows to SessionMetadata consumers."""

    def __init__(
        self,
        repository: PostgresConversationSessionRepository,
        session_id: str,
        *,
        model: str = "",
    ) -> None:
        self._repository = repository
        self.session_id = session_id
        self.model = model
        self.root = Path("/")

    def load_or_create(self) -> SessionMetadata:
        record = self._load_or_create_record()
        return self._metadata(record)

    def update_counts(
        self,
        *,
        event_count: int,
        message_count: int,
        summary_status: str | None = None,
        summary_attempts: int | None = None,
        last_restore_mode: str | None = None,
        summary_error: str | None = None,
        compacted_until_event_id: int | None = None,
    ) -> SessionMetadata:
        metadata = self.load_or_create()
        return SessionMetadata(
            **{
                **asdict(metadata),
                "updated_at": utc_now(),
                "event_count": event_count,
                "message_count": message_count,
                "summary_status": summary_status if summary_status is not None else metadata.summary_status,
                "summary_attempts": summary_attempts if summary_attempts is not None else metadata.summary_attempts,
                "last_restore_mode": last_restore_mode if last_restore_mode is not None else metadata.last_restore_mode,
                "summary_error": summary_error,
                "compacted_until_event_id": (
                    compacted_until_event_id
                    if compacted_until_event_id is not None
                    else metadata.compacted_until_event_id
                ),
            }
        )

    def update_after_user_message(
        self,
        message: str,
        *,
        event_count: int,
        message_count: int,
    ) -> SessionMetadata:
        record = self._load_or_create_record()
        normalized_message = " ".join(message.strip().split())
        if record.title is None and normalized_message:
            record = self._repository.rename_session(
                self.session_id,
                normalized_message[:SESSION_TITLE_PREVIEW_CHARS],
            ) or record
        metadata = self._metadata(record)
        return SessionMetadata(
            **{
                **asdict(metadata),
                "last_user_message": normalized_message or None,
                "event_count": event_count,
                "message_count": message_count,
                "updated_at": utc_now(),
            }
        )

    def update_summary(self, summary: str | None) -> bool:
        return self._repository.update_summary(self.session_id, summary)

    def _load_or_create_record(self) -> ConversationSessionRecord:
        record = self._repository.get_session(self.session_id)
        if record is not None:
            return record
        return self._repository.create_session(session_id=self.session_id)

    def _metadata(self, record: ConversationSessionRecord) -> SessionMetadata:
        count = self._repository.count_messages(self.session_id)
        return SessionMetadata(
            session_id=record.session_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            cwd="postgres",
            model=self.model,
            transcript_path=f"postgres://conversation_sessions/{record.session_id}/messages",
            summary_path=f"postgres://conversation_sessions/{record.session_id}/summary",
            artifacts_dir="",
            title=record.title or DEFAULT_SESSION_TITLE,
            title_source="user" if record.title else "auto",
            event_count=count,
            message_count=count,
            summary_status="valid" if record.summary else "none",
        )


class InMemoryToolResultCompactor:
    """Compacts long tool results without writing local artifact files."""

    def __init__(self, *, threshold_chars: int = DEFAULT_TOOL_RESULT_THRESHOLD_CHARS) -> None:
        self.threshold_chars = threshold_chars

    def compact_tool_result(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        result_text: str,
    ) -> CompactRecord | None:
        if len(result_text) <= self.threshold_chars:
            return None
        return CompactRecord(
            artifact_path="",
            summary=_summary(tool_name, result_text),
            relevance=(
                f"该 tool result 来自 {tool_name}，因长度超过阈值已在当前上下文中压缩摘要，"
                "未写入本地文件。"
            ),
            must_keep=[],
        )


class PostgresRuntimeContextCompactor:
    """Stores runtime session summaries in PostgreSQL instead of local summary files."""

    def __init__(
        self,
        repository: PostgresConversationSessionRepository,
        session_id: str,
        *,
        summarizer: Any,
        recent_messages_count: int = DEFAULT_RECENT_MESSAGES_COUNT,
    ) -> None:
        self._repository = repository
        self.session_id = session_id
        self.summarizer = summarizer
        self.recent_messages_count = recent_messages_count

    def compact(
        self,
        messages: list[dict[str, Any]],
        *,
        existing_summary: str | None = None,
    ) -> RuntimeCompactionResult:
        summary_input = _summary_input(messages, existing_summary)
        try:
            summary, _attempts = self.summarizer.summarize(summary_input)
        except Exception as exc:
            notice = _recovery_notice(str(exc), self.recent_messages_count)
            return RuntimeCompactionResult(
                messages=_recent_messages(messages, self.recent_messages_count),
                session_summary=notice,
                mode="recent_with_recovery_notice",
                warning=notice,
            )

        self._repository.update_summary(self.session_id, summary)
        return RuntimeCompactionResult(
            messages=_recent_messages(messages, self.recent_messages_count),
            session_summary=summary,
            mode="summary_plus_recent",
        )
