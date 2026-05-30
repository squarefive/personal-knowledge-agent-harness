from __future__ import annotations

import json
from typing import Any, TextIO

from .events import AgentEvent


class CliRenderer:
    def __init__(self, *, stream: TextIO, max_text_length: int = 240):
        self.stream = stream
        self.max_text_length = max_text_length

    def render(self, event: AgentEvent) -> None:
        if event.event_type == "final_answer_generated":
            self._section("Final Answer")
            self._write(event.payload.get("answer", ""))
            return

        payload = self._truncate(event.payload)
        if event.event_type == "user_input_received":
            self._section("User Input")
            self._write(payload.get("user_input", ""))
        elif event.event_type == "llm_call_started":
            self._write(f"[LLM] {payload.get('stage', 'unknown')} started")
        elif event.event_type == "llm_call_finished":
            status = payload.get("status", "success")
            self._write(f"[LLM] {payload.get('stage', 'unknown')} finished ({status})")
        elif event.event_type == "tool_call_started":
            self._section(f"Tool Call: {payload.get('tool_name', 'unknown')}")
            self._dump(payload.get("input", {}))
        elif event.event_type == "tool_call_finished":
            tool_name = payload.get("tool_name", "unknown")
            duration_ms = payload.get("duration_ms")
            suffix = f" in {duration_ms}ms" if duration_ms is not None else ""
            self._section(f"Tool Result: {tool_name}{suffix}")
            self._dump(payload.get("output", {}))
        elif event.event_type == "evidence_checked":
            self._write(f"[Evidence] {payload.get('status', 'completed')}")
        elif event.event_type == "error":
            self._write(f"[Error] {payload.get('message', 'unknown error')}")

    def _section(self, title: str) -> None:
        self._write(f"\n-- {title}")

    def _write(self, text: Any) -> None:
        print(text, file=self.stream)

    def _dump(self, value: Any) -> None:
        self._write(json.dumps(value, ensure_ascii=False, indent=2))

    def _truncate(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._truncate_text(value)
        if isinstance(value, list):
            return [self._truncate(item) for item in value]
        if isinstance(value, dict):
            return {key: self._truncate(item) for key, item in value.items()}
        return value

    def _truncate_text(self, value: str) -> str:
        if len(value) <= self.max_text_length:
            return value
        return f"{value[: self.max_text_length - 3]}..."
