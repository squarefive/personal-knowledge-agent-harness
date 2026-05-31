from __future__ import annotations

import json
import time
from dataclasses import asdict
from typing import Any, Callable

from .context_compactor import ContextCompactor
from .events import AgentEvent, new_run_id
from .llm_client import DeepSeekClient
from .memory_extractor import MemoryExtractor
from .memory_index import MemoryIndexStore
from .memory_store import MemoryStore
from .prompt_builder import build_system_prompt
from .schemas import LLMResponse, MemoryDocument, MemoryIndex, MemoryIndexEntry
from .session_metadata import SessionMetadataStore
from .session_transcript import SessionTranscript
from .tool_dispatcher import ToolDispatcher
from .tools import KnowledgeTools

EventSink = Callable[[AgentEvent], None]


class AgentLoop:
    def __init__(
        self,
        *,
        llm: DeepSeekClient,
        tools: KnowledgeTools,
        dispatcher: ToolDispatcher,
        memory_index_store: MemoryIndexStore | None = None,
        memory_store: MemoryStore | None = None,
        messages: list[dict[str, Any]] | None = None,
        transcript: SessionTranscript | None = None,
        metadata_store: SessionMetadataStore | None = None,
        context_compactor: ContextCompactor | None = None,
        memory_extractor: MemoryExtractor | None = None,
        max_turns: int = 8,
        event_sink: EventSink | None = None,
    ):
        self.llm = llm
        self.tools = tools
        self.dispatcher = dispatcher
        self.memory_index_store = memory_index_store
        self.memory_store = memory_store
        self.messages = messages if messages is not None else []
        self.transcript = transcript
        self.metadata_store = metadata_store
        self.context_compactor = context_compactor
        self.memory_extractor = memory_extractor
        self.max_turns = max_turns
        self.event_sink = event_sink

    def run(self, user_input: str) -> str:
        run_id = new_run_id()
        user_message = {"role": "user", "content": user_input}
        self._append_message(user_message)
        memory_index, selected_memories = self._prepare_turn_context(user_input)
        system_prompt = build_system_prompt(
            memory_index=memory_index,
            selected_memories=selected_memories,
        )
        tool_definitions = self.tools.definitions()
        self._emit(run_id, "user_input_received", user_input=user_input)

        for turn in range(self.max_turns):
            self._emit(run_id, "llm_call_started", stage="next_action", turn=turn)
            try:
                response = self.llm.chat(
                    messages=self.messages,
                    tools=tool_definitions,
                    system_prompt=system_prompt,
                )
            except Exception as exc:
                self._emit(
                    run_id,
                    "llm_call_finished",
                    stage="next_action",
                    turn=turn,
                    status="error",
                    error_message=str(exc),
                )
                self._emit(run_id, "error", stage="llm_call", message=str(exc))
                raise
            self._emit(
                run_id,
                "llm_call_finished",
                stage="next_action",
                turn=turn,
                status="success",
                tool_calls_count=len(response.tool_calls),
            )
            if not response.tool_calls:
                answer = response.text or ""
                self._append_message({"role": "assistant", "content": answer})
                self._emit(run_id, "evidence_checked", status="completed", turn=turn)
                self._finalize_turn(
                    run_id=run_id,
                    user_input=user_input,
                    final_answer=answer,
                    memory_index=memory_index,
                )
                self._emit(run_id, "final_answer_generated", answer=answer, turn=turn)
                return answer

            self._append_message(self._assistant_message(response))
            for tool_call in response.tool_calls:
                display_input = self.dispatcher.display_input(tool_call.name, tool_call.arguments)
                self._emit(
                    run_id,
                    "tool_call_started",
                    turn=turn,
                    tool_name=tool_call.name,
                    tool_call_id=tool_call.id,
                    input=display_input,
                )
                started_at = time.monotonic()
                result = self.dispatcher.execute(tool_call)
                duration_ms = int((time.monotonic() - started_at) * 1000)
                compact_record = self._compact_tool_result(
                    run_id=run_id,
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    result=result,
                )
                display_output = self.dispatcher.display_output(tool_call.name, result)
                self._emit(
                    run_id,
                    "tool_call_finished",
                    turn=turn,
                    tool_name=tool_call.name,
                    tool_call_id=tool_call.id,
                    status="success" if result.get("ok") is not False else "error",
                    duration_ms=duration_ms,
                    output=display_output,
                )
                if compact_record is not None:
                    self._emit(
                        run_id,
                        "context_compacted",
                        turn=turn,
                        tool_name=tool_call.name,
                        tool_call_id=tool_call.id,
                        compact_record=asdict(compact_record),
                    )
                self._append_message(
                    self._tool_message(
                        tool_call_id=tool_call.id,
                        result=result,
                        compact_record=compact_record,
                    )
                )

        answer = "工具调用次数过多，已停止本轮处理。"
        self._append_message({"role": "assistant", "content": answer})
        self._emit(run_id, "error", stage="agent_loop", message=answer)
        self._finalize_turn(
            run_id=run_id,
            user_input=user_input,
            final_answer=answer,
            memory_index=memory_index,
        )
        self._emit(run_id, "final_answer_generated", answer=answer)
        return answer

    def _compact_tool_result(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        result: dict[str, Any],
    ):
        if self.context_compactor is None:
            return None
        return self.context_compactor.compact_tool_result(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            result_text=json.dumps(result, ensure_ascii=False),
        )

    def _finalize_turn(
        self,
        *,
        run_id: str,
        user_input: str,
        final_answer: str,
        memory_index: MemoryIndex | None,
    ) -> None:
        if self.memory_extractor is None:
            return
        candidates = self.memory_extractor.extract(
            user_input=user_input,
            final_answer=final_answer,
            memory_index=memory_index,
            recent_messages=self.messages[-12:],
        )
        if candidates:
            self._emit(
                run_id,
                "memory_candidates_generated",
                candidates=[asdict(candidate) for candidate in candidates],
            )

    def _prepare_turn_context(
        self,
        user_input: str,
    ) -> tuple[MemoryIndex | None, list[MemoryDocument]]:
        memory_index = self._load_memory_index()
        if memory_index is None or self.memory_store is None:
            return memory_index, []

        selected_entries = self._select_memory_entries(
            user_input=user_input,
            memory_index=memory_index,
            recent_messages=self.messages[-12:],
        )
        selected_memories: list[MemoryDocument] = []
        for entry in selected_entries:
            try:
                selected_memories.append(self.memory_store.read_by_entry(entry))
            except Exception:
                continue
        return memory_index, selected_memories

    def _load_memory_index(self) -> MemoryIndex | None:
        if self.memory_index_store is None:
            return None
        try:
            return self.memory_index_store.load()
        except Exception:
            return MemoryIndex()

    @staticmethod
    def _select_memory_entries(
        *,
        user_input: str,
        memory_index: MemoryIndex,
        recent_messages: list[dict[str, Any]] | None = None,
        limit: int = 3,
    ) -> list[MemoryIndexEntry]:
        query_parts = [user_input]
        if recent_messages:
            query_parts.extend(_message_text(message) for message in recent_messages)
        query = " ".join(part for part in query_parts if part).lower()
        if not query:
            return []

        scored: list[tuple[int, MemoryIndexEntry]] = []
        for entry in memory_index.entries:
            haystack = " ".join([entry.name, entry.type, entry.description, entry.path]).lower()
            score = 0
            for token in _query_tokens(query):
                if token in haystack:
                    score += 1
            if entry.name.lower() in query:
                score += 2
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    def _emit(self, run_id: str, event_type: str, **payload: Any) -> None:
        if self.event_sink is None:
            return
        self.event_sink(AgentEvent(run_id=run_id, event_type=event_type, payload=payload))

    @staticmethod
    def _assistant_message(response: LLMResponse) -> dict[str, Any]:
        message: dict[str, Any] = {
            "role": "assistant",
            "content": response.text,
            "tool_calls": [],
        }
        for tool_call in response.tool_calls:
            message["tool_calls"].append(
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(tool_call.arguments, ensure_ascii=False),
                    },
                }
            )
        return message

    def _tool_message(
        self,
        *,
        tool_call_id: str,
        result: dict[str, Any],
        compact_record: Any | None,
    ) -> dict[str, Any]:
        content = json.dumps(result, ensure_ascii=False)
        if compact_record is not None:
            content = json.dumps(
                {"ok": result.get("ok", True), "compact_record": asdict(compact_record)},
                ensure_ascii=False,
            )
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }

    def _append_message(self, message: dict[str, Any]) -> None:
        self.messages.append(message)
        if self.transcript is not None:
            try:
                self.transcript.append_message(message)
            except Exception:
                pass
        self._update_metadata_counts()

    def _update_metadata_counts(self) -> None:
        if self.metadata_store is None:
            return
        try:
            event_count = self.transcript.event_count() if self.transcript is not None else 0
            if self.transcript is not None:
                message_count = len(self.transcript.load_messages())
            else:
                message_count = len(self.messages)
            self.metadata_store.update_counts(event_count=event_count, message_count=message_count)
        except Exception:
            pass


def _query_tokens(query: str) -> list[str]:
    return [token for token in query.replace("/", " ").replace("-", " ").split() if token]


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    return str(content)
