from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from psycopg.types.json import Jsonb

from personal_knowledge_agent.postgres import (
    InMemoryToolResultCompactor,
    PostgresConversationSessionRepository,
    PostgresConversationTranscriptAdapter,
    PostgresRuntimeContextCompactor,
    PostgresSessionMetadataAdapter,
)


NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=1)
SESSION_ROW = ("chat_1", "初始标题", "已有 summary", "idle", None, 0.18, NOW, LATER)


class FakeCursor:
    def __init__(self, row: object | None = None, rows: list[object] | None = None, rowcount: int = 0) -> None:
        self._row = row
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self) -> object | None:
        return self._row

    def fetchall(self) -> list[object]:
        return self._rows


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.next_row: object | None = None
        self.next_rows: list[object] = []
        self.next_rowcount = 0
        self.rows_by_call: list[object | None] = []
        self.commit_count = 0

    def execute(self, query: str, params: tuple[object, ...] = ()) -> FakeCursor:
        self.executed.append((" ".join(query.split()), params))
        row = self.rows_by_call.pop(0) if self.rows_by_call else self.next_row
        return FakeCursor(row=row, rows=self.next_rows, rowcount=self.next_rowcount)

    def commit(self) -> None:
        self.commit_count += 1


def jsonb_value(value: object) -> object:
    assert isinstance(value, Jsonb)
    return value.obj


def test_create_session_writes_user_id_and_returns_lightweight_metadata() -> None:
    connection = FakeConnection()
    connection.next_row = SESSION_ROW
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    session = repo.create_session(session_id=" chat_1 ", title=" 初始标题 ")

    assert session.session_id == "chat_1"
    assert session.title == "初始标题"
    assert session.summary == "已有 summary"
    assert session.status == "idle"
    assert session.current_run_id is None
    assert session.last_prompt_usage_ratio == 0.18
    assert session.created_at == NOW.isoformat()
    sql, params = connection.executed[0]
    assert "INSERT INTO conversation_sessions" in sql
    assert "session_id, user_id, title" in sql
    assert "RETURNING session_id, title, summary, status, current_run_id, last_prompt_usage_ratio" in sql
    assert params == ("chat_1", "usr_1", "初始标题")
    assert connection.commit_count == 1


def test_create_session_allows_same_session_id_for_different_users() -> None:
    connection = FakeConnection()
    connection.rows_by_call = [SESSION_ROW, SESSION_ROW]
    first_repo = PostgresConversationSessionRepository(connection, "usr_1")
    second_repo = PostgresConversationSessionRepository(connection, "usr_2")

    first_repo.create_session(session_id="shared")
    second_repo.create_session(session_id="shared")

    assert connection.executed[0][1] == ("shared", "usr_1", None)
    assert connection.executed[1][1] == ("shared", "usr_2", None)


def test_list_sessions_filters_by_user_id_and_limit() -> None:
    connection = FakeConnection()
    connection.next_rows = [SESSION_ROW]
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    sessions = repo.list_sessions(limit=5)

    assert [session.session_id for session in sessions] == ["chat_1"]
    sql, params = connection.executed[0]
    assert "FROM conversation_sessions WHERE user_id = %s" in sql
    assert "ORDER BY updated_at DESC, session_id DESC LIMIT %s" in sql
    assert params == ("usr_1", 5)


def test_get_session_filters_by_user_id_and_returns_none_for_cross_user_miss() -> None:
    connection = FakeConnection()
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    session = repo.get_session("chat_other")

    assert session is None
    sql, params = connection.executed[0]
    assert "FROM conversation_sessions WHERE user_id = %s AND session_id = %s" in sql
    assert params == ("usr_1", "chat_other")


def test_rename_session_filters_by_user_id_and_hides_cross_user_miss() -> None:
    connection = FakeConnection()
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    renamed = repo.rename_session("chat_other", "新标题")

    assert renamed is None
    sql, params = connection.executed[0]
    assert "UPDATE conversation_sessions SET title = %s, updated_at = now()" in sql
    assert "WHERE user_id = %s AND session_id = %s" in sql
    assert params == ("新标题", "usr_1", "chat_other")
    assert connection.commit_count == 1


def test_rename_session_returns_user_scoped_row() -> None:
    connection = FakeConnection()
    connection.next_row = ("chat_1", "新标题", None, "idle", None, None, NOW, LATER)
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    renamed = repo.rename_session("chat_1", "新标题")

    assert renamed is not None
    assert renamed.title == "新标题"


