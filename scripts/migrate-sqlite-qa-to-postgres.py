from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from psycopg.types.json import Jsonb

from personal_knowledge_agent.postgres import close_postgres_pool, create_postgres_pool


LEGACY_SOURCE = "sqlite_qa_cards"
REQUIRED_SQLITE_COLUMNS = (
    "id",
    "question",
    "answer",
    "summary",
    "keywords",
    "category",
    "source_type",
    "created_at",
    "updated_at",
)


class MigrationError(Exception):
    pass


class PostgresConnection(Protocol):
    def execute(self, query: str, params: Sequence[object] = ()) -> object: ...


@dataclass(frozen=True)
class LegacyQACard:
    legacy_card_id: str
    question: str
    answer: str
    summary: str
    keywords: list[str]
    category: str
    source_type: str
    created_at: object
    updated_at: object


@dataclass(frozen=True)
class MigrationSummary:
    total: int
    upserted: int
    dry_run: bool
    user_id: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy SQLite Q&A cards into PostgreSQL.")
    parser.add_argument("--sqlite-db", required=True, type=Path, help="Path to the legacy SQLite database.")
    parser.add_argument("--target-email", required=True, help="Existing PostgreSQL user email to own migrated cards.")
    parser.add_argument("--database-url", required=True, help="PostgreSQL database URL.")
    parser.add_argument("--dry-run", action="store_true", help="Read and validate data without writing PostgreSQL.")
    return parser.parse_args(argv)


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized:
        raise MigrationError("target email must not be empty")
    return normalized


def migrate_sqlite_qa_to_postgres(
    *,
    sqlite_db: Path,
    postgres_connection: PostgresConnection,
    target_email: str,
    dry_run: bool = False,
) -> MigrationSummary:
    normalized_email = normalize_email(target_email)
    user_id = lookup_user_id(postgres_connection, normalized_email)
    if user_id is None:
        raise MigrationError(f"target user does not exist for email: {normalized_email}")

    with sqlite3.connect(sqlite_db) as sqlite_connection:
        sqlite_connection.row_factory = sqlite3.Row
        cards = read_legacy_qa_cards(sqlite_connection)

    if dry_run:
        return MigrationSummary(total=len(cards), upserted=0, dry_run=True, user_id=user_id)

    for card in cards:
        upsert_qa_card(postgres_connection, user_id=user_id, card=card)

    commit = getattr(postgres_connection, "commit", None)
    if callable(commit):
        commit()

    return MigrationSummary(total=len(cards), upserted=len(cards), dry_run=False, user_id=user_id)


def lookup_user_id(postgres_connection: PostgresConnection, email: str) -> str | None:
    cursor = postgres_connection.execute(
        """
        SELECT user_id
        FROM users
        WHERE email = %s
        """,
        (email,),
    )
    row = _fetchone(cursor)
    if row is None:
        return None
    if isinstance(row, dict):
        return str(row["user_id"])
    return str(row[0])  # type: ignore[index]


def read_legacy_qa_cards(sqlite_connection: sqlite3.Connection) -> list[LegacyQACard]:
    columns = _qa_cards_columns(sqlite_connection)
    missing_columns = [column for column in REQUIRED_SQLITE_COLUMNS if column not in columns]
    if missing_columns:
        raise MigrationError(f"legacy qa_cards table is missing required columns: {', '.join(missing_columns)}")

    select_columns = list(REQUIRED_SQLITE_COLUMNS)
    if "is_vectorized" in columns:
        select_columns.append("is_vectorized")

    rows = sqlite_connection.execute(
        f"""
        SELECT {", ".join(select_columns)}
        FROM qa_cards
        ORDER BY created_at ASC, id ASC
        """
    ).fetchall()
    return [_legacy_card_from_row(row) for row in rows]


def upsert_qa_card(postgres_connection: PostgresConnection, *, user_id: str, card: LegacyQACard) -> None:
    postgres_connection.execute(
        """
        INSERT INTO qa_cards (
          card_id,
          user_id,
          question,
          answer,
          summary,
          keywords,
          category,
          source_type,
          embedding,
          embedding_status,
          embedding_model,
          legacy_source,
          legacy_card_id,
          created_at,
          updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, NULL, %s, %s, %s, %s)
        ON CONFLICT (user_id, legacy_source, legacy_card_id)
        DO UPDATE SET
          question = EXCLUDED.question,
          answer = EXCLUDED.answer,
          summary = EXCLUDED.summary,
          keywords = EXCLUDED.keywords,
          category = EXCLUDED.category,
          source_type = EXCLUDED.source_type,
          embedding = NULL,
          embedding_status = 'pending',
          embedding_model = NULL,
          updated_at = EXCLUDED.updated_at
        """,
        (
            _migrated_card_id(user_id, card.legacy_card_id),
            user_id,
            card.question,
            card.answer,
            card.summary,
            Jsonb(card.keywords),
            card.category,
            card.source_type,
            "pending",
            LEGACY_SOURCE,
            card.legacy_card_id,
            card.created_at,
            card.updated_at,
        ),
    )


def _qa_cards_columns(sqlite_connection: sqlite3.Connection) -> set[str]:
    rows = sqlite_connection.execute("PRAGMA table_info(qa_cards)").fetchall()
    if not rows:
        raise MigrationError("legacy SQLite database does not contain qa_cards table")
    return {str(row[1]) for row in rows}


def _legacy_card_from_row(row: sqlite3.Row) -> LegacyQACard:
    legacy_card_id = str(row["id"])
    return LegacyQACard(
        legacy_card_id=legacy_card_id,
        question=str(row["question"]),
        answer=str(row["answer"]),
        summary=str(row["summary"]),
        keywords=parse_keywords(row["keywords"], legacy_card_id=legacy_card_id),
        category=str(row["category"]),
        source_type=str(row["source_type"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def parse_keywords(value: object, *, legacy_card_id: str) -> list[str]:
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise MigrationError(f"invalid keywords JSON for legacy card id {legacy_card_id}") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise MigrationError(f"keywords must be a JSON list of strings for legacy card id {legacy_card_id}")
    return parsed


def _migrated_card_id(user_id: str, legacy_card_id: str) -> str:
    value = f"{user_id}:{LEGACY_SOURCE}:{legacy_card_id}"
    return f"qa_{uuid.uuid5(uuid.NAMESPACE_URL, value).hex}"


def _fetchone(cursor: object) -> object | None:
    fetchone = getattr(cursor, "fetchone")
    return fetchone()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    pool = create_postgres_pool(args.database_url, min_size=1, max_size=1)
    try:
        with pool.connection() as connection:
            summary = migrate_sqlite_qa_to_postgres(
                sqlite_db=args.sqlite_db,
                postgres_connection=connection,
                target_email=args.target_email,
                dry_run=args.dry_run,
            )
    except MigrationError as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 2
    finally:
        close_postgres_pool(pool)

    mode = "dry-run" if summary.dry_run else "migrated"
    print(f"{mode}: total={summary.total} upserted={summary.upserted} user_id={summary.user_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
