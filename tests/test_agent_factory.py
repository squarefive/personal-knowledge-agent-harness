import pytest

from personal_knowledge_agent.agent_bootstrap import AgentConfig, create_agent, create_agent_components
from personal_knowledge_agent.agent_runtime import AgentLoopRunner
from personal_knowledge_agent.agent_tools.qa_knowledge_tools import QAKnowledgeToolHandlers
from personal_knowledge_agent.agent_tools.todo_tools import TodoToolHandlers
from tests.fakes import (
    InMemoryMemoryStore,
    InMemoryMetadataStore,
    InMemoryQACardStore,
    InMemoryRuntimeContextCompactor,
    InMemoryTodoStore,
    InMemoryToolResultCompactor,
    InMemoryTranscript,
)


class FakeSummarizer:
    def summarize(self, messages):
        return "summary", 1


def make_config(tmp_path):
    return AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
    )


def make_components(config, **overrides):
    memory_store = overrides.pop("memory_store", InMemoryMemoryStore())
    kwargs = {
        "qa_store": InMemoryQACardStore(),
        "todo_store": InMemoryTodoStore(),
        "transcript": InMemoryTranscript(),
        "metadata_store": InMemoryMetadataStore(),
        "context_compactor": InMemoryToolResultCompactor(),
        "runtime_context_compactor": InMemoryRuntimeContextCompactor(summarizer=FakeSummarizer()),
        "memory_index_store": memory_store,
        "memory_store": memory_store,
    }
    kwargs.update(overrides)
    return create_agent_components(config, **kwargs)


def test_create_agent_components_requires_cloud_runtime_dependencies(tmp_path):
    with pytest.raises(ValueError, match="qa_store is required for cloud-only Agent runtime"):
        create_agent_components(make_config(tmp_path))


def test_create_agent_components_returns_agent_and_tools(tmp_path):
    components = make_components(make_config(tmp_path))

    assert isinstance(components.agent, AgentLoopRunner)
    assert isinstance(components.tools, QAKnowledgeToolHandlers)
    assert isinstance(components.todo_tools, TodoToolHandlers)


def test_create_agent_components_uses_injected_stores_and_adapters(tmp_path):
    qa_store = InMemoryQACardStore()
    todo_store = InMemoryTodoStore()
    transcript = InMemoryTranscript()
    metadata_store = InMemoryMetadataStore()
    context_compactor = InMemoryToolResultCompactor()
    runtime_compactor = InMemoryRuntimeContextCompactor(summarizer=FakeSummarizer())
    memory_store = InMemoryMemoryStore()

    components = make_components(
        make_config(tmp_path),
        qa_store=qa_store,
        todo_store=todo_store,
        transcript=transcript,
        metadata_store=metadata_store,
        context_compactor=context_compactor,
        runtime_context_compactor=runtime_compactor,
        memory_store=memory_store,
        memory_index_store=memory_store,
    )

    assert components.tools.store is qa_store
    assert components.todo_tools.store is todo_store
    assert components.agent.message_recorder.transcript is transcript
    assert components.agent.message_recorder.metadata_store is metadata_store
    assert components.agent.context_compactor is context_compactor
    assert components.agent.runtime_context_compactor is runtime_compactor
    assert components.agent.memory_index_store is memory_store
    assert components.agent.memory_store is memory_store


def test_create_agent_components_can_disable_semantic_index(tmp_path):
    components = make_components(make_config(tmp_path), enable_semantic_index=False)

    assert components.tools.semantic_index is None


def test_create_agent_components_passes_llm_provider_user_id(tmp_path):
    components = make_components(
        make_config(tmp_path),
        llm_provider_user_id="llm_test_1",
    )

    assert components.agent.llm.llm_provider_user_id == "llm_test_1"


def test_create_agent_requires_cloud_runtime_dependencies(tmp_path):
    with pytest.raises(ValueError, match="qa_store is required for cloud-only Agent runtime"):
        create_agent(make_config(tmp_path))
