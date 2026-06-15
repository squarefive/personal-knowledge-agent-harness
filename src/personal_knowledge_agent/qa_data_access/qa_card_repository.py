from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .qa_card_models import QACard, SearchResult

FORBIDDEN_CATEGORIES = {"其他", "未分类", "杂项", "默认分类", "未知", "待分类"}
CATEGORY_CHECK_SQL = (
    "length(trim(category)) BETWEEN 1 AND 24 "
    "AND category NOT IN ('其他', '未分类', '杂项', '默认分类', '未知', '待分类')"
)


class QACardRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize_schema()

    def initialize_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS qa_cards (
                  id TEXT PRIMARY KEY,
                  question TEXT NOT NULL,
                  answer TEXT NOT NULL,
                  summary TEXT NOT NULL,
                  keywords TEXT NOT NULL,
                  category TEXT NOT NULL CHECK (
                    length(trim(category)) BETWEEN 1 AND 24
                    AND category NOT IN ('其他', '未分类', '杂项', '默认分类', '未知', '待分类')
                  ),
                  source_type TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  is_vectorized INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._ensure_column(conn, "qa_cards", "is_vectorized", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "qa_cards", "category", "TEXT")

    def save_card(
        self,
        *,
        question: str,
        answer: str,
        summary: str,
        keywords: list[str],
        category: str,
    ) -> QACard:
        self._require_text("question", question)
        self._require_text("answer", answer)
        self._require_text("summary", summary)
        clean_keywords = self._clean_keywords(keywords)
        clean_category = self.validate_category(category)
        now = self._now()
        card = QACard(
            id=f"qa_{uuid.uuid4().hex}",
            question=question.strip(),
            answer=answer.strip(),
            summary=summary.strip(),
            keywords=clean_keywords,
            category=clean_category,
            source_type="manual_qa",
            created_at=now,
            updated_at=now,
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO qa_cards (
                  id, question, answer, summary, keywords, category,
                  source_type, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card.id,
                    card.question,
                    card.answer,
                    card.summary,
                    json.dumps(card.keywords, ensure_ascii=False),
                    card.category,
                    card.source_type,
                    card.created_at,
                    card.updated_at,
                ),
            )
        return card

    def read_card(self, card_id: str) -> QACard | None:
        self._require_text("card_id", card_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM qa_cards WHERE id = ?",
                (card_id.strip(),),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_card(row)

    def update_card(
        self,
        card_id: str,
        *,
        question: str | None = None,
        answer: str | None = None,
        summary: str | None = None,
        keywords: list[str] | None = None,
        category: str | None = None,
    ) -> QACard | None:
        self._require_text("card_id", card_id)
        current = self.read_card(card_id)
        if current is None:
            return None
        if question is None and answer is None and summary is None and keywords is None and category is None:
            raise ValueError("at least one field must be provided")

        next_question = current.question if question is None else question.strip()
        next_answer = current.answer if answer is None else answer.strip()
        next_summary = current.summary if summary is None else summary.strip()
        next_keywords = current.keywords if keywords is None else self._clean_keywords(keywords)
        next_category = current.category if category is None else self.validate_category(category)
        self._require_text("question", next_question)
        self._require_text("answer", next_answer)
        self._require_text("summary", next_summary)
        updated_at = self._now()

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE qa_cards
                SET question = ?, answer = ?, summary = ?, keywords = ?, category = ?, updated_at = ?, is_vectorized = 0
                WHERE id = ?
                """,
                (
                    next_question,
                    next_answer,
                    next_summary,
                    json.dumps(next_keywords, ensure_ascii=False),
                    next_category,
                    updated_at,
                    card_id.strip(),
                ),
            )
        return self.read_card(card_id)

    def delete_card(self, card_id: str) -> bool:
        self._require_text("card_id", card_id)
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM qa_cards WHERE id = ?", (card_id.strip(),))
        return cursor.rowcount > 0

    def list_recent_cards(self, limit: int = 10, category: str | None = None) -> list[QACard]:
        safe_limit = self._safe_limit(limit)
        clean_category = self.validate_optional_category(category)
        where, params = self._category_filter(clean_category)
        sql = f"SELECT * FROM qa_cards{where} ORDER BY created_at DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(sql, (*params, safe_limit)).fetchall()
        cards = [self._row_to_card(row) for row in rows]
        return cards

    def list_unvectorized_cards(self, limit: int | None = None) -> list[QACard]:
        params: tuple[int, ...] = ()
        sql = "SELECT * FROM qa_cards WHERE is_vectorized = 0 ORDER BY created_at ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params = (self._safe_limit(limit),)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_card(row) for row in rows]

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

    def mark_card_vectorized(self, card_id: str) -> bool:
        self._require_text("card_id", card_id)
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE qa_cards SET is_vectorized = 1 WHERE id = ?",
                (card_id.strip(),),
            )
        return cursor.rowcount > 0

    def search_cards(self, query: str, limit: int = 5, category: str | None = None) -> list[SearchResult]:
        self._require_text("query", query)
        clean_category = self.validate_optional_category(category)
        terms = self._search_terms(query)
        safe_limit = self._safe_limit(limit)
        clauses: list[str] = []
        params: list[str] = []
        for term in terms:
            pattern = f"%{term}%"
            clauses.append(
                """
                question LIKE ? OR answer LIKE ? OR summary LIKE ? OR keywords LIKE ?
                """
            )
            params.extend([pattern, pattern, pattern, pattern])

        where = " OR ".join(f"({clause})" for clause in clauses)
        if clean_category is not None:
            where = f"category = ? AND ({where})"
            params.insert(0, clean_category)
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM qa_cards WHERE {where}", params).fetchall()

        results: list[SearchResult] = []
        for row in rows:
            card = self._row_to_card(row)
            score = self._score_card(card, terms)
            if score > 0:
                results.append(
                    SearchResult(
                        card_id=card.id,
                        question=card.question,
                        summary=card.summary,
                        answer_snippet=self._snippet(card.answer),
                        score=score,
                        source_type=card.source_type,
                        created_at=card.created_at,
                        category=card.category,
                    )
                )
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:safe_limit]

    def list_cards_missing_category(self) -> list[QACard]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM qa_cards WHERE category IS NULL OR length(trim(category)) = 0 ORDER BY created_at ASC"
            ).fetchall()
        return [self._row_to_card(row) for row in rows]

    def set_card_category(self, card_id: str, category: str) -> bool:
        self._require_text("card_id", card_id)
        clean_category = self.validate_category(category)
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE qa_cards SET category = ?, updated_at = ? WHERE id = ?",
                (clean_category, self._now(), card_id.strip()),
            )
        return cursor.rowcount > 0

    def enforce_category_constraints(self) -> None:
        with self._connect() as conn:
            invalid_rows = conn.execute(
                f"SELECT id FROM qa_cards WHERE category IS NULL OR NOT ({CATEGORY_CHECK_SQL})"
            ).fetchall()
            if invalid_rows:
                ids = ", ".join(row["id"] for row in invalid_rows)
                raise ValueError(f"cannot enforce category constraints; invalid cards: {ids}")
            conn.execute("ALTER TABLE qa_cards RENAME TO qa_cards_old")
            conn.execute(
                """
                CREATE TABLE qa_cards (
                  id TEXT PRIMARY KEY,
                  question TEXT NOT NULL,
                  answer TEXT NOT NULL,
                  summary TEXT NOT NULL,
                  keywords TEXT NOT NULL,
                  category TEXT NOT NULL CHECK (
                    length(trim(category)) BETWEEN 1 AND 24
                    AND category NOT IN ('其他', '未分类', '杂项', '默认分类', '未知', '待分类')
                  ),
                  source_type TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  is_vectorized INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                INSERT INTO qa_cards (
                  id, question, answer, summary, keywords, category,
                  source_type, created_at, updated_at, is_vectorized
                )
                SELECT
                  id, question, answer, summary, keywords, category,
                  source_type, created_at, updated_at, is_vectorized
                FROM qa_cards_old
                """
            )
            conn.execute("DROP TABLE qa_cards_old")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_card(row: sqlite3.Row) -> QACard:
        return QACard(
            id=row["id"],
            question=row["question"],
            answer=row["answer"],
            summary=row["summary"],
            keywords=json.loads(row["keywords"]),
            category=row["category"] or "",
            source_type=row["source_type"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            is_vectorized=row["is_vectorized"],
        )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        declaration: str,
    ) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {row["name"] for row in rows}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _require_text(name: str, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    @staticmethod
    def validate_category(category: str) -> str:
        if not isinstance(category, str) or not category.strip():
            raise ValueError("category must be a non-empty string")
        clean = category.strip()
        if len(clean) > 24:
            raise ValueError("category must be at most 24 characters")
        if clean in FORBIDDEN_CATEGORIES:
            raise ValueError(f"category cannot be a fallback category: {clean}")
        return clean

    @classmethod
    def validate_optional_category(cls, category: str | None) -> str | None:
        if category is None:
            return None
        return cls.validate_category(category)

    @staticmethod
    def _category_filter(category: str | None) -> tuple[str, tuple[str, ...]]:
        if category is None:
            return "", ()
        return " WHERE category = ?", (category,)

    @staticmethod
    def _clean_keywords(keywords: list[str]) -> list[str]:
        if not isinstance(keywords, list):
            raise ValueError("keywords must be a list of strings")
        clean = [keyword.strip() for keyword in keywords if isinstance(keyword, str) and keyword.strip()]
        if not clean:
            raise ValueError("keywords must contain at least one non-empty string")
        return clean

    @staticmethod
    def _safe_limit(limit: int) -> int:
        if not isinstance(limit, int) or limit < 1:
            return 10
        return min(limit, 50)

    @staticmethod
    def _search_terms(query: str) -> list[str]:
        raw_terms = [query.strip(), *query.strip().split()]
        terms: list[str] = []
        for term in raw_terms:
            if term and term not in terms:
                terms.append(term)
        return terms

    @staticmethod
    def _score_card(card: QACard, terms: list[str]) -> int:
        score = 0
        keywords_text = " ".join(card.keywords)
        fields = [
            (card.question, 4),
            (card.summary, 3),
            (keywords_text, 2),
            (card.answer, 1),
        ]
        for term in terms:
            lowered = term.lower()
            for value, weight in fields:
                if lowered in value.lower():
                    score += weight
        return score

    @staticmethod
    def _snippet(answer: str, length: int = 160) -> str:
        clean = " ".join(answer.split())
        if len(clean) <= length:
            return clean
        return f"{clean[: length - 3]}..."
