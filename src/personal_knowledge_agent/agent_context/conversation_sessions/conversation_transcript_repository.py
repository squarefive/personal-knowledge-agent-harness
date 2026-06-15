from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .conversation_session_metadata_repository import utc_now, validate_session_id

FIRST_EVENT_ID_INCREMENT = 1
UNKNOWN_EVENT_ID = 0


class ConversationTranscriptRepository:
    def __init__(self, root: str | Path, *, session_id: str = "default"):
        self.root = Path(root)
        self.session_id = validate_session_id(session_id)
        self.session_dir = self.root / ".sessions" / self.session_id
        self.path = self.session_dir / "transcript.jsonl"

    def append_message(self, message: dict[str, Any]) -> int:
        event_id = self.event_count() + FIRST_EVENT_ID_INCREMENT
        self.session_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "event_id": event_id,
            "type": "message",
            "created_at": utc_now(),
            "message": message,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
        return event_id

    def load_messages(self) -> list[dict[str, Any]]:
        return [
            event["message"]
            for event in self.load_events()
            if event.get("type") == "message" and isinstance(event.get("message"), dict)
        ]

    def load_events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            events.append(json.loads(line))
        return events

    def event_count(self) -> int:
        return len(self.load_events())

    def load_display_messages(self) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for event in self.load_events():
            message = event.get("message")
            if event.get("type") != "message" or not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if role not in {"user", "assistant"} or not isinstance(content, str):
                continue
            if role == "assistant" and (message.get("tool_calls") or message.get("tool_call_id")):
                continue
            messages.append(
                {
                    "role": role,
                    "content": content,
                    "created_at": event.get("created_at", ""),
                    "event_id": event.get("event_id", UNKNOWN_EVENT_ID),
                }
            )
        return messages
