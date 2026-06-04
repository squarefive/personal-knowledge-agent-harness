from personal_knowledge_agent.agent_factory import create_agent, create_agent_components
from personal_knowledge_agent.agent_loop import AgentLoop
from personal_knowledge_agent.config import AgentConfig
from personal_knowledge_agent.tools import KnowledgeTools


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
