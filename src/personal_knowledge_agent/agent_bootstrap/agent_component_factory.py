from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from ..agent_context.agent_profile_memory import (
    AgentMemoryCandidateExtractor,
    AgentMemoryDocumentRepository,
    AgentMemoryIndexRepository,
)
from ..agent_context.conversation_sessions import (
    ConversationSessionMetadataRepository,
    ConversationSessionRestorer,
    ConversationSessionSummarizer,
    ConversationTranscriptRepository,
)
from ..agent_runtime import AgentEvent, AgentLoopRunner
from ..agent_tools.agent_memory_tools import AgentMemoryToolHandlers
from ..agent_tools.qa_knowledge_tools import QAKnowledgeToolHandlers
from ..agent_tools.todo_tools import TodoToolHandlers
from ..llm_clients import DeepSeekChatClient
from ..tool_runtime import ApprovalRequest, ToolDispatcher
from .agent_runtime_config import AgentConfig


class QACardStore(Protocol):
    pass


class TodoStore(Protocol):
    pass


class SemanticIndex(Protocol):
    pass


@dataclass(frozen=True)
class AgentComponents:
    agent: AgentLoopRunner
    tools: QAKnowledgeToolHandlers
    todo_tools: TodoToolHandlers


def create_agent_components(
    config: AgentConfig,
    event_sink: Callable[[AgentEvent], None] | None = None,
    approval_callback: Callable[[ApprovalRequest], bool] | None = None,
    session_id: str = "default",
    qa_store: QACardStore | None = None,
    todo_store: TodoStore | None = None,
    llm_provider_user_id: str | None = None,
    semantic_index: SemanticIndex | None = None,
    enable_semantic_index: bool = True,
    transcript: Any | None = None,
    metadata_store: Any | None = None,
    context_compactor: Any | None = None,
    runtime_context_compactor: Any | None = None,
    runtime_context_compactor_factory: Callable[[ConversationSessionSummarizer], Any] | None = None,
    memory_index_store: Any | None = None,
    memory_store: Any | None = None,
) -> AgentComponents:
    store = _required_component(qa_store, "qa_store")
    resolved_todo_store = _required_component(todo_store, "todo_store")
    llm = DeepSeekChatClient(
        api_key=config.deepseek_api_key,
        model=config.deepseek_model,
        llm_provider_user_id=llm_provider_user_id,
    )
    resolved_transcript = _required_component(transcript, "transcript")
    resolved_metadata_store = _required_component(metadata_store, "metadata_store")
    summarizer = ConversationSessionSummarizer(llm)
    restore_result = ConversationSessionRestorer(
        transcript=resolved_transcript,
        metadata_store=resolved_metadata_store,
        summarizer=summarizer,
    ).restore()
    resolved_memory_index_store = _required_component(memory_index_store, "memory_index_store")
    resolved_memory_store = _required_component(memory_store, "memory_store")
    resolved_semantic_index = semantic_index if enable_semantic_index else None
    tools = QAKnowledgeToolHandlers(store, semantic_index=resolved_semantic_index)
    todo_tools = TodoToolHandlers(resolved_todo_store)
    memory_tools = AgentMemoryToolHandlers(
        memory_index_repository=resolved_memory_index_store,
        memory_document_repository=resolved_memory_store,
    )
    dispatcher = ToolDispatcher(tools, memory_tools, todo_tools=todo_tools)
    resolved_runtime_context_compactor = runtime_context_compactor
    if resolved_runtime_context_compactor is None and runtime_context_compactor_factory is not None:
        resolved_runtime_context_compactor = runtime_context_compactor_factory(summarizer)
    agent = AgentLoopRunner(
        llm=llm,
        dispatcher=dispatcher,
        memory_index_store=resolved_memory_index_store,
        memory_store=resolved_memory_store,
        messages=restore_result.messages,
        transcript=resolved_transcript,
        metadata_store=resolved_metadata_store,
        context_compactor=context_compactor,
        runtime_context_compactor=resolved_runtime_context_compactor,
        session_summary=restore_result.summary,
        context_window_tokens=config.context_window_tokens,
        memory_extractor=AgentMemoryCandidateExtractor(),
        approval_callback=approval_callback if approval_callback is not None else None,
        event_sink=event_sink,
    )
    return AgentComponents(agent=agent, tools=tools, todo_tools=todo_tools)


def create_agent(
    config: AgentConfig,
    event_sink: Callable[[AgentEvent], None] | None = None,
    approval_callback: Callable[[ApprovalRequest], bool] | None = None,
    session_id: str = "default",
) -> AgentLoopRunner:
    return create_agent_components(
        config,
        event_sink=event_sink,
        approval_callback=approval_callback,
        session_id=session_id,
    ).agent


def _required_component(component: Any | None, name: str) -> Any:
    if component is None:
        raise ValueError(f"{name} is required for cloud-only Agent runtime")
    return component
