from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from psycopg.types.json import Jsonb

from personal_knowledge_agent.postgres import PostgresQACardRepository


NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=1)
CARD_ROW = (
    "qa_1",
    "What is the source boundary?",
    "Only persisted Q&A facts are answer evidence.",
    "Q&A facts only.",
    ["source", "evidence"],
    "Agent边界",
    "manual_qa",
    NOW,
    LATER,
    "ready",
)


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
        self.commit_count = 0

    def execute(self, query: str, params: tuple[object, ...] = ()) -> FakeCursor:
        self.executed.append((" ".join(query.split()), params))
        return FakeCursor(row=self.next_row, rows=self.next_rows, rowcount=self.next_rowcount)

    def commit(self) -> None:
        self.commit_count += 1


def jsonb_value(value: object) -> object:
    assert isinstance(value, Jsonb)
    return value.obj


def test_create_card_writes_user_id_and_complete_fields_with_keyword_jsonb() -> None:
    connection = FakeConnection()
    connection.next_row = CARD_ROW
    repo = PostgresQACardRepository(connection, "usr_1")

    card = repo.create_card(
        card_id="qa_1",
        question=" What is the source boundary? ",
        answer=" Only persisted Q&A facts are answer evidence. ",
        summary=" Q&A facts only. ",
        keywords=[" source ", "evidence"],
        category=" Agent边界 ",
        source_type=" manual_qa ",
    )

    assert card.id == "qa_1"
    assert card.keywords == ["source", "evidence"]
    assert card.is_vectorized == 1
    sql, params = connection.executed[0]
    assert "INSERT INTO qa_cards" in sql
    assert "user_id" in sql
    assert "RETURNING card_id" in sql
    assert params[:5] == (
        "qa_1",
        "usr_1",
        "What is the source boundary?",
        "Only persisted Q&A facts are answer evidence.",
        "Q&A facts only.",
    )
    assert jsonb_value(params[5]) == ["source", "evidence"]
    assert params[6:] == ("Agent边界", "manual_qa")
    assert connection.commit_count == 1


def test_save_card_compat_method_writes_user_id() -> None:
    connection = FakeConnection()
    connection.next_row = CARD_ROW
    repo = PostgresQACardRepository(connection, "usr_1")

    card = repo.save_card(
        question="What is the source boundary?",
        answer="Only persisted Q&A facts are answer evidence.",
        summary="Q&A facts only.",
        keywords=["source", "evidence"],
        category="Agent边界",
    )

    assert card.id == "qa_1"
    sql, params = connection.executed[0]
    assert "INSERT INTO qa_cards" in sql
    assert "user_id" in sql
    assert params[1] == "usr_1"


def test_get_card_filters_by_user_id_and_returns_none_for_cross_user_miss() -> None:
    connection = FakeConnection()
    repo = PostgresQACardRepository(connection, "usr_1")

    card = repo.get_card("qa_other")

    assert card is None
    sql, params = connection.executed[0]
    assert "FROM qa_cards WHERE user_id = %s AND card_id = %s" in sql
    assert params == ("usr_1", "qa_other")


def test_read_card_compat_method_filters_by_user_id() -> None:
    connection = FakeConnection()
    repo = PostgresQACardRepository(connection, "usr_1")

    card = repo.read_card("qa_other")

    assert card is None
    sql, params = connection.executed[0]
    assert "FROM qa_cards WHERE user_id = %s AND card_id = %s" in sql
    assert params == ("usr_1", "qa_other")


def test_get_card_maps_keywords_json_string_to_python_list() -> None:
    connection = FakeConnection()
    connection.next_row = {
        "card_id": "qa_2",
        "question": "Question",
        "answer": "Answer",
        "summary": "Summary",
        "keywords": '["jsonb", "keywords"]',
        "category": "Postgres",
        "source_type": "manual_qa",
        "created_at": NOW,
        "updated_at": LATER,
        "embedding_status": "pending",
    }
    repo = PostgresQACardRepository(connection, "usr_1")

    card = repo.get_card("qa_2")

    assert card is not None
    assert card.keywords == ["jsonb", "keywords"]
    assert card.created_at == NOW.isoformat()
    assert card.is_vectorized == 0


