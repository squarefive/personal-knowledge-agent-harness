from __future__ import annotations

from typing import Protocol

from .conversation_session_models import SessionMetadata
from .session_utils import DEFAULT_SESSION_TITLE, utc_now, validate_session_id


class ConversationSessionMetadataRepository(Protocol):
    def load_or_create(self) -> SessionMetadata: ...

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
    ) -> SessionMetadata: ...

    def update_after_user_message(
        self,
        message: str,
        *,
        event_count: int,
        message_count: int,
    ) -> SessionMetadata: ...

    def update_summary(self, summary: str | None) -> bool: ...
