from personal_knowledge_agent.agent_bootstrap import create_agent, create_agent_components
from personal_knowledge_agent.agent_runtime import AgentLoopRunner
from personal_knowledge_agent.agent_bootstrap import AgentConfig
from personal_knowledge_agent.agent_tools.qa_knowledge_tools import QAKnowledgeToolHandlers
from personal_knowledge_agent.agent_tools.todo_tools import TodoToolHandlers
from personal_knowledge_agent.agent_context.conversation_sessions import RuntimeCompactionResult, SessionMetadata


class FakeQAStore:
    pass


class FakeTodoStore:
    pass


class FakeTranscript:
    def __init__(self):
        self.messages = []

    def append_message(self, message):
        self.messages.append(message)
        return len(self.messages)

    def load_messages(self):
        return list(self.messages)

    def event_count(self):
        return len(self.messages)


class FakeMetadataStore:
    def __init__(self):
        self.summary = None

    def load_or_create(self):
        return SessionMetadata(
            session_id="injected",
            created_at="2026-06-27T00:00:00+00:00",
            updated_at="2026-06-27T00:00:00+00:00",
            cwd="memory",
            model="test-model",
            transcript_path="memory://transcript",
            summary_path="memory://summary",
            artifacts_dir="",
        )

    def update_counts(self, **kwargs):
        return self.load_or_create()

    def update_after_user_message(self, message, *, event_count, message_count):
        return self.load_or_create()

    def update_summary(self, summary):
        self.summary = summary
        return True


class FakeToolResultCompactor:
    def compact_tool_result(self, **kwargs):
        return None


class FakeRuntimeContextCompactor:
    def compact(self, messages, *, existing_summary=None):
        return RuntimeCompactionResult(messages=messages, session_summary="summary", mode="test")


def test_create_agent_components_returns_agent_and_tools(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )

    components = create_agent_components(config)

    assert isinstance(components.agent, AgentLoopRunner)
    assert isinstance(components.tools, QAKnowledgeToolHandlers)
    assert isinstance(components.todo_tools, TodoToolHandlers)


def test_create_agent_returns_agent_loop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )

    agent = create_agent(config)

    assert isinstance(agent, AgentLoopRunner)


def test_create_agent_accepts_approval_callback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )
    approvals = []

    def approve(request):
        approvals.append(request)
        return False

    agent = create_agent(config, approval_callback=approve)

    assert agent.tool_call_step.approval_callback is approve


def test_create_agent_components_accepts_session_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )

    create_agent_components(config, session_id="chat_1")

    assert (tmp_path / ".sessions" / "chat_1" / "metadata.json").exists()
    assert not (tmp_path / ".sessions" / "default" / "metadata.json").exists()


def test_create_agent_components_uses_injected_qa_and_todo_stores(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )
    qa_store = FakeQAStore()
    todo_store = FakeTodoStore()

    components = create_agent_components(
        config,
        qa_store=qa_store,
        todo_store=todo_store,
    )

    assert components.tools.store is qa_store
    assert components.todo_tools.store is todo_store


def test_create_agent_components_can_disable_semantic_index(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )

    components = create_agent_components(config, enable_semantic_index=False)

    assert components.tools.semantic_index is None


def test_create_agent_components_passes_llm_provider_user_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )

    components = create_agent_components(
        config,
        llm_provider_user_id="llm_test_1",
    )

    assert components.agent.llm.llm_provider_user_id == "llm_test_1"


def test_create_agent_components_default_behavior_creates_session_metadata(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )

    create_agent_components(config)

    assert (tmp_path / ".sessions" / "default" / "metadata.json").exists()


def test_create_agent_components_uses_injected_session_runtime_without_local_sessions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )
    transcript = FakeTranscript()
    metadata_store = FakeMetadataStore()
    context_compactor = FakeToolResultCompactor()
    runtime_compactor = FakeRuntimeContextCompactor()

    components = create_agent_components(
        config,
        transcript=transcript,
        metadata_store=metadata_store,
        context_compactor=context_compactor,
        runtime_context_compactor=runtime_compactor,
    )

    assert components.agent.message_recorder.transcript is transcript
    assert components.agent.message_recorder.metadata_store is metadata_store
    assert components.agent.context_compactor is context_compactor
    assert components.agent.runtime_context_compactor is runtime_compactor
    assert not (tmp_path / ".sessions").exists()