def test_list_recent_cards_filters_by_user_id_and_category_with_limit_param() -> None:
    connection = FakeConnection()
    connection.next_rows = [CARD_ROW]
    repo = PostgresQACardRepository(connection, "usr_1")

    cards = repo.list_recent_cards(limit=3, category="Agent边界")

    assert [card.id for card in cards] == ["qa_1"]
    sql, params = connection.executed[0]
    assert "WHERE user_id = %s AND category = %s" in sql
    assert "ORDER BY created_at DESC, card_id DESC LIMIT %s" in sql
    assert params == ("usr_1", "Agent边界", 3)


def test_list_all_cards_filters_by_user_id_and_orders_by_created_at_asc() -> None:
    connection = FakeConnection()
    connection.next_rows = [CARD_ROW]
    repo = PostgresQACardRepository(connection, "usr_1")

    cards = repo.list_all_cards()

    assert [card.id for card in cards] == ["qa_1"]
    sql, params = connection.executed[0]
    assert "FROM qa_cards WHERE user_id = %s ORDER BY created_at ASC" in sql
    assert params == ("usr_1",)


def test_list_all_cards_filters_by_user_id_and_category() -> None:
    connection = FakeConnection()
    connection.next_rows = [CARD_ROW]
    repo = PostgresQACardRepository(connection, "usr_1")

    cards = repo.list_all_cards(category="Agent边界")

    assert [card.id for card in cards] == ["qa_1"]
    sql, params = connection.executed[0]
    assert "WHERE user_id = %s AND category = %s" in sql
    assert "ORDER BY created_at ASC" in sql
    assert params == ("usr_1", "Agent边界")


def test_read_cards_by_ids_preserves_input_order_and_filters_missing_or_cross_user() -> None:
    connection = FakeConnection()
    first_row = (
        "qa_1",
        "First question",
        "First answer",
        "First summary",
        ["first"],
        "Agent边界",
        "manual_qa",
        NOW,
        LATER,
        "ready",
    )
    second_row = (
        "qa_2",
        "Second question",
        "Second answer",
        "Second summary",
        ["second"],
        "Agent边界",
        "manual_qa",
        NOW,
        LATER,
        "pending",
    )
    rows_by_card_id = {"qa_1": first_row, "qa_2": second_row}

    def execute(query: str, params: tuple[object, ...] = ()) -> FakeCursor:
        connection.executed.append((" ".join(query.split()), params))
        return FakeCursor(row=rows_by_card_id.get(params[1]))

    connection.execute = execute  # type: ignore[method-assign]
    repo = PostgresQACardRepository(connection, "usr_1")

    cards = repo.read_cards_by_ids(["qa_2", "qa_missing", " ", "qa_1", "qa_cross_user"])

    assert [card.id for card in cards] == ["qa_2", "qa_1"]
    assert [params for _, params in connection.executed] == [
        ("usr_1", "qa_2"),
        ("usr_1", "qa_missing"),
        ("usr_1", "qa_1"),
        ("usr_1", "qa_cross_user"),
    ]


def test_read_cards_by_ids_applies_category_after_user_scoped_read() -> None:
    connection = FakeConnection()
    connection.next_row = CARD_ROW
    repo = PostgresQACardRepository(connection, "usr_1")

    cards = repo.read_cards_by_ids(["qa_1"], category="其他分类")

    assert cards == []
    sql, params = connection.executed[0]
    assert "WHERE user_id = %s AND card_id = %s" in sql
    assert params == ("usr_1", "qa_1")


