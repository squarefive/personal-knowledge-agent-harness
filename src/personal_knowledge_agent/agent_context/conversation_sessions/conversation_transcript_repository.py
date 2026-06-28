from __future__ import annotations

from typing import Any, Protocol


class ConversationTranscriptRepository(Protocol):
    def append_message(self, message: dict[str, Any]) -> int: ...

    def load_messages(self) -> list[dict[str, Any]]: ...

    def event_count(self) -> int: ...