def test_append_message_queries_next_sequence_and_writes_jsonb_message_with_user_id() -> None:
    connection = FakeConnection()
    connection.rows_by_call = [(3,)]
    repo = PostgresConversationSessionRepository(connection, "usr_1")
    message = {"role": "user", "content": "你好", "metadata": {"source": "web"}}

    sequence_no = repo.append_message("chat_1", message)

    assert sequence_no == 3
    next_sql, next_params = connection.executed[0]
    insert_sql, insert_params = connection.executed[1]
    touch_sql, touch_params = connection.executed[2]
    assert "SELECT COALESCE(MAX(sequence_no), 0) + 1 FROM conversation_messages" in next_sql
    assert "WHERE user_id = %s AND session_id = %s" in next_sql
    assert next_params == ("usr_1", "chat_1")
    assert "INSERT INTO conversation_messages" in insert_sql
    assert insert_params[:4] == ("usr_1", "chat_1", 3, "user")
    assert jsonb_value(insert_params[4]) == message
    assert "UPDATE conversation_sessions SET updated_at = now()" in touch_sql
    assert touch_params == ("usr_1", "chat_1")
    assert connection.commit_count == 1


def test_append_message_can_use_explicit_sequence_no_for_clear_callers() -> None:
    connection = FakeConnection()
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    sequence_no = repo.append_message("chat_1", {"type": "assistant_delta"}, sequence_no=7, role="assistant")

    assert sequence_no == 7
    assert len(connection.executed) == 2
    sql, params = connection.executed[0]
    assert "INSERT INTO conversation_messages" in sql
    assert params[:4] == ("usr_1", "chat_1", 7, "assistant")


def test_append_message_rejects_non_dict_message() -> None:
    connection = FakeConnection()
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    with pytest.raises(ValueError, match="message must be a dict"):
        repo.append_message("chat_1", ["not", "dict"])  # type: ignore[arg-type]

    assert connection.executed == []


def test_load_messages_filters_by_user_id_session_id_and_maps_jsonb_dicts() -> None:
    connection = FakeConnection()
    connection.next_rows = [
        ({"role": "user", "content": "第一条"},),
        {"message": {"role": "assistant", "content": "第二条", "tool_calls": []}},
    ]
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    messages = repo.load_messages("chat_1", limit=2)

    assert messages == [
        {"role": "user", "content": "第一条"},
        {"role": "assistant", "content": "第二条", "tool_calls": []},
    ]
    sql, params = connection.executed[0]
    assert "SELECT message FROM conversation_messages" in sql
    assert "WHERE user_id = %s AND session_id = %s" in sql
    assert "ORDER BY sequence_no ASC LIMIT %s" in sql
    assert params == ("usr_1", "chat_1", 2)


def test_load_messages_without_limit_keeps_user_scoped_ordering() -> None:
    connection = FakeConnection()
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    assert repo.load_messages("chat_1") == []

    sql, params = connection.executed[0]
    assert "ORDER BY sequence_no ASC" in sql
    assert "LIMIT" not in sql
    assert params == ("usr_1", "chat_1")


def test_count_messages_filters_by_user_id_and_session_id() -> None:
    connection = FakeConnection()
    connection.next_row = (4,)
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    assert repo.count_messages("chat_1") == 4

    sql, params = connection.executed[0]
    assert "SELECT COUNT(*) FROM conversation_messages" in sql
    assert "WHERE user_id = %s AND session_id = %s" in sql
    assert params == ("usr_1", "chat_1")


def test_update_summary_filters_by_user_id_and_returns_rowcount() -> None:
    connection = FakeConnection()
    connection.next_rowcount = 1
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    updated = repo.update_summary("chat_1", "压缩后的 summary")

    assert updated is True
    sql, params = connection.executed[0]
    assert "UPDATE conversation_sessions SET summary = %s, updated_at = now()" in sql
    assert "WHERE user_id = %s AND session_id = %s" in sql
    assert params == ("压缩后的 summary", "usr_1", "chat_1")
    assert connection.commit_count == 1


def test_update_summary_returns_false_for_cross_user_miss() -> None:
    connection = FakeConnection()
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    assert repo.update_summary("chat_other", "summary") is False


def test_update_prompt_usage_ratio_filters_by_user_id_and_validates_ratio() -> None:
    connection = FakeConnection()
    connection.next_rowcount = 1
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    updated = repo.update_prompt_usage_ratio("chat_1", 0.42)

    assert updated is True
    sql, params = connection.executed[0]
    assert "UPDATE conversation_sessions SET last_prompt_usage_ratio = %s, updated_at = now()" in sql
    assert "WHERE user_id = %s AND session_id = %s" in sql
    assert params == (0.42, "usr_1", "chat_1")
    assert connection.commit_count == 1

    with pytest.raises(ValueError, match="ratio must be between 0 and 1"):
        repo.update_prompt_usage_ratio("chat_1", 1.5)


