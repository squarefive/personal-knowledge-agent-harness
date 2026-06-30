from __future__ import annotations

import json
from typing import Any, TextIO

from ...agent_runtime import AgentEvent
from .constants import CliConstants as cli_constants


class CliEventRenderer:
    def __init__(self, *, stream: TextIO, max_text_length: int = cli_constants.DEFAULT_MAX_TEXT_LENGTH):
        self.stream = stream
        self.max_text_length = max_text_length
        self._answer_parts: list[str] = []
        self._answer_open = False

    def render(self, event: AgentEvent) -> None:
        if event.event_type == "answer_delta":
            self._write_answer_delta(str(event.payload.get("text", "")))
            return

        if event.event_type == "final_answer_generated":
            self._finish_answer(str(event.payload.get("answer", "")))
            return

        payload = self._truncate(event.payload)
        if event.event_type == "user_input_received":
            self._section("User Input")
            self._write(payload.get("user_input", ""))
        elif event.event_type == "llm_call_started":
            self._write(f"[LLM] {payload.get('stage', cli_constants.DEFAULT_EVENT_STAGE)} started")
        elif event.event_type == "llm_call_finished":
            status = payload.get("status", cli_constants.DEFAULT_EVENT_STATUS)
            self._write(f"[LLM] {payload.get('stage', cli_constants.DEFAULT_EVENT_STAGE)} finished ({status})")
        elif event.event_type == "tool_call_started":
            self._section(f"Tool Call: {payload.get('tool_name', cli_constants.DEFAULT_EVENT_STAGE)}")
            self._dump(payload.get("input", {}))
        elif event.event_type == "tool_call_finished":
            tool_name = payload.get("tool_name", cli_constants.DEFAULT_EVENT_STAGE)
            duration_ms = payload.get("duration_ms")
            suffix = f" in {duration_ms}ms" if duration_ms is not None else ""
            self._section(f"Tool Result: {tool_name}{suffix}")
            self._dump(payload.get("output", {}))
        elif event.event_type == "evidence_checked":
            self._write(f"[Evidence] {payload.get('status', cli_constants.DEFAULT_EVIDENCE_STATUS)}")
        elif event.event_type == "memory_candidates_generated":
            self._section("Memory Candidates")
            self._dump(payload.get("candidates", []))
        elif event.event_type == "error":
            self._write(f"[Error] {payload.get('message', 'unknown error')}")

    def _section(self, title: str) -> None:
        self._write(f"\n-- {title}")

    def _write(self, text: Any) -> None:
        print(text, file=self.stream)

    def _write_raw(self, text: str, *, end: str = "") -> None:
        print(text, end=end, file=self.stream, flush=True)

    def _dump(self, value: Any) -> None:
        self._write(json.dumps(value, ensure_ascii=False, indent=2))

    def _write_answer_delta(self, text: str) -> None:
        if not text:
            return
        if not self._answer_open:
            self._section("Final Answer")
            self._answer_open = True
        self._answer_parts.append(text)
        self._write_raw(text)

    def _finish_answer(self, answer: str) -> None:
        streamed_answer = "".join(self._answer_parts)
        if not streamed_answer:
            self._section("Final Answer")
            self._write(answer)
        elif streamed_answer != answer:
            self._write_raw("\n")
            self._section("Final Answer (verified)")
            self._write(answer)
        else:
            self._write_raw("\n")
        self._answer_parts = []
        self._answer_open = False

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
        return (
            f"{value[: self.max_text_length - len(cli_constants.TEXT_ELLIPSIS)]}"
            f"{cli_constants.TEXT_ELLIPSIS}"
        )
