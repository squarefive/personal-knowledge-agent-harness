from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .agent_loop import AgentLoop
from .agent_memory import MemoryExtractor, MemoryIndexStore, MemoryStore
from .config import AgentConfig
from .events import AgentEvent
from .llm_client import DeepSeekClient
from .permissions import ApprovalRequest
from .qa_semantic_index import QASemanticIndex
from .qa_store import SQLiteStore
from .session_memory import (
    ContextCompactor,
    SessionMetadataStore,
    SessionRestore,
    SessionSummarizer,
    SessionTranscript,
)
from .tools import KnowledgeTools, ToolDispatcher


@dataclass(frozen=True)
class AgentComponents:
    agent: AgentLoop
    tools: KnowledgeTools


def create_agent_components(
    config: AgentConfig,
    event_sink: Callable[[AgentEvent], None] | None = None,
    approval_callback: Callable[[ApprovalRequest], bool] | None = None,
) -> AgentComponents:
    store = SQLiteStore(config.knowledge_db_path)
    workspace_root = Path.cwd()
    llm = DeepSeekClient(
        api_key=config.deepseek_api_key,
        model=config.deepseek_model,
    )
    transcript = SessionTranscript(workspace_root)
    metadata_store = SessionMetadataStore(workspace_root, model=config.deepseek_model)
    restore_result = SessionRestore(
        transcript=transcript,
        metadata_store=metadata_store,
        summarizer=SessionSummarizer(llm),
    ).restore()
    metadata = metadata_store.load_or_create()
    memory_index_store = MemoryIndexStore(workspace_root)
    memory_store = MemoryStore(workspace_root)
    semantic_index = QASemanticIndex(
        dashscope_api_key=config.dashscope_api_key,
        embedding_base_url=config.qwen_embedding_base_url,
        embedding_model=config.qwen_embedding_model,
        embedding_dimensions=config.qwen_embedding_dimensions,
        qdrant_path=config.qdrant_path,
        collection_name=config.qdrant_collection,
    )
    tools = KnowledgeTools(
        store,
        memory_index_store=memory_index_store,
        memory_store=memory_store,
        semantic_index=semantic_index,
    )
    dispatcher = ToolDispatcher(tools)
    agent = AgentLoop(
        llm=llm,
        tools=tools,
        dispatcher=dispatcher,
        memory_index_store=memory_index_store,
        memory_store=memory_store,
        messages=restore_result.messages,
        transcript=transcript,
        metadata_store=metadata_store,
        context_compactor=ContextCompactor(workspace_root, artifacts_dir=metadata.artifacts_dir),
        memory_extractor=MemoryExtractor(),
        approval_callback=approval_callback if approval_callback is not None else None,
        event_sink=event_sink,
    )
    return AgentComponents(agent=agent, tools=tools)


def create_agent(
    config: AgentConfig,
    event_sink: Callable[[AgentEvent], None] | None = None,
    approval_callback: Callable[[ApprovalRequest], bool] | None = None,
) -> AgentLoop:
    return create_agent_components(
        config,
        event_sink=event_sink,
        approval_callback=approval_callback,
    ).agent
