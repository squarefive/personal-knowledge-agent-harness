from personal_knowledge_agent.agent_factory import create_agent, create_agent_components
from personal_knowledge_agent.agent_runtime import AgentLoopRunner as AgentLoop
from personal_knowledge_agent.config import AgentConfig
from personal_knowledge_agent.agent_tools.qa_knowledge_tools import QAKnowledgeToolHandlers as KnowledgeTools


def test_create_agent_components_returns_agent_and_tools(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )

    components = create_agent_components(config)

    assert isinstance(components.agent, AgentLoop)
    assert isinstance(components.tools, KnowledgeTools)


def test_create_agent_returns_agent_loop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )

    agent = create_agent(config)

    assert isinstance(agent, AgentLoop)


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
