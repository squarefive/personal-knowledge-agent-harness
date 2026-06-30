from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path


def load_rebuild_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "rebuild-postgres-qa-embeddings.py"
    spec = importlib.util.spec_from_file_location("rebuild_postgres_qa_embeddings", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    def __init__(self, row=None, rows=None, rowcount=0):
        self._row = row
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class FakePostgresConnection:
    def __init__(self, *, user_row=("usr_1",), card_rows=None) -> None:
        self.user_row = user_row
        self.card_rows = card_rows or []
        self.executed = []
        self.commit_count = 0

    def execute(self, query, params=()):
        sql = " ".join(query.split())
        self.executed.append((sql, params))
        if "FROM users" in sql:
            return FakeCursor(row=self.user_row)
        if "FROM qa_cards" in sql and "embedding_status != %s" in sql and params[1] == "ready":
            return FakeCursor(rows=self.card_rows)
        if "UPDATE qa_cards" in sql:
            return FakeCursor(rowcount=1)
        return FakeCursor()

    def commit(self):
        self.commit_count += 1


class FakeEmbeddingClient:
    model = "text-embedding-v4"

    def __init__(self, *, fail_texts=None) -> None:
        self.fail_texts = set(fail_texts or [])
        self.texts = []

    def is_enabled(self):
        return True

    def embed_text(self, text):
        self.texts.append(text)
        if text in self.fail_texts:
            raise RuntimeError("embedding failed")
        return [0.1, 0.2, 0.3]


def card_row(card_id, question):
    now = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
    return (
        card_id,
        question,
        "Answer",
        "Summary",
        ["postgres"],
        "Agent边界",
        "manual_qa",
        now,
        now,
        "pending",
    )


def test_rebuild_requires_api_key_before_any_database_write() -> None:
    module = load_rebuild_module()
    connection = FakePostgresConnection(card_rows=[card_row("qa_1", "Question")])

    try:
        module.rebuild_postgres_qa_embeddings(
            postgres_connection=connection,
            target_email="user@example.test",
            dashscope_api_key=None,
            limit=10,
            embedding_client=FakeEmbeddingClient(),
        )
    except module.RebuildError as exc:
        assert "DASHSCOPE_API_KEY is required" in str(exc)
    else:
        raise AssertionError("Expected missing API key error")

    assert connection.executed == []
    assert connection.commit_count == 0


def test_rebuild_processes_target_user_by_email_and_marks_success_ready() -> None:
    module = load_rebuild_module()
    connection = FakePostgresConnection(card_rows=[card_row("qa_1", "Question")])
    embedding_client = FakeEmbeddingClient()

    summary = module.rebuild_postgres_qa_embeddings(
        postgres_connection=connection,
        target_email=" USER@Example.TEST ",
        dashscope_api_key="dashscope-key",
        limit=5,
        embedding_client=embedding_client,
    )

    assert summary == {"user_id": "usr_1", "total": 1, "indexed": 1, "failed": 0, "failed_card_ids": []}
    assert embedding_client.texts == ["Question\nSummary\npostgres"]
    assert connection.executed[0][1] == ("user@example.test",)
    list_sql, list_params = connection.executed[1]
    assert "WHERE user_id = %s AND embedding_status != %s" in list_sql
    assert list_params == ("usr_1", "ready", 5)
    update_sql, update_params = connection.executed[2]
    assert "embedding_status = %s" in update_sql
    assert update_params == ("ready", "[0.1,0.2,0.3]", "text-embedding-v4", "usr_1", "qa_1")


def test_rebuild_marks_single_card_failed_and_continues() -> None:
    module = load_rebuild_module()
    first = card_row("qa_1", "First")
    second = card_row("qa_2", "Second")
    connection = FakePostgresConnection(card_rows=[first, second])
    embedding_client = FakeEmbeddingClient(fail_texts={"First\nSummary\npostgres"})

    summary = module.rebuild_postgres_qa_embeddings(
        postgres_connection=connection,
        target_email="user@example.test",
        dashscope_api_key="dashscope-key",
        limit=10,
        embedding_client=embedding_client,
    )

    assert summary == {"user_id": "usr_1", "total": 2, "indexed": 1, "failed": 1, "failed_card_ids": ["qa_1"]}
    failed_updates = [params for sql, params in connection.executed if "UPDATE qa_cards" in sql and params[0] == "failed"]
    ready_updates = [params for sql, params in connection.executed if "UPDATE qa_cards" in sql and params[0] == "ready"]
    assert failed_updates == [("failed", None, None, "usr_1", "qa_1")]
    assert ready_updates == [("ready", "[0.1,0.2,0.3]", "text-embedding-v4", "usr_1", "qa_2")]
