from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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
    RuntimeContextCompactor,
    ToolResultCompactor,
)
from ..agent_runtime import AgentEvent, AgentLoopRunner
from ..agent_tools.agent_memory_tools import AgentMemoryToolHandlers
from ..agent_tools.qa_knowledge_tools import QAKnowledgeToolHandlers
from ..llm_clients import DeepSeekChatClient
from ..qa_data_access import QACardRepository, QACardSemanticIndex
from ..tool_runtime import ApprovalRequest, ToolDispatcher
from .agent_runtime_config import AgentConfig


@dataclass(frozen=True)
class AgentComponents:
    agent: AgentLoopRunner
    tools: QAKnowledgeToolHandlers


def create_agent_components(
    config: AgentConfig,
    event_sink: Callable[[AgentEvent], None] | None = None,
    approval_callback: Callable[[ApprovalRequest], bool] | None = None,
    session_id: str = "default",
) -> AgentComponents:
    store = QACardRepository(config.knowledge_db_path)
    workspace_root = Path.cwd()
    llm = DeepSeekChatClient(
        api_key=config.deepseek_api_key,
        model=config.deepseek_model,
    )
    transcript = ConversationTranscriptRepository(workspace_root, session_id=session_id)
    metadata_store = ConversationSessionMetadataRepository(
        workspace_root,
        session_id=session_id,
        model=config.deepseek_model,
    )
    restore_result = ConversationSessionRestorer(
        transcript=transcript,
        metadata_store=metadata_store,
        summarizer=ConversationSessionSummarizer(llm),
    ).restore()
    metadata = metadata_store.load_or_create()
    memory_index_store = AgentMemoryIndexRepository(workspace_root)
    memory_store = AgentMemoryDocumentRepository(workspace_root)
    semantic_index = QACardSemanticIndex(
        dashscope_api_key=config.dashscope_api_key,
        embedding_base_url=config.qwen_embedding_base_url,
        embedding_model=config.qwen_embedding_model,
        embedding_dimensions=config.qwen_embedding_dimensions,
        qdrant_path=config.qdrant_path,
        collection_name=config.qdrant_collection,
    )
    tools = QAKnowledgeToolHandlers(store, semantic_index=semantic_index)
    memory_tools = AgentMemoryToolHandlers(
        memory_index_repository=memory_index_store,
        memory_document_repository=memory_store,
    )
    dispatcher = ToolDispatcher(tools, memory_tools)
    agent = AgentLoopRunner(
        llm=llm,
        dispatcher=dispatcher,
        memory_index_store=memory_index_store,
        memory_store=memory_store,
        messages=restore_result.messages,
        transcript=transcript,
        metadata_store=metadata_store,
        context_compactor=ToolResultCompactor(workspace_root, artifacts_dir=metadata.artifacts_dir),
        runtime_context_compactor=RuntimeContextCompactor(
            workspace_root,
            summarizer=ConversationSessionSummarizer(llm),
            session_id=session_id,
        ),
        session_summary=restore_result.summary,
        context_window_tokens=config.context_window_tokens,
        memory_extractor=AgentMemoryCandidateExtractor(),
        approval_callback=approval_callback if approval_callback is not None else None,
        event_sink=event_sink,
    )
    return AgentComponents(agent=agent, tools=tools)


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
