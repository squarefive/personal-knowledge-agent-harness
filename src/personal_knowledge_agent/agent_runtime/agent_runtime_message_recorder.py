from __future__ import annotations

from typing import Any

from ..agent_context.conversation_sessions import ConversationSessionMetadataRepository as SessionMetadataStore
from ..agent_context.conversation_sessions import ConversationTranscriptRepository as SessionTranscript


class RuntimeMessageRecorder:
    def __init__(
        self,
        *,
        messages: list[dict[str, Any]] | None = None,
        transcript: SessionTranscript | None = None,
        metadata_store: SessionMetadataStore | None = None,
    ):
        self.messages = messages if messages is not None else []
        self.transcript = transcript
        self.metadata_store = metadata_store

    def append(self, message: dict[str, Any]) -> None:
        self.messages.append(message)
        if self.transcript is not None:
            try:
                self.transcript.append_message(message)
            except Exception:
                pass
        self._update_metadata_counts(message)

    def _update_metadata_counts(self, message: dict[str, Any]) -> None:
        if self.metadata_store is None:
            return
        try:
            event_count = self.transcript.event_count() if self.transcript is not None else 0
            if self.transcript is not None:
                message_count = len(self.transcript.load_messages())
            else:
                message_count = len(self.messages)
            if message.get("role") == "user" and isinstance(message.get("content"), str):
                self.metadata_store.update_after_user_message(
                    message["content"],
                    event_count=event_count,
                    message_count=message_count,
                )
                return
            self.metadata_store.update_counts(event_count=event_count, message_count=message_count)
        except Exception:
            pass
