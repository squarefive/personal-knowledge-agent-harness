from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .schemas import QACard, SearchResult

logger = logging.getLogger(__name__)


class SQLiteStore:
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
                  source_type TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """
            )
        logger.info("sqlite.schema.initialized")

    def save_card(
        self,
        *,
        question: str,
        answer: str,
        summary: str,
        keywords: list[str],
    ) -> QACard:
        self._require_text("question", question)
        self._require_text("answer", answer)
        self._require_text("summary", summary)
        clean_keywords = self._clean_keywords(keywords)
        now = self._now()
        card = QACard(
            id=f"qa_{uuid.uuid4().hex}",
            question=question.strip(),
            answer=answer.strip(),
            summary=summary.strip(),
            keywords=clean_keywords,
            source_type="manual_qa",
            created_at=now,
            updated_at=now,
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO qa_cards (
                  id, question, answer, summary, keywords,
                  source_type, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card.id,
                    card.question,
                    card.answer,
                    card.summary,
                    json.dumps(card.keywords, ensure_ascii=False),
                    card.source_type,
                    card.created_at,
                    card.updated_at,
                ),
            )
        logger.info("sqlite.card.inserted", extra={"card_id": card.id})
        return card

    def read_card(self, card_id: str) -> QACard | None:
        self._require_text("card_id", card_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM qa_cards WHERE id = ?",
                (card_id.strip(),),
            ).fetchone()
        if row is None:
            logger.info("sqlite.card.not_found", extra={"card_id": card_id})
            return None
        return self._row_to_card(row)

    def list_recent_cards(self, limit: int = 10) -> list[QACard]:
        safe_limit = self._safe_limit(limit)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM qa_cards ORDER BY created_at DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        cards = [self._row_to_card(row) for row in rows]
        logger.info("sqlite.recent.completed", extra={"count": len(cards)})
        return cards

    def search_cards(self, query: str, limit: int = 5) -> list[SearchResult]:
        self._require_text("query", query)
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
                    )
                )
        results.sort(key=lambda item: item.score, reverse=True)
        limited = results[:safe_limit]
        logger.info("sqlite.search.completed", extra={"count": len(limited)})
        return limited

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
            source_type=row["source_type"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _require_text(name: str, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

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
