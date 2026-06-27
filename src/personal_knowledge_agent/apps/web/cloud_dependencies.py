from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator

from ...agent_bootstrap import AgentConfig
from ...agent_tools.qa_knowledge_tools import QAKnowledgeToolHandlers
from ...agent_tools.todo_tools import TodoToolHandlers
from ...auth import AuthService, AuthSessionRecord, AuthSessionWithUserRecord, AuthUser, LoginCodeRecord
from ...mail import SmtpEmailConfig, SmtpEmailSender
from ...postgres import (
    PostgresAuthRepository,
    PostgresConversationSessionRepository,
    PostgresQACardRepository,
    PostgresTodoRepository,
    close_postgres_pool,
    create_postgres_pool,
)


@dataclass(frozen=True)
class CloudUserTools:
    tools: QAKnowledgeToolHandlers
    todo_tools: TodoToolHandlers


class CloudUserToolFactory:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @contextmanager
    def open_tools(self, user_id: str) -> Iterator[CloudUserTools]:
        with self._pool.connection() as connection:
            yield self._build_tools(connection, user_id)

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
        return CloudUserTools(
            tools=QAKnowledgeToolHandlers(qa_store, semantic_index=None),
            todo_tools=TodoToolHandlers(todo_store),
        )


@dataclass(frozen=True)
class WebCloudDependencies:
    pool: Any
    auth_service: AuthService
    email_sender: SmtpEmailSender
    user_tool_factory: CloudUserToolFactory
    session_repository: PooledConversationSessionRepository


def create_web_cloud_dependencies(config: AgentConfig) -> WebCloudDependencies | None:
    if not config.database_url:
        return None
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
            user_tool_factory=CloudUserToolFactory(pool),
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