def test_list_unvectorized_cards_filters_by_user_id_status_and_limit_param() -> None:
    connection = FakeConnection()
    connection.next_rows = [
        (
            "qa_2",
            "Question",
            "Answer",
            "Summary",
            ["pending"],
            "Postgres",
            "manual_qa",
            NOW,
            LATER,
            "pending",
        )
    ]
    repo = PostgresQACardRepository(connection, "usr_1")

    cards = repo.list_unvectorized_cards(limit=2)

    assert [card.id for card in cards] == ["qa_2"]
    sql, params = connection.executed[0]
    assert "WHERE user_id = %s AND embedding_status != 'ready'" in sql
    assert "ORDER BY created_at ASC LIMIT %s" in sql
    assert params == ("usr_1", 2)


def test_list_unvectorized_cards_without_limit_uses_user_id_only() -> None:
    connection = FakeConnection()
    repo = PostgresQACardRepository(connection, "usr_1")

    assert repo.list_unvectorized_cards() == []

    sql, params = connection.executed[0]
    assert "WHERE user_id = %s AND embedding_status != 'ready'" in sql
    assert "LIMIT %s" not in sql
    assert params == ("usr_1",)


def test_search_keyword_cards_uses_user_id_and_parameter_tuple_for_ilike_terms() -> None:
    connection = FakeConnection()
    connection.next_rows = [
        (
            "qa_1",
            "What is the source boundary?",
            "Q&A facts only.",
            "Only persisted Q&A facts are answer evidence.",
            "manual_qa",
            NOW,
            "Agent边界",
        )
    ]
    repo = PostgresQACardRepository(connection, "usr_1")

    results = repo.search_keyword_cards("source", limit=2, category="Agent边界")

    assert results[0].card_id == "qa_1"
    assert results[0].answer_snippet == "Only persisted Q&A facts are answer evidence."
    sql, params = connection.executed[0]
    assert "WHERE user_id = %s AND category = %s AND" in sql
    assert "question ILIKE %s" in sql
    assert "answer ILIKE %s" in sql
    assert "summary ILIKE %s" in sql
    assert "keywords::text ILIKE %s" in sql
    assert "category ILIKE %s" in sql
    assert params == ("usr_1", "Agent边界", "%source%", "%source%", "%source%", "%source%", "%source%", 2)


def test_search_cards_compat_method_filters_by_user_id() -> None:
    connection = FakeConnection()
    repo = PostgresQACardRepository(connection, "usr_1")

    results = repo.search_cards("source")

    assert results == []
    sql, params = connection.executed[0]
    assert "WHERE user_id = %s" in sql
    assert params == ("usr_1", "%source%", "%source%", "%source%", "%source%", "%source%", 5)


def test_update_card_filters_by_user_id_resets_embedding_and_returns_none_when_not_owned() -> None:
    connection = FakeConnection()
    repo = PostgresQACardRepository(connection, "usr_1")

    updated = repo.update_card("qa_cross_user", question="New question", keywords=["new"])

    assert updated is None
    sql, params = connection.executed[0]
    assert "UPDATE qa_cards SET" in sql
    assert "embedding = NULL" in sql
    assert "embedding_status = 'pending'" in sql
    assert "WHERE user_id = %s AND card_id = %s" in sql
    assert params[:3] == ("New question", None, None)
    assert jsonb_value(params[3]) == ["new"]
    assert params[4:] == (None, None, "usr_1", "qa_cross_user")
    assert connection.commit_count == 1


def test_update_card_with_keywords_none_does_not_update_keywords() -> None:
    connection = FakeConnection()
    connection.next_row = CARD_ROW
    repo = PostgresQACardRepository(connection, "usr_1")

    updated = repo.update_card("qa_1", question="New question", keywords=None)

    assert updated is not None
    sql, params = connection.executed[0]
    assert "keywords = COALESCE(%s, keywords)" in sql
    assert params[3] is None
    assert params[-2:] == ("usr_1", "qa_1")


def test_update_card_rejects_empty_keywords() -> None:
    connection = FakeConnection()
    repo = PostgresQACardRepository(connection, "usr_1")

    with pytest.raises(ValueError, match="keywords must contain at least one non-empty string"):
        repo.update_card("qa_1", keywords=[])

    assert connection.executed == []


