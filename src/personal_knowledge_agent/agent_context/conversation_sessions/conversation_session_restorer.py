from __future__ import annotations

import json

from .conversation_session_metadata_repository import ConversationSessionMetadataRepository
from .conversation_session_models import SessionRestoreResult
from .conversation_session_summarizer import ConversationSessionSummarizer
from .conversation_transcript_repository import ConversationTranscriptRepository
from .session_utils import _recent_messages, _recovery_notice


class ConversationSessionRestorer:
    def __init__(
        self,
        *,
        transcript: ConversationTranscriptRepository,
        metadata_store: ConversationSessionMetadataRepository,
        summarizer: ConversationSessionSummarizer | None = None,
        message_budget_chars: int = 120_000,
        first_messages_count: int = 6,
        recent_messages_count: int = 12,
    ):
        self.transcript = transcript
        self.metadata_store = metadata_store
        self.summarizer = summarizer
        self.message_budget_chars = message_budget_chars
        self.first_messages_count = first_messages_count
        self.recent_messages_count = recent_messages_count

    def restore(self) -> SessionRestoreResult:
        self.metadata_store.load_or_create()
        messages = self.transcript.load_messages()
        if _estimated_chars(messages) <= self.message_budget_chars:
            self.metadata_store.update_counts(
                event_count=self.transcript.event_count(),
                message_count=len(messages),
                last_restore_mode="full",
            )
            return SessionRestoreResult(messages=messages, mode="full")

        if self.summarizer is not None:
            try:
                summary, attempts = self.summarizer.summarize(messages)
                self.metadata_store.update_summary(summary)
                recent = _recent_messages(messages, self.recent_messages_count)
                self.metadata_store.update_counts(
                    event_count=self.transcript.event_count(),
                    message_count=len(messages),
                    summary_status="valid",
                    summary_attempts=attempts,
                    last_restore_mode="summary_plus_recent",
                )
                return SessionRestoreResult(messages=recent, mode="summary_plus_recent", summary=summary)
            except Exception as exc:
                return self._fallback(messages, str(exc))

        return self._fallback(messages, "summarizer is not configured")

    def _fallback(self, messages: list[dict], error: str) -> SessionRestoreResult:
        notice = _recovery_notice(error, self.recent_messages_count, first_count=self.first_messages_count)
        restored = _recent_messages(messages, self.recent_messages_count)
        self.metadata_store.update_counts(
            event_count=self.transcript.event_count(),
            message_count=len(messages),
            summary_status="failed",
            summary_attempts=(self.summarizer.max_retries if self.summarizer is not None else 0),
            last_restore_mode="first_and_recent",
            summary_error=error[:240],
        )
        return SessionRestoreResult(messages=restored, mode="first_and_recent", summary=notice, warning=notice)


def _estimated_chars(messages: list[dict]) -> int:
    return len(json.dumps(messages, ensure_ascii=False))
