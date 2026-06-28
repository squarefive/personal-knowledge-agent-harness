from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator

from ...agent_bootstrap import AgentConfig
from ...agent_bootstrap.agent_runtime_config import (
    DEFAULT_QWEN_EMBEDDING_BASE_URL,
    DEFAULT_QWEN_EMBEDDING_DIMENSIONS,
    DEFAULT_QWEN_EMBEDDING_MODEL,
)
from ...agent_tools.qa_knowledge_tools import QAKnowledgeToolHandlers
from ...agent_tools.todo_tools import TodoToolHandlers
from ...auth import AuthService, AuthSessionRecord, AuthSessionWithUserRecord, AuthUser, LoginCodeRecord
from ...llm_clients import QwenEmbeddingClient
from ...mail import SmtpEmailConfig, SmtpEmailSender
from ...postgres import (
    PostgresAgentMemoryRepository,
    PostgresAuthRepository,
    PostgresConversationSessionRepository,
    PostgresQACardRepository,
    PostgresQASemanticIndex,
    PostgresTodoRepository,
    close_postgres_pool,
    create_postgres_pool,
)


@dataclass(frozen=True)
class CloudUserTools:
    tools: QAKnowledgeToolHandlers
    todo_tools: TodoToolHandlers
    memory_index_store: PostgresAgentMemoryRepository
    memory_store: PostgresAgentMemoryRepository

    def close(self) -> None:
        semantic_index = getattr(self.tools, "semantic_index", None)
        close = getattr(semantic_index, "close", None)
        if callable(close):
            close()


class CloudUserToolFactory:
    def __init__(
        self,
        pool: Any,
        *,
        dashscope_api_key: str | None = None,
        embedding_base_url: str = DEFAULT_QWEN_EMBEDDING_BASE_URL,
        embedding_model: str = DEFAULT_QWEN_EMBEDDING_MODEL,
        embedding_dimensions: int = DEFAULT_QWEN_EMBEDDING_DIMENSIONS,
    ) -> None:
        self._pool = pool
        self._dashscope_api_key = dashscope_api_key
        self._embedding_base_url = embedding_base_url
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions

    @contextmanager
    def open_tools(self, user_id: str) -> Iterator[CloudUserTools]:
        with self._pool.connection() as connection:
            tools = self._build_tools(connection, user_id)
            try:
                yield tools
            finally:
                tools.close()

    def create_persistent_tools(self, user_id: str) -> tuple[CloudUserTools, Any]:
        connection = self._pool.getconn()
        try:
            return self._build_tools(connection, user_id), connection
        except Exception:
            self._pool.putconn(connection)
            raise

    def close_persistent_tools(self, connection: Any) -> None:
        self._pool.putconn(connection)

    def _build_tools(self, connection: Any, user_id: str) -> CloudUserTools:
        qa_store = PostgresQACardRepository(connection, user_id)
        todo_store = PostgresTodoRepository(connection, user_id)
        memory_store = PostgresAgentMemoryRepository(connection, user_id)
        semantic_index = self._build_semantic_index(qa_store)
        return CloudUserTools(
            tools=QAKnowledgeToolHandlers(qa_store, semantic_index=semantic_index),
            todo_tools=TodoToolHandlers(todo_store),
            memory_index_store=memory_store,
            memory_store=memory_store,
        )

    def _build_semantic_index(self, qa_store: PostgresQACardRepository) -> PostgresQASemanticIndex | None:
        if not self._dashscope_api_key:
            return None
        embedding_client = QwenEmbeddingClient(
            api_key=self._dashscope_api_key,
            base_url=self._embedding_base_url,
            model=self._embedding_model,
            dimensions=self._embedding_dimensions,
        )
        return PostgresQASemanticIndex(qa_store, embedding_client)


@dataclass(frozen=True)
class WebCloudDependencies:
    pool: Any
    auth_service: AuthService
    email_sender: SmtpEmailSender
    user_tool_factory: CloudUserToolFactory
    session_repository: PooledConversationSessionRepository


