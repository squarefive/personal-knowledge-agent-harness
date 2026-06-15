from __future__ import annotations

from typing import Any

from ..agent_context.agent_profile_memory import AgentMemoryDocumentRepository as MemoryStore
from ..agent_context.agent_profile_memory import AgentMemoryCandidateExtractor as MemoryExtractor
from ..agent_context.agent_profile_memory import AgentMemoryIndexRepository as MemoryIndexStore
from ..events import new_run_id
from ..llm_clients import DeepSeekChatClient as DeepSeekClient
from ..permissions import check_permission, default_approval_callback
from ..agent_context import build_system_prompt
from ..agent_context.conversation_sessions import ToolResultCompactor as ContextCompactor
from ..agent_context.conversation_sessions import ConversationSessionMetadataRepository as SessionMetadataStore
from ..agent_context.conversation_sessions import ConversationTranscriptRepository as SessionTranscript
from ..tool_runtime import ToolDispatcher
from ..agent_tools.qa_knowledge_tools import QAKnowledgeToolHandlers as KnowledgeTools
from .agent_llm_call_runner import LLMCallStep
from .agent_event_emitter import AgentEventEmitter, EventSink
from ..agent_context.agent_profile_memory.agent_memory_turn_finalizer import TurnMemoryFinalizer
from .agent_answer_finalizer import AnswerFinishStep
from .agent_llm_message_formatter import format_assistant_tool_call_message, format_tool_result_message
from ..agent_context.agent_turn_context_loader import TurnContextLoader
from .agent_runtime_message_recorder import RuntimeMessageRecorder
from .agent_tool_call_runner import ToolCallStep


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
        permission_checker=None,
        approval_callback=None,
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
            permission_checker=permission_checker or check_permission,
            approval_callback=approval_callback or default_approval_callback,
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
        turn_start_index = len(self.messages)
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


AgentLoopRunner = AgentLoop