def test_delete_card_filters_by_user_id_and_hides_cross_user_existence() -> None:
    connection = FakeConnection()
    repo = PostgresQACardRepository(connection, "usr_1")

    deleted = repo.delete_card("qa_cross_user")

    assert deleted is False
    sql, params = connection.executed[0]
    assert "DELETE FROM qa_cards WHERE user_id = %s AND card_id = %s" in sql
    assert params == ("usr_1", "qa_cross_user")
    assert connection.commit_count == 1


def test_delete_card_returns_true_only_when_user_scoped_row_was_deleted() -> None:
    connection = FakeConnection()
    connection.next_rowcount = 1
    repo = PostgresQACardRepository(connection, "usr_1")

    assert repo.delete_card("qa_1") is True


def test_update_embedding_status_updates_only_user_scoped_card() -> None:
    connection = FakeConnection()
    connection.next_rowcount = 1
    repo = PostgresQACardRepository(connection, "usr_1")

    updated = repo.update_embedding_status(
        "qa_1",
        status="ready",
        embedding=[0.1, 0.2],
        embedding_model="text-embedding-v4",
    )

    assert updated is True
    sql, params = connection.executed[0]
    assert "UPDATE qa_cards SET embedding_status = %s, embedding = %s::vector, embedding_model = %s" in sql
    assert "WHERE user_id = %s AND card_id = %s" in sql
    assert params == ("ready", "[0.1,0.2]", "text-embedding-v4", "usr_1", "qa_1")
    assert connection.commit_count == 1


def test_mark_card_vectorized_sets_ready_only_for_user_scoped_card() -> None:
    connection = FakeConnection()
    connection.next_rowcount = 1
    repo = PostgresQACardRepository(connection, "usr_1")

    updated = repo.mark_card_vectorized("qa_1")

    assert updated is True
    sql, params = connection.executed[0]
    assert "UPDATE qa_cards SET embedding_status = 'ready', updated_at = now()" in sql
    assert "WHERE user_id = %s AND card_id = %s AND embedding IS NOT NULL" in sql
    assert params == ("usr_1", "qa_1")
    assert connection.commit_count == 1


def test_mark_card_vectorized_returns_false_for_missing_or_cross_user_card() -> None:
    connection = FakeConnection()
    repo = PostgresQACardRepository(connection, "usr_1")

    updated = repo.mark_card_vectorized("qa_cross_user")

    assert updated is False
    sql, params = connection.executed[0]
    assert "WHERE user_id = %s AND card_id = %s" in sql
    assert params == ("usr_1", "qa_cross_user")
    assert connection.commit_count == 1


def test_validate_category_matches_sqlite_repository_rules() -> None:
    assert PostgresQACardRepository.validate_category(" Agent 开发 ") == "Agent 开发"

    with pytest.raises(ValueError, match="fallback category"):
        PostgresQACardRepository.validate_category("其他")

    with pytest.raises(ValueError, match="at most 24 characters"):
        PostgresQACardRepository.validate_category("过长分类" * 10)


def test_category_filters_use_validation_before_sql() -> None:
    connection = FakeConnection()
    repo = PostgresQACardRepository(connection, "usr_1")

    with pytest.raises(ValueError, match="fallback category"):
        repo.search_cards("query", category="未分类")

    assert connection.executed == []


def test_update_embedding_status_rejects_ready_without_embedding() -> None:
    connection = FakeConnection()
    repo = PostgresQACardRepository(connection, "usr_1")

    with pytest.raises(ValueError, match="embedding is required"):
        repo.update_embedding_status("qa_1", status="ready")

    assert connection.executed == []


def test_update_embedding_status_can_clear_embedding_for_user_scoped_card() -> None:
    connection = FakeConnection()
    repo = PostgresQACardRepository(connection, "usr_1")

    updated = repo.update_embedding_status("qa_missing", status="failed")

    assert updated is False
    sql, params = connection.executed[0]
    assert "WHERE user_id = %s AND card_id = %s" in sql
    assert params == ("failed", None, None, "usr_1", "qa_missing")