def create_web_cloud_dependencies(config: AgentConfig) -> WebCloudDependencies:
    if not config.database_url:
        raise ValueError("DATABASE_URL is required for cloud-only Web runtime")
    pool = create_postgres_pool(config.database_url)
    try:
        auth_service = AuthService(
            PooledAuthRepository(pool),
            allowed_login_emails=set(config.allowed_login_emails),
        )
        email_sender = SmtpEmailSender(_smtp_config(config))
        return WebCloudDependencies(
            pool=pool,
            auth_service=auth_service,
            email_sender=email_sender,
            user_tool_factory=CloudUserToolFactory(
                pool,
                dashscope_api_key=config.dashscope_api_key,
                embedding_base_url=config.qwen_embedding_base_url,
                embedding_model=config.qwen_embedding_model,
                embedding_dimensions=config.qwen_embedding_dimensions,
            ),
            session_repository=PooledConversationSessionRepository(pool),
        )
    except Exception:
        close_postgres_pool(pool)
        raise


def close_web_cloud_dependencies(dependencies: WebCloudDependencies | None) -> None:
    if dependencies is not None:
        close_postgres_pool(dependencies.pool)


class PooledAuthRepository:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def get_user_by_email(self, email: str) -> AuthUser | None:
        with self._repository() as repository:
            return repository.get_user_by_email(email)

    def create_user(self, user: AuthUser) -> AuthUser:
        with self._repository() as repository:
            return repository.create_user(user)

    def save_login_code(self, login_code: LoginCodeRecord) -> None:
        with self._repository() as repository:
            repository.save_login_code(login_code)

    def get_latest_login_code(self, email: str, purpose: str) -> LoginCodeRecord | None:
        with self._repository() as repository:
            return repository.get_latest_login_code(email, purpose)

    def increment_login_code_attempt(self, login_code_id: str) -> None:
        with self._repository() as repository:
            repository.increment_login_code_attempt(login_code_id)

    def consume_login_code(self, login_code_id: str, consumed_at: datetime) -> None:
        with self._repository() as repository:
            repository.consume_login_code(login_code_id, consumed_at)

    def create_auth_session(self, session: AuthSessionRecord) -> None:
        with self._repository() as repository:
            repository.create_auth_session(session)

    def get_auth_session_by_token_hash(self, token_hash: str) -> AuthSessionWithUserRecord | None:
        with self._repository() as repository:
            return repository.get_auth_session_by_token_hash(token_hash)

    def update_auth_session_last_seen(self, session_id: str, last_seen_at: datetime) -> None:
        with self._repository() as repository:
            repository.update_auth_session_last_seen(session_id, last_seen_at)

    def revoke_auth_session(self, token_hash: str, revoked_at: datetime) -> None:
        with self._repository() as repository:
            repository.revoke_auth_session(token_hash, revoked_at)

    @contextmanager
    def _repository(self) -> Iterator[PostgresAuthRepository]:
        with self._pool.connection() as connection:
            yield PostgresAuthRepository(connection)


class PooledConversationSessionRepository:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def create_session(self, user_id: str, *, session_id: str, title: str | None = None) -> Any:
        with self._repository(user_id) as repository:
            return repository.create_session(session_id=session_id, title=title)

    def list_sessions(self, user_id: str) -> list[Any]:
        with self._repository(user_id) as repository:
            return repository.list_sessions()

    def rename_session(self, user_id: str, session_id: str, title: str) -> Any | None:
        with self._repository(user_id) as repository:
            return repository.rename_session(session_id, title)

    def load_messages(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        with self._repository(user_id) as repository:
            return repository.load_messages(session_id)

    @contextmanager
    def _repository(self, user_id: str) -> Iterator[PostgresConversationSessionRepository]:
        with self._pool.connection() as connection:
            yield PostgresConversationSessionRepository(connection, user_id)


def _smtp_config(config: AgentConfig) -> SmtpEmailConfig:
    missing = [
        name
        for name, value in (
            ("SMTP_HOST", config.smtp_host),
            ("SMTP_USER", config.smtp_user),
            ("SMTP_PASSWORD", config.smtp_password),
            ("MAIL_FROM", config.mail_from),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"SMTP config is required when DATABASE_URL is set: {', '.join(missing)}")
    return SmtpEmailConfig(
        host=str(config.smtp_host),
        port=config.smtp_port,
        ssl=config.smtp_ssl,
        user=str(config.smtp_user),
        password=str(config.smtp_password),
        mail_from=str(config.mail_from),
    )