def test_mark_running_and_idle_are_user_scoped_status_updates() -> None:
    connection = FakeConnection()
    connection.next_rowcount = 1
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    running = repo.mark_running("chat_1", run_id="run_1")
    idle = repo.mark_idle("chat_1")

    assert running is True
    assert idle is True
    running_sql, running_params = connection.executed[0]
    idle_sql, idle_params = connection.executed[1]
    assert "SET status = %s, current_run_id = %s, updated_at = now()" in running_sql
    assert "WHERE user_id = %s AND session_id = %s" in running_sql
    assert running_params == ("running", "run_1", "usr_1", "chat_1")
    assert "SET status = %s, current_run_id = NULL, updated_at = now()" in idle_sql
    assert "WHERE user_id = %s AND session_id = %s" in idle_sql
    assert idle_params == ("idle", "usr_1", "chat_1")
    assert connection.commit_count == 2


def test_mark_running_returns_false_for_cross_user_miss() -> None:
    connection = FakeConnection()
    repo = PostgresConversationSessionRepository(connection, "usr_1")

    assert repo.mark_running("chat_other", run_id="run_1") is False


def test_user_input_is_parameterized_not_concatenated_into_sql() -> None:
    connection = FakeConnection()
    repo = PostgresConversationSessionRepository(connection, "usr_1")
    malicious_session_id = "chat_1' OR '1'='1"

    repo.get_session(malicious_session_id)

    sql, params = connection.executed[0]
    assert malicious_session_id not in sql
    assert params == ("usr_1", malicious_session_id)


def test_postgres_transcript_adapter_uses_current_user_repository() -> None:
    connection = FakeConnection()
    connection.rows_by_call = [(1,), None, None, (1,)]
    repo = PostgresConversationSessionRepository(connection, "usr_1")
    transcript = PostgresConversationTranscriptAdapter(repo, "chat_1")

    event_id = transcript.append_message({"role": "user", "content": "你好"})
    count = transcript.event_count()

    assert event_id == 1
    assert count == 1
    assert connection.executed[0][1] == ("usr_1", "chat_1")
    assert connection.executed[1][1][:4] == ("usr_1", "chat_1", 1, "user")
    assert connection.executed[3][1] == ("usr_1", "chat_1")


def test_postgres_metadata_adapter_loads_or_creates_and_updates_summary() -> None:
    connection = FakeConnection()
    connection.rows_by_call = [None, SESSION_ROW, (2,)]
    connection.next_rowcount = 1
    repo = PostgresConversationSessionRepository(connection, "usr_1")
    metadata_store = PostgresSessionMetadataAdapter(repo, "chat_1", model="deepseek-test")

    metadata = metadata_store.load_or_create()
    updated = metadata_store.update_summary("summary")

    assert metadata.session_id == "chat_1"
    assert metadata.model == "deepseek-test"
    assert metadata.message_count == 2
    assert metadata.transcript_path == "postgres://conversation_sessions/chat_1/messages"
    assert updated is True
    assert connection.executed[0][1] == ("usr_1", "chat_1")
    assert connection.executed[1][1] == ("chat_1", "usr_1", None)
    assert connection.executed[3][1] == ("summary", "usr_1", "chat_1")


def test_postgres_metadata_adapter_autotitles_first_user_message_with_user_scope() -> None:
    connection = FakeConnection()
    connection.rows_by_call = [
        ("chat_1", None, None, "idle", None, None, NOW, NOW),
        ("chat_1", "第一条用户消息", None, "idle", None, None, NOW, LATER),
        (1,),
    ]
    repo = PostgresConversationSessionRepository(connection, "usr_1")
    metadata_store = PostgresSessionMetadataAdapter(repo, "chat_1")

    metadata = metadata_store.update_after_user_message(
        "第一条用户消息",
        event_count=1,
        message_count=1,
    )

    assert metadata.title == "第一条用户消息"
    assert metadata.last_user_message == "第一条用户消息"
    assert connection.executed[1][1] == ("第一条用户消息", "usr_1", "chat_1")


def test_in_memory_tool_result_compactor_does_not_return_local_artifact_path() -> None:
    compactor = InMemoryToolResultCompactor(threshold_chars=5)

    record = compactor.compact_tool_result(
        run_id="run_1",
        tool_call_id="call_1",
        tool_name="search_qa_cards",
        result_text="很长的工具结果",
    )

    assert record is not None
    assert record.artifact_path == ""
    assert "未写入本地文件" in record.relevance


def test_postgres_runtime_context_compactor_updates_session_summary() -> None:
    class FakeSummarizer:
        def summarize(self, messages):
            return "压缩 summary", 1

    connection = FakeConnection()
    connection.next_rowcount = 1
    repo = PostgresConversationSessionRepository(connection, "usr_1")
    compactor = PostgresRuntimeContextCompactor(repo, "chat_1", summarizer=FakeSummarizer(), recent_messages_count=1)

    result = compactor.compact(
        [{"role": "user", "content": "one"}, {"role": "assistant", "content": "two"}],
        existing_summary=None,
    )

    assert result.session_summary == "压缩 summary"
    assert result.messages == [{"role": "assistant", "content": "two"}]
    assert connection.executed[0][1] == ("压缩 summary", "usr_1", "chat_1")
