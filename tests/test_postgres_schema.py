from __future__ import annotations

from personal_knowledge_agent.postgres import POSTGRES_SCHEMA_STATEMENTS, initialize_postgres_schema


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.commit_count = 0

    def execute(self, query: str) -> None:
        self.executed.append(" ".join(query.split()))

    def commit(self) -> None:
        self.commit_count += 1


def test_initialize_postgres_schema_executes_expected_ddl() -> None:
    connection = FakeConnection()

    initialize_postgres_schema(connection)

    sql = "\n".join(connection.executed)
    assert connection.executed[0] == "CREATE EXTENSION IF NOT EXISTS vector"
    assert len(connection.executed) == len(POSTGRES_SCHEMA_STATEMENTS)
    assert connection.commit_count == 1

    for table_name in (
        "users",
        "email_login_codes",
        "auth_sessions",
        "qa_cards",
        "todo_items",
        "conversation_sessions",
        "conversation_messages",
        "agent_user_memories",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql

    assert "email TEXT NOT NULL UNIQUE" in sql
    assert "llm_provider_user_id TEXT NOT NULL UNIQUE" in sql
    assert "code_hash TEXT NOT NULL" in sql
    assert "expires_at TIMESTAMPTZ NOT NULL" in sql
    assert "consumed BOOLEAN NOT NULL DEFAULT false" in sql
    assert "attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0)" in sql
    assert "token_hash TEXT NOT NULL UNIQUE" in sql
    assert "embedding vector" in sql
    assert "embedding_status TEXT NOT NULL DEFAULT 'pending'" in sql
    assert "embedding_model TEXT" in sql
    assert "legacy_source TEXT" in sql
    assert "legacy_card_id TEXT" in sql
    assert "UNIQUE (user_id, session_id)" in sql
    assert "FOREIGN KEY (user_id, session_id)" in sql
    assert "REFERENCES conversation_sessions(user_id, session_id)" in sql


def test_initialize_postgres_schema_is_idempotent_sql() -> None:
    connection = FakeConnection()

    initialize_postgres_schema(connection)
    initialize_postgres_schema(connection)

    sql = "\n".join(connection.executed)
    assert sql.count("CREATE EXTENSION IF NOT EXISTS vector") == 2
    assert sql.count("CREATE TABLE IF NOT EXISTS qa_cards") == 2
    assert sql.count("CREATE INDEX IF NOT EXISTS idx_qa_cards_user_id_created_at") == 2
    assert connection.commit_count == 2


def test_business_tables_include_user_id() -> None:
    sql_by_table = {
        statement.split("CREATE TABLE IF NOT EXISTS ", 1)[1].split(" ", 1)[0]: " ".join(statement.split())
        for statement in POSTGRES_SCHEMA_STATEMENTS
        if "CREATE TABLE IF NOT EXISTS" in statement
    }

    for table_name in (
        "email_login_codes",
        "auth_sessions",
        "qa_cards",
        "todo_items",
        "conversation_sessions",
        "conversation_messages",
        "agent_user_memories",
    ):
        assert "user_id TEXT NOT NULL REFERENCES users(user_id)" in sql_by_table[table_name]
