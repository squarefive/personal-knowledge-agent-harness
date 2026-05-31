from __future__ import annotations

from typing import Any

from ..agent_memory.document_store import MemoryStore
from ..agent_memory.extract_memory_candidates import MemoryExtractor
from ..agent_memory.index_store import MemoryIndexStore
from ..events import new_run_id
from ..llm_client import DeepSeekClient
from ..prompt_builder import build_system_prompt
from ..session_memory.compact_tool_result import ContextCompactor
from ..session_memory.metadata import SessionMetadataStore
from ..session_memory.transcript import SessionTranscript
from ..tools.dispatch_tool_call import ToolDispatcher
from ..tools.knowledge_tools import KnowledgeTools
from .call_llm import LLMCallStep
from .emit_agent_events import AgentEventEmitter, EventSink
from .finalize_turn_memory import TurnMemoryFinalizer
from .finish_answer import AnswerFinishStep
from .format_llm_messages import format_assistant_tool_call_message, format_tool_result_message
from .load_turn_context import TurnContextLoader
from .record_runtime_messages import RuntimeMessageRecorder
from .run_tool_call import ToolCallStep


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
        self.context_compactor = context_compactor
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
        self.llm_call_step = LLMCallStep(llm=self.llm, emit=self.event_emitter.emit)
        self.tool_call_step = ToolCallStep(
            dispatcher=self.dispatcher,
            context_compactor=self.context_compactor,
            emit=self.event_emitter.emit,
        )
        self.answer_finish_step = AnswerFinishStep(
            append_message=self.message_recorder.append,
            turn_memory_finalizer=TurnMemoryFinalizer(self.memory_extractor),
            emit=self.event_emitter.emit,
        )

    @property
    def messages(self) -> list[dict[str, Any]]:
        return self.message_recorder.messages

    def run(self, user_input: str) -> str:
        run_id = new_run_id()
        user_message = {"role": "user", "content": user_input}
        self.message_recorder.append(user_message)
        turn_context = self.turn_context_loader.load(
            user_input=user_input,
            recent_messages=self.messages[-12:],
        )
        system_prompt = build_system_prompt(
            memory_index=turn_context.memory_index,
            selected_memories=turn_context.selected_memories,
        )
        tool_definitions = self.tools.definitions()
        self.event_emitter.emit(run_id, "user_input_received", user_input=user_input)

        for turn in range(self.max_turns):
            response = self.llm_call_step.run(
                run_id=run_id,
                turn=turn,
                messages=self.messages,
                tools=tool_definitions,
                system_prompt=system_prompt,
            )
            if not response.tool_calls:
                return self.answer_finish_step.finish(
                    run_id=run_id,
                    turn=turn,
                    user_input=user_input,
                    answer=response.text or "",
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
