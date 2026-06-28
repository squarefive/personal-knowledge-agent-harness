import pytest

from personal_knowledge_agent.agent_bootstrap import AgentConfig
from personal_knowledge_agent.apps.web import cloud_dependencies as module
from personal_knowledge_agent.apps.web.cloud_dependencies import (
    CloudUserToolFactory,
    PooledConversationSessionRepository,
    close_web_cloud_dependencies,
    create_web_cloud_dependencies,
)
from personal_knowledge_agent.auth import AuthService
from personal_knowledge_agent.mail import SmtpEmailSender
from personal_knowledge_agent.postgres import PostgresQASemanticIndex


class FakePool:
    pass


def test_create_web_cloud_dependencies_uses_database_and_smtp_config(tmp_path, monkeypatch):
    pool = FakePool()
    created_database_urls = []
    closed_pools = []

    def fake_create_postgres_pool(database_url):
        created_database_urls.append(database_url)
        return pool

    def fake_close_postgres_pool(closed_pool):
        closed_pools.append(closed_pool)

    monkeypatch.setattr(module, "create_postgres_pool", fake_create_postgres_pool)
    monkeypatch.setattr(module, "close_postgres_pool", fake_close_postgres_pool)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        database_url="postgresql://example/db",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_ssl=False,
        smtp_user="mailer@example.com",
        smtp_password="smtp-secret",
        mail_from="mailer@example.com",
    )

    dependencies = create_web_cloud_dependencies(config)

    assert created_database_urls == ["postgresql://example/db"]
    assert dependencies is not None
    assert dependencies.pool is pool
    assert isinstance(dependencies.auth_service, AuthService)
    assert isinstance(dependencies.email_sender, SmtpEmailSender)
    assert dependencies.email_sender.config.host == "smtp.example.com"
    assert dependencies.email_sender.config.port == 587
    assert dependencies.email_sender.config.ssl is False
    assert dependencies.email_sender.config.user == "mailer@example.com"
    assert dependencies.email_sender.config.mail_from == "mailer@example.com"
    assert isinstance(dependencies.user_tool_factory, CloudUserToolFactory)
    assert isinstance(dependencies.session_repository, PooledConversationSessionRepository)

    close_web_cloud_dependencies(dependencies)

    assert closed_pools == [pool]


def test_pooled_conversation_session_repository_uses_current_user(monkeypatch):
    calls = []

    class FakeConnectionContext:
        def __enter__(self):
            return "connection"

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakePool:
        def connection(self):
            return FakeConnectionContext()

    class FakePostgresConversationSessionRepository:
        def __init__(self, connection, user_id):
            calls.append(("init", connection, user_id))
            self.user_id = user_id

        def create_session(self, *, session_id, title=None):
            calls.append(("create", self.user_id, session_id, title))
            return {"session_id": session_id, "title": title}

        def list_sessions(self):
            calls.append(("list", self.user_id))
            return [{"session_id": "session_1"}]

        def rename_session(self, session_id, title):
            calls.append(("rename", self.user_id, session_id, title))
            return {"session_id": session_id, "title": title}

        def load_messages(self, session_id):
            calls.append(("messages", self.user_id, session_id))
            return [{"role": "user", "content": "hello"}]

    monkeypatch.setattr(
        module,
        "PostgresConversationSessionRepository",
        FakePostgresConversationSessionRepository,
    )
    repository = PooledConversationSessionRepository(FakePool())

    assert repository.create_session("usr_1", session_id="session_1", title=None)["session_id"] == "session_1"
    assert repository.list_sessions("usr_1") == [{"session_id": "session_1"}]
    assert repository.rename_session("usr_1", "session_1", "新标题")["title"] == "新标题"
    assert repository.load_messages("usr_1", "session_1") == [{"role": "user", "content": "hello"}]
    assert calls == [
        ("init", "connection", "usr_1"),
        ("create", "usr_1", "session_1", None),
        ("init", "connection", "usr_1"),
        ("list", "usr_1"),
        ("init", "connection", "usr_1"),
        ("rename", "usr_1", "session_1", "新标题"),
        ("init", "connection", "usr_1"),
        ("messages", "usr_1", "session_1"),
    ]


def test_cloud_user_tool_factory_injects_postgres_semantic_index_when_embedding_key_is_configured() -> None:
    class FakeConnectionContext:
        def __enter__(self):
            return "connection"

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakePool:
        def connection(self):
            return FakeConnectionContext()

    factory = CloudUserToolFactory(
        FakePool(),
        dashscope_api_key="dashscope-key",
        embedding_base_url="https://dashscope.example/v1",
        embedding_model="text-embedding-v4",
        embedding_dimensions=1024,
    )

    with factory.open_tools("usr_1") as tools:
        semantic_index = tools.tools.semantic_index

    assert isinstance(semantic_index, PostgresQASemanticIndex)
    assert semantic_index.embedding_client.api_key == "dashscope-key"
    assert semantic_index.embedding_client.base_url == "https://dashscope.example/v1"
    assert semantic_index.embedding_client.model == "text-embedding-v4"


def test_cloud_user_tool_factory_keeps_semantic_index_none_without_embedding_key() -> None:
    class FakeConnectionContext:
        def __enter__(self):
            return "connection"

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakePool:
        def connection(self):
            return FakeConnectionContext()

    factory = CloudUserToolFactory(FakePool(), dashscope_api_key=None)

    with factory.open_tools("usr_1") as tools:
        assert tools.tools.semantic_index is None


def test_create_web_cloud_dependencies_requires_database_url(tmp_path, monkeypatch):
    created_database_urls = []
    monkeypatch.setattr(module, "create_postgres_pool", lambda database_url: created_database_urls.append(database_url))
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
    )

    with pytest.raises(ValueError, match="DATABASE_URL is required for cloud-only Web runtime"):
        create_web_cloud_dependencies(config)
    assert created_database_urls == []


def test_create_web_cloud_dependencies_rejects_local_fallback_when_cloud_only(tmp_path, monkeypatch):
    created_database_urls = []
    monkeypatch.setattr(module, "create_postgres_pool", lambda database_url: created_database_urls.append(database_url))
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        cloud_only=True,
    )

    with pytest.raises(ValueError, match="DATABASE_URL is required for cloud-only Web runtime"):
        create_web_cloud_dependencies(config)

    assert created_database_urls == []


def test_create_web_cloud_dependencies_closes_pool_when_smtp_config_is_missing(tmp_path, monkeypatch):
    pool = FakePool()
    closed_pools = []
    monkeypatch.setattr(module, "create_postgres_pool", lambda database_url: pool)
    monkeypatch.setattr(module, "close_postgres_pool", lambda closed_pool: closed_pools.append(closed_pool))
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        database_url="postgresql://example/db",
    )

    try:
        create_web_cloud_dependencies(config)
    except ValueError as exc:
        assert "SMTP config is required" in str(exc)
    else:
        raise AssertionError("Expected SMTP config error")

    assert closed_pools == [pool]
