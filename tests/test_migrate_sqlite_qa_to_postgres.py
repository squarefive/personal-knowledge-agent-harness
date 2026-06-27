from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb


def load_migration_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "migrate-sqlite-qa-to-postgres.py"
    spec = importlib.util.spec_from_file_location("migrate_sqlite_qa_to_postgres", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    def __init__(self, row: object | None = None) -> None:
        self._row = row

    def fetchone(self) -> object | None:
        return self._row


class FakePostgresConnection:
    def __init__(self, user_row: object | None = ("usr_1",)) -> None:
        self.user_row = user_row
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.commit_count = 0

    def execute(self, query: str, params: tuple[object, ...] = ()) -> FakeCursor:
        sql = " ".join(query.split())
        self.executed.append((sql, params))
        if "FROM users" in sql:
            return FakeCursor(self.user_row)
        return FakeCursor()

    def commit(self) -> None:
        self.commit_count += 1


def create_sqlite_db(tmp_path, *, include_is_vectorized: bool = True, keywords: str = '["agent", "qa"]') -> Path:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        is_vectorized_column = ", is_vectorized INTEGER NOT NULL DEFAULT 0" if include_is_vectorized else ""
        connection.execute(
            f"""
            CREATE TABLE qa_cards (
              id TEXT PRIMARY KEY,
              question TEXT NOT NULL,
              answer TEXT NOT NULL,
              summary TEXT NOT NULL,
              keywords TEXT NOT NULL,
              category TEXT NOT NULL,
              source_type TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
              {is_vectorized_column}
            )
            """
        )
        connection.execute(
            """
            INSERT INTO qa_cards (
              id, question, answer, summary, keywords, category, source_type, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "qa_legacy_1",
                "旧问题？",
                "旧答案。",
                "旧摘要。",
                keywords,
                "Agent 开发",
                "manual_qa",
                "2026-06-20T10:00:00+00:00",
                "2026-06-20T11:00:00+00:00",
            ),
        )
        connection.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute("INSERT INTO sessions (id, payload) VALUES ('session_1', 'must not migrate')")
        connection.execute("CREATE TABLE todo_items (id TEXT PRIMARY KEY, title TEXT NOT NULL)")
        connection.execute("INSERT INTO todo_items (id, title) VALUES ('todo_1', 'must not migrate')")
    return db_path


def jsonb_value(value: object) -> object:
    assert isinstance(value, Jsonb)
    return value.obj


def test_cli_argument_parsing_and_email_normalization(tmp_path) -> None:
    module = load_migration_module()
    db_path = tmp_path / "legacy.db"

    args = module.parse_args(
        [
            "--sqlite-db",
            str(db_path),
            "--target-email",
            "  USER@Example.TEST ",
            "--database-url",
            "postgresql://example/db",
            "--dry-run",
        ]
    )

    assert args.sqlite_db == db_path
    assert args.target_email == "  USER@Example.TEST "
    assert args.database_url == "postgresql://example/db"
    assert args.dry_run is True
    assert module.normalize_email(args.target_email) == "user@example.test"


def test_reads_only_qa_cards_and_does_not_migrate_sessions_or_todo(tmp_path) -> None:
    module = load_migration_module()
    db_path = create_sqlite_db(tmp_path)
    postgres = FakePostgresConnection()

    summary = module.migrate_sqlite_qa_to_postgres(
        sqlite_db=db_path,
        postgres_connection=postgres,
        target_email="USER@EXAMPLE.TEST",
    )

    assert summary.total == 1
    assert summary.upserted == 1
    executed_sql = " ".join(sql for sql, _params in postgres.executed)
    assert "sessions" not in executed_sql
    assert "todo" not in executed_sql
    assert postgres.commit_count == 1


def test_user_missing_returns_clear_error_without_writing(tmp_path) -> None:
    module = load_migration_module()
    db_path = create_sqlite_db(tmp_path)
    postgres = FakePostgresConnection(user_row=None)

    with pytest.raises(module.MigrationError, match="target user does not exist for email: user@example.test"):
        module.migrate_sqlite_qa_to_postgres(
            sqlite_db=db_path,
            postgres_connection=postgres,
            target_email=" USER@EXAMPLE.TEST ",
        )

    assert len(postgres.executed) == 1
    sql, params = postgres.executed[0]
    assert "SELECT user_id FROM users WHERE email = %s" in sql
    assert params == ("user@example.test",)
    assert postgres.commit_count == 0


def test_upsert_sql_contains_user_and_legacy_identity_and_pending_embedding(tmp_path) -> None:
    module = load_migration_module()
    db_path = create_sqlite_db(tmp_path, include_is_vectorized=False)
    postgres = FakePostgresConnection(user_row={"user_id": "usr_1"})

    module.migrate_sqlite_qa_to_postgres(
        sqlite_db=db_path,
        postgres_connection=postgres,
        target_email="user@example.test",
    )

    sql, params = postgres.executed[1]
    assert "INSERT INTO qa_cards" in sql
    assert "user_id" in sql
    assert "legacy_source" in sql
    assert "legacy_card_id" in sql
    assert "ON CONFLICT (user_id, legacy_source, legacy_card_id) DO UPDATE" in sql
    assert "embedding = NULL" in sql
    assert "embedding_status = 'pending'" in sql
    assert "embedding_model = NULL" in sql
    assert params[1] == "usr_1"
    assert jsonb_value(params[5]) == ["agent", "qa"]
    assert params[8] == "pending"
    assert params[9:11] == (module.LEGACY_SOURCE, "qa_legacy_1")


def test_keywords_json_parse_error_includes_card_id(tmp_path) -> None:
    module = load_migration_module()
    db_path = create_sqlite_db(tmp_path, keywords="not json")
    postgres = FakePostgresConnection()

    with pytest.raises(module.MigrationError, match="invalid keywords JSON for legacy card id qa_legacy_1"):
        module.migrate_sqlite_qa_to_postgres(
            sqlite_db=db_path,
            postgres_connection=postgres,
            target_email="user@example.test",
        )

    assert postgres.commit_count == 0


def test_keywords_must_be_json_list_of_strings(tmp_path) -> None:
    module = load_migration_module()
    db_path = create_sqlite_db(tmp_path, keywords='["valid", 1]')
    postgres = FakePostgresConnection()

    with pytest.raises(module.MigrationError, match="keywords must be a JSON list of strings"):
        module.migrate_sqlite_qa_to_postgres(
            sqlite_db=db_path,
            postgres_connection=postgres,
            target_email="user@example.test",
        )

    assert postgres.commit_count == 0


def test_dry_run_validates_without_writing_postgres(tmp_path) -> None:
    module = load_migration_module()
    db_path = create_sqlite_db(tmp_path)
    postgres = FakePostgresConnection()

    summary = module.migrate_sqlite_qa_to_postgres(
        sqlite_db=db_path,
        postgres_connection=postgres,
        target_email="user@example.test",
        dry_run=True,
    )

    assert summary.total == 1
    assert summary.upserted == 0
    assert summary.dry_run is True
    assert len(postgres.executed) == 1
    assert "FROM users" in postgres.executed[0][0]
    assert postgres.commit_count == 0


def test_main_returns_error_code_for_migration_error(tmp_path, monkeypatch, capsys) -> None:
    module = load_migration_module()
    db_path = create_sqlite_db(tmp_path)

    class FakePool:
        def connection(self):
            class ConnectionContext:
                def __enter__(self):
                    return FakePostgresConnection(user_row=None)

                def __exit__(self, exc_type, exc, tb):
                    return False

            return ConnectionContext()

    monkeypatch.setattr(module, "create_postgres_pool", lambda *args, **kwargs: FakePool())
    monkeypatch.setattr(module, "close_postgres_pool", lambda pool: None)

    exit_code = module.main(
        [
            "--sqlite-db",
            str(db_path),
            "--target-email",
            "missing@example.test",
            "--database-url",
            "postgresql://example/db",
        ]
    )

    assert exit_code == 2
    assert "target user does not exist for email: missing@example.test" in capsys.readouterr().err
