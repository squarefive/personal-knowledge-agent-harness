from __future__ import annotations

from typing import Any

from ..agent_context.agent_profile_memory import (
    AgentMemoryCandidateExtractor,
    AgentMemoryDocumentRepository,
    AgentMemoryIndexRepository,
    AgentMemoryTurnFinalizer,
)
from ..agent_context import build_system_prompt
from ..agent_context.conversation_sessions import (
    ConversationSessionMetadataRepository,
    ConversationTranscriptRepository,
    RuntimeContextCompactor,
    ToolResultCompactor,
)
from ..llm_clients import DeepSeekChatClient, LLMContextLengthExceeded
from ..tool_runtime import ToolDispatcher, check_permission, default_approval_callback
from .agent_llm_call_runner import AgentLLMCallRunner
from .agent_event_emitter import AgentEventEmitter, EventSink
from .agent_events import new_run_id
from .agent_answer_finalizer import AgentAnswerFinalizer
from .agent_llm_message_formatter import format_assistant_tool_call_message, format_tool_result_message
from ..agent_context.agent_turn_context_loader import TurnContextLoader
from .agent_runtime_message_recorder import RuntimeMessageRecorder
from .agent_tool_call_runner import AgentToolCallRunner


class AgentLoopRunner:
    def __init__(
        self,
        *,
        llm: DeepSeekChatClient,
        dispatcher: ToolDispatcher,
        memory_index_store: AgentMemoryIndexRepository | None = None,
        memory_store: AgentMemoryDocumentRepository | None = None,
        messages: list[dict[str, Any]] | None = None,
        transcript: ConversationTranscriptRepository | None = None,
        metadata_store: ConversationSessionMetadataRepository | None = None,
        context_compactor: ToolResultCompactor | None = None,
        runtime_context_compactor: RuntimeContextCompactor | None = None,
        session_summary: str | None = None,
        context_window_tokens: int = 1_000_000,
        runtime_compact_usage_threshold: float = 0.75,
        memory_extractor: AgentMemoryCandidateExtractor | None = None,
        permission_checker=None,
        approval_callback=None,
        max_turns: int = 8,
        event_sink: EventSink | None = None,
    ):
        self.llm = llm
        self.dispatcher = dispatcher
        self.memory_index_store = memory_index_store
        self.memory_store = memory_store
        self.context_compactor = context_compactor
        self.runtime_context_compactor = runtime_context_compactor
        self.session_summary = session_summary
        self.context_window_tokens = context_window_tokens
        self.runtime_compact_usage_threshold = runtime_compact_usage_threshold
        self.last_prompt_usage_ratio: float | None = None
        self.memory_extractor = memory_extractor
        self.max_turns = max_turns
        self.event_emitter = AgentEventEmitter(event_sink)
        self.message_recorder = RuntimeMessageRecorder(
            messages=messages,
            transcript=transcript,
            metadata_store=metadata_store,
        )
        self.turn_context_loader = TurnContextLoader(
            memory_index_store=memory_index_store,
            memory_store=memory_store,
        )
        self.llm_call_step = AgentLLMCallRunner(llm=self.llm, emit=self.event_emitter.emit)
        self.tool_call_step = AgentToolCallRunner(
            dispatcher=self.dispatcher,
            context_compactor=self.context_compactor,
            permission_checker=permission_checker or check_permission,
            approval_callback=approval_callback or default_approval_callback,
            emit=self.event_emitter.emit,
        )
        self.answer_finish_step = AgentAnswerFinalizer(
            append_message=self.message_recorder.append,
            turn_memory_finalizer=AgentMemoryTurnFinalizer(self.memory_extractor),
            emit=self.event_emitter.emit,
        )

    @property
    def messages(self) -> list[dict[str, Any]]:
        return self.message_recorder.messages

    def run(self, user_input: str) -> str:
        run_id = new_run_id()
        turn_start_index = len(self.messages)
        user_message = {"role": "user", "content": user_input}
        self.message_recorder.append(user_message)
        self.event_emitter.emit(run_id, "user_input_received", user_input=user_input)
        if self._should_compact_before_llm_call():
            self._apply_runtime_compaction(run_id=run_id, reason="usage_threshold")
            turn_start_index = 0
        turn_context = self.turn_context_loader.load(
            user_input=user_input,
            recent_messages=self.messages[-12:],
        )
        system_prompt = build_system_prompt(
            memory_index=turn_context.memory_index,
            selected_memories=turn_context.selected_memories,
            session_summary=self.session_summary,
        )
        tool_definitions = self.dispatcher.definitions()

        for turn in range(self.max_turns):
            response, compacted_during_llm = self._run_llm_with_context_limit_retry(
                run_id=run_id,
                turn=turn,
                tool_definitions=tool_definitions,
                system_prompt=system_prompt,
                turn_context=turn_context,
            )
            if compacted_during_llm:
                turn_start_index = 0
                system_prompt = build_system_prompt(
                    memory_index=turn_context.memory_index,
                    selected_memories=turn_context.selected_memories,
                    session_summary=self.session_summary,
                )
            self._update_prompt_usage_ratio(run_id, response)
            if not response.tool_calls:
                return self.answer_finish_step.finish(
                    run_id=run_id,
                    turn=turn,
                    user_input=user_input,
                    answer=response.text or "",
                    turn_messages=self.messages[turn_start_index:],
                    memory_index=turn_context.memory_index,
                    recent_messages=self.messages[-12:],
                )

            self.message_recorder.append(format_assistant_tool_call_message(response))
            for tool_call in response.tool_calls:
                tool_result = self.tool_call_step.run(run_id=run_id, turn=turn, tool_call=tool_call)
                self.message_recorder.append(
                    format_tool_result_message(
                        tool_call_id=tool_call.id,
                        result=tool_result.result,
                        compact_record=tool_result.compact_record,
                    )
                )

        return self.answer_finish_step.stop_for_too_many_tool_calls(
            run_id=run_id,
            user_input=user_input,
            memory_index=turn_context.memory_index,
            recent_messages=self.messages[-12:],
        )

    def _run_llm_with_context_limit_retry(
        self,
        *,
        run_id: str,
        turn: int,
        tool_definitions: list[dict[str, Any]],
        system_prompt: str,
        turn_context,
    ):
        try:
            return (
                self.llm_call_step.run(
                    run_id=run_id,
                    turn=turn,
                    messages=self.messages,
                    tools=tool_definitions,
                    system_prompt=system_prompt,
                ),
                False,
            )
        except LLMContextLengthExceeded:
            if self.runtime_context_compactor is None:
                raise
            self._apply_runtime_compaction(run_id=run_id, reason="context_length_exceeded")
            retry_system_prompt = build_system_prompt(
                memory_index=turn_context.memory_index,
                selected_memories=turn_context.selected_memories,
                session_summary=self.session_summary,
            )
            return (
                self.llm_call_step.run(
                    run_id=run_id,
                    turn=turn,
                    messages=self.messages,
                    tools=tool_definitions,
                    system_prompt=retry_system_prompt,
                ),
                True,
            )

    def _should_compact_before_llm_call(self) -> bool:
        if self.runtime_context_compactor is None or self.last_prompt_usage_ratio is None:
            return False
        return self.last_prompt_usage_ratio >= self.runtime_compact_usage_threshold

    def _apply_runtime_compaction(self, *, run_id: str, reason: str) -> None:
        if self.runtime_context_compactor is None:
            return
        previous_prompt_usage_ratio = self.last_prompt_usage_ratio
        self.event_emitter.emit(
            run_id,
            "runtime_context_compaction_started",
            reason=reason,
            prompt_usage_ratio=previous_prompt_usage_ratio,
            threshold=self.runtime_compact_usage_threshold,
        )
        result = self.runtime_context_compactor.compact(
            self.messages,
            existing_summary=self.session_summary,
        )
        self.message_recorder.messages = result.messages
        self.session_summary = result.session_summary
        self.last_prompt_usage_ratio = None
        self.event_emitter.emit(
            run_id,
            "runtime_context_compaction_finished",
            reason=reason,
            prompt_usage_ratio=previous_prompt_usage_ratio,
            threshold=self.runtime_compact_usage_threshold,
            mode=result.mode,
        )

    def _update_prompt_usage_ratio(self, run_id: str, response) -> None:
        if response.usage is None or response.usage.prompt_tokens is None:
            return
        self.last_prompt_usage_ratio = response.usage.prompt_tokens / self.context_window_tokens
        self.event_emitter.emit(
            run_id,
            "prompt_usage_updated",
            prompt_usage_ratio=self.last_prompt_usage_ratio,
        )
