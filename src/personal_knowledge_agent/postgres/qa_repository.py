from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from psycopg.types.json import Jsonb

from ..qa_data_access.qa_card_models import QACard, SearchResult, SemanticSearchHit
from .constants import PostgresConstants as postgres_constants


class PostgresConnection(Protocol):
    def execute(self, query: str, params: Sequence[object] = ()) -> object: ...


class PostgresQACardRepository:
    def __init__(self, connection: PostgresConnection, user_id: str) -> None:
        _require_text("user_id", user_id)
        self._connection = connection
        self._user_id = user_id.strip()

    def create_card(
        self,
        *,
        question: str,
        answer: str,
        summary: str,
        keywords: list[str],
        category: str,
        source_type: str = postgres_constants.DEFAULT_QA_SOURCE_TYPE,
        card_id: str | None = None,
    ) -> QACard:
        clean_question = _require_text("question", question)
        clean_answer = _require_text("answer", answer)
        clean_summary = _require_text("summary", summary)
        clean_category = self.validate_category(category)
        clean_source_type = _require_text("source_type", source_type)
        clean_keywords = _clean_keywords(keywords)
        clean_card_id = card_id.strip() if card_id is not None else f"{postgres_constants.QA_CARD_ID_PREFIX}_{uuid.uuid4().hex}"
        _require_text("card_id", clean_card_id)

        cursor = self._connection.execute(
            """
            INSERT INTO qa_cards (
              card_id,
              user_id,
              question,
              answer,
              summary,
              keywords,
              category,
              source_type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING
              card_id,
              question,
              answer,
              summary,
              keywords,
              category,
              source_type,
              created_at,
              updated_at,
              embedding_status
            """,
            (
                clean_card_id,
                self._user_id,
                clean_question,
                clean_answer,
                clean_summary,
                Jsonb(clean_keywords),
                clean_category,
                clean_source_type,
            ),
        )
        row = _fetchone(cursor)
        self._commit()
        if row is None:
            return QACard(
                id=clean_card_id,
                question=clean_question,
                answer=clean_answer,
                summary=clean_summary,
                keywords=clean_keywords,
                category=clean_category,
                source_type=clean_source_type,
                created_at="",
                updated_at="",
            )
        return _row_to_card(row)

    def save_card(
        self,
        *,
        question: str,
        answer: str,
        summary: str,
        keywords: list[str],
        category: str,
        source_type: str = postgres_constants.DEFAULT_QA_SOURCE_TYPE,
    ) -> QACard:
        return self.create_card(
            question=question,
            answer=answer,
            summary=summary,
            keywords=keywords,
            category=category,
            source_type=source_type,
        )

    def get_card(self, card_id: str) -> QACard | None:
        clean_card_id = _require_text("card_id", card_id)
        cursor = self._connection.execute(
            """
            SELECT
              card_id,
              question,
              answer,
              summary,
              keywords,
              category,
              source_type,
              created_at,
              updated_at,
              embedding_status
            FROM qa_cards
            WHERE user_id = %s AND card_id = %s
            """,
            (self._user_id, clean_card_id),
        )
        row = _fetchone(cursor)
        if row is None:
            return None
        return _row_to_card(row)

    def read_card(self, card_id: str) -> QACard | None:
        return self.get_card(card_id)

    def list_recent_cards(self, limit: int = postgres_constants.DEFAULT_QA_LIMIT, category: str | None = None) -> list[QACard]:
        safe_limit = _safe_limit(limit)
        clean_category = self.validate_optional_category(category)
        if clean_category is None:
            cursor = self._connection.execute(
                """
                SELECT
                  card_id,
                  question,
                  answer,
                  summary,
                  keywords,
                  category,
                  source_type,
                  created_at,
                  updated_at,
                  embedding_status
                FROM qa_cards
                WHERE user_id = %s
                ORDER BY created_at DESC, card_id DESC
                LIMIT %s
                """,
                (self._user_id, safe_limit),
            )
        else:
            cursor = self._connection.execute(
                """
                SELECT
                  card_id,
                  question,
                  answer,
                  summary,
                  keywords,
                  category,
                  source_type,
                  created_at,
                  updated_at,
                  embedding_status
                FROM qa_cards
                WHERE user_id = %s AND category = %s
                ORDER BY created_at DESC, card_id DESC
                LIMIT %s
                """,
                (self._user_id, clean_category, safe_limit),
            )
        return [_row_to_card(row) for row in _fetchall(cursor)]

    def list_all_cards(self, category: str | None = None) -> list[QACard]:
        clean_category = self.validate_optional_category(category)
        if clean_category is None:
            cursor = self._connection.execute(
                """
                SELECT
                  card_id,
                  question,
                  answer,
                  summary,
                  keywords,
                  category,
                  source_type,
                  created_at,
                  updated_at,
                  embedding_status
                FROM qa_cards
                WHERE user_id = %s
                ORDER BY created_at ASC
                """,
                (self._user_id,),
            )
        else:
            cursor = self._connection.execute(
                """
                SELECT
                  card_id,
                  question,
                  answer,
                  summary,
                  keywords,
                  category,
                  source_type,
                  created_at,
                  updated_at,
                  embedding_status
                FROM qa_cards
                WHERE user_id = %s AND category = %s
                ORDER BY created_at ASC
                """,
                (self._user_id, clean_category),
            )
        return [_row_to_card(row) for row in _fetchall(cursor)]

    def list_unvectorized_cards(self, limit: int | None = None) -> list[QACard]:
        if limit is None:
            cursor = self._connection.execute(
                """
                SELECT
                  card_id,
                  question,
                  answer,
                  summary,
                  keywords,
                  category,
                  source_type,
                  created_at,
                  updated_at,
                  embedding_status
                FROM qa_cards
                WHERE user_id = %s AND embedding_status != %s
                ORDER BY created_at ASC
                """,
                (self._user_id, postgres_constants.EMBEDDING_STATUS_READY),
            )
        else:
            cursor = self._connection.execute(
                """
                SELECT
                  card_id,
                  question,
                  answer,
                  summary,
                  keywords,
                  category,
                  source_type,
                  created_at,
                  updated_at,
                  embedding_status
                FROM qa_cards
                WHERE user_id = %s AND embedding_status != %s
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (self._user_id, postgres_constants.EMBEDDING_STATUS_READY, _safe_limit(limit)),
            )
        return [_row_to_card(row) for row in _fetchall(cursor)]

    def read_cards_by_ids(self, card_ids: list[str], category: str | None = None) -> list[QACard]:
        clean_category = self.validate_optional_category(category)
        cards: list[QACard] = []
        for card_id in card_ids:
            if not isinstance(card_id, str) or not card_id.strip():
                continue
            card = self.read_card(card_id)
            if card is not None and (clean_category is None or card.category == clean_category):
                cards.append(card)
        return cards

    def search_keyword_cards(
        self,
        query: str,
        limit: int = postgres_constants.DEFAULT_QA_SEARCH_LIMIT,
        category: str | None = None,
    ) -> list[SearchResult]:
        clean_query = _require_text("query", query)
        safe_limit = _safe_limit(limit)
        clean_category = self.validate_optional_category(category)
        pattern = f"%{clean_query}%"
        if clean_category is None:
            cursor = self._connection.execute(
                """
                SELECT
                  card_id,
                  question,
                  summary,
                  answer,
                  source_type,
                  created_at,
                  category
                FROM qa_cards
                WHERE user_id = %s
                  AND (
                    question ILIKE %s
                    OR answer ILIKE %s
                    OR summary ILIKE %s
                    OR keywords::text ILIKE %s
                    OR category ILIKE %s
                  )
                ORDER BY updated_at DESC, card_id DESC
                LIMIT %s
                """,
                (self._user_id, pattern, pattern, pattern, pattern, pattern, safe_limit),
            )
        else:
            cursor = self._connection.execute(
                """
                SELECT
                  card_id,
                  question,
                  summary,
                  answer,
                  source_type,
                  created_at,
                  category
                FROM qa_cards
                WHERE user_id = %s
                  AND category = %s
                  AND (
                    question ILIKE %s
                    OR answer ILIKE %s
                    OR summary ILIKE %s
                    OR keywords::text ILIKE %s
                    OR category ILIKE %s
                  )
                ORDER BY updated_at DESC, card_id DESC
                LIMIT %s
                """,
                (self._user_id, clean_category, pattern, pattern, pattern, pattern, pattern, safe_limit),
            )
        return [_row_to_search_result(row) for row in _fetchall(cursor)]

    def search_cards(
        self,
        query: str,
        limit: int = postgres_constants.DEFAULT_QA_SEARCH_LIMIT,
        category: str | None = None,
    ) -> list[SearchResult]:
        return self.search_keyword_cards(query=query, limit=limit, category=category)

    def search_vector_cards(
        self,
        embedding: Sequence[float],
        limit: int = postgres_constants.DEFAULT_QA_SEARCH_LIMIT,
        category: str | None = None,
    ) -> list[SemanticSearchHit]:
        vector = _vector_literal(embedding)
        if vector is None:
            raise ValueError("embedding must not be empty")
        safe_limit = _safe_limit(limit)
        clean_category = self.validate_optional_category(category)
        if clean_category is None:
            cursor = self._connection.execute(
                """
                SELECT
                  card_id,
                  1 - (embedding <=> %s::vector) AS score
                FROM qa_cards
                WHERE user_id = %s
                  AND embedding_status = %s
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vector, self._user_id, postgres_constants.EMBEDDING_STATUS_READY, vector, safe_limit),
            )
        else:
            cursor = self._connection.execute(
                """
                SELECT
                  card_id,
                  1 - (embedding <=> %s::vector) AS score
                FROM qa_cards
                WHERE user_id = %s
                  AND embedding_status = %s
                  AND embedding IS NOT NULL
                  AND category = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vector, self._user_id, postgres_constants.EMBEDDING_STATUS_READY, clean_category, vector, safe_limit),
            )
        return [_row_to_semantic_hit(row) for row in _fetchall(cursor)]

    def update_card(
        self,
        card_id: str,
        *,
        question: str | None = None,
        answer: str | None = None,
        summary: str | None = None,
        keywords: list[str] | None = None,
        category: str | None = None,
        source_type: str | None = None,
    ) -> QACard | None:
        clean_card_id = _require_text("card_id", card_id)
        if all(value is None for value in (question, answer, summary, keywords, category, source_type)):
            raise ValueError("at least one field must be provided")

        cursor = self._connection.execute(
            """
            UPDATE qa_cards
            SET
              question = COALESCE(%s, question),
              answer = COALESCE(%s, answer),
              summary = COALESCE(%s, summary),
              keywords = COALESCE(%s, keywords),
              category = COALESCE(%s, category),
              source_type = COALESCE(%s, source_type),
              embedding = NULL,
              embedding_status = %s,
              embedding_model = NULL,
              updated_at = now()
            WHERE user_id = %s AND card_id = %s
            RETURNING
              card_id,
              question,
              answer,
              summary,
              keywords,
              category,
              source_type,
              created_at,
              updated_at,
              embedding_status
            """,
            (
                _optional_text("question", question),
                _optional_text("answer", answer),
                _optional_text("summary", summary),
                Jsonb(_clean_keywords(keywords)) if keywords is not None else None,
                self.validate_optional_category(category),
                _optional_text("source_type", source_type),
                postgres_constants.EMBEDDING_STATUS_PENDING,
                self._user_id,
                clean_card_id,
            ),
        )
        row = _fetchone(cursor)
        self._commit()
        if row is None:
            return None
        return _row_to_card(row)

    def delete_card(self, card_id: str) -> bool:
        clean_card_id = _require_text("card_id", card_id)
        cursor = self._connection.execute(
            """
            DELETE FROM qa_cards
            WHERE user_id = %s AND card_id = %s
            """,
            (self._user_id, clean_card_id),
        )
        self._commit()
        return _rowcount(cursor) > 0

    def mark_card_vectorized(self, card_id: str) -> bool:
        clean_card_id = _require_text("card_id", card_id)
        cursor = self._connection.execute(
            """
            UPDATE qa_cards
            SET
              embedding_status = %s,
              updated_at = now()
            WHERE user_id = %s AND card_id = %s AND embedding IS NOT NULL
            """,
            (postgres_constants.EMBEDDING_STATUS_READY, self._user_id, clean_card_id),
        )
        self._commit()
        return _rowcount(cursor) > 0

    @staticmethod
    def validate_category(category: str) -> str:
        if not isinstance(category, str) or not category.strip():
            raise ValueError("category must be a non-empty string")
        clean = category.strip()
        if len(clean) > postgres_constants.MAX_CATEGORY_LENGTH:
            raise ValueError("category must be at most 24 characters")
        if clean in postgres_constants.FORBIDDEN_CATEGORIES:
            raise ValueError(f"category cannot be a fallback category: {clean}")
        return clean

    @classmethod
    def validate_optional_category(cls, category: str | None) -> str | None:
        if category is None:
            return None
        return cls.validate_category(category)

    def update_embedding_status(
        self,
        card_id: str,
        *,
        status: str,
        embedding: Sequence[float] | None = None,
        embedding_model: str | None = None,
    ) -> bool:
        clean_card_id = _require_text("card_id", card_id)
        clean_status = _require_text("status", status)
        if clean_status not in postgres_constants.EMBEDDING_STATUSES:
            raise ValueError("status must be pending, ready, or failed")
        if clean_status == postgres_constants.EMBEDDING_STATUS_READY and embedding is None:
            raise ValueError("embedding is required when status is ready")
        clean_model = _optional_text("embedding_model", embedding_model)

        cursor = self._connection.execute(
            """
            UPDATE qa_cards
            SET
              embedding_status = %s,
              embedding = %s::vector,
              embedding_model = %s,
              updated_at = now()
            WHERE user_id = %s AND card_id = %s
            """,
            (clean_status, _vector_literal(embedding), clean_model, self._user_id, clean_card_id),
        )
        self._commit()
        return _rowcount(cursor) > 0

    def _commit(self) -> None:
        commit = getattr(self._connection, "commit", None)
        if callable(commit):
            commit()


def _fetchone(cursor: object) -> object | None:
    fetchone = getattr(cursor, "fetchone")
    return fetchone()


def _fetchall(cursor: object) -> list[object]:
    fetchall = getattr(cursor, "fetchall")
    return list(fetchall())


def _rowcount(cursor: object) -> int:
    rowcount = getattr(cursor, "rowcount", 0)
    return int(rowcount)


def _row_to_card(row: object) -> QACard:
    embedding_status = _row_value(row, 9, "embedding_status")
    return QACard(
        id=_row_value(row, 0, "card_id"),
        question=_row_value(row, 1, "question"),
        answer=_row_value(row, 2, "answer"),
        summary=_row_value(row, 3, "summary"),
        keywords=_keywords_from_value(_row_value(row, 4, "keywords")),
        category=_row_value(row, 5, "category"),
        source_type=_row_value(row, 6, "source_type"),
        created_at=_stringify_timestamp(_row_value(row, 7, "created_at")),
        updated_at=_stringify_timestamp(_row_value(row, 8, "updated_at")),
        is_vectorized=1 if embedding_status == postgres_constants.EMBEDDING_STATUS_READY else 0,
    )


def _row_to_search_result(row: object) -> SearchResult:
    answer = _row_value(row, 3, "answer")
    return SearchResult(
        card_id=_row_value(row, 0, "card_id"),
        question=_row_value(row, 1, "question"),
        summary=_row_value(row, 2, "summary"),
        answer_snippet=_snippet(answer),
        score=postgres_constants.SEARCH_RESULT_SCORE,
        source_type=_row_value(row, 4, "source_type"),
        created_at=_stringify_timestamp(_row_value(row, 5, "created_at")),
        category=_row_value(row, 6, "category"),
    )


def _row_to_semantic_hit(row: object) -> SemanticSearchHit:
    return SemanticSearchHit(
        card_id=str(_row_value(row, 0, "card_id")),
        score=float(_row_value(row, 1, "score")),
    )


def _row_value(row: object, index: int, key: str) -> object:
    if isinstance(row, dict):
        return row[key]
    return row[index]  # type: ignore[index]


def _keywords_from_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, str):
        loaded = json.loads(value)
        if isinstance(loaded, list):
            return [item for item in loaded if isinstance(item, str)]
    return []


def _stringify_timestamp(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_text(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    return _require_text(name, value)


def _clean_keywords(keywords: list[str]) -> list[str]:
    if not isinstance(keywords, list):
        raise ValueError("keywords must be a list of strings")
    clean = [keyword.strip() for keyword in keywords if isinstance(keyword, str) and keyword.strip()]
    if not clean:
        raise ValueError("keywords must contain at least one non-empty string")
    return clean


def _safe_limit(limit: int) -> int:
    if not isinstance(limit, int) or limit < 1:
        return postgres_constants.DEFAULT_QA_LIMIT
    return min(limit, postgres_constants.MAX_QA_LIMIT)


def _vector_literal(embedding: Sequence[float] | None) -> str | None:
    if embedding is None:
        return None
    if not embedding:
        return None
    return "[" + ",".join(str(value) for value in embedding) + "]"


def _snippet(answer: object, length: int = postgres_constants.SEARCH_SNIPPET_LENGTH) -> str:
    clean = " ".join(str(answer).split())
    if len(clean) <= length:
        return clean
    return f"{clean[: length - len(postgres_constants.SEARCH_SNIPPET_ELLIPSIS)]}{postgres_constants.SEARCH_SNIPPET_ELLIPSIS}"
