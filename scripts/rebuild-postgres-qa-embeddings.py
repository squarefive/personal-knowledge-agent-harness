from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from personal_knowledge_agent.agent_bootstrap.agent_runtime_config import (
    DEFAULT_QWEN_EMBEDDING_BASE_URL,
    DEFAULT_QWEN_EMBEDDING_DIMENSIONS,
    DEFAULT_QWEN_EMBEDDING_MODEL,
)
from personal_knowledge_agent.llm_clients import QwenEmbeddingClient
from personal_knowledge_agent.postgres import PostgresQACardRepository, close_postgres_pool, create_postgres_pool
from personal_knowledge_agent.postgres.qa_semantic_index import PostgresQASemanticIndex
from personal_knowledge_agent.security.secrets import read_secret


class RebuildError(Exception):
    pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild PostgreSQL pgvector embeddings for Q&A cards.")
    parser.add_argument("--target-email", required=True, help="Existing PostgreSQL user email whose cards should be rebuilt.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum unvectorized cards to process.")
    parser.add_argument("--database-url", help="PostgreSQL database URL. Defaults to DATABASE_URL/_FILE.")
    parser.add_argument("--embedding-base-url", default=DEFAULT_QWEN_EMBEDDING_BASE_URL)
    parser.add_argument("--embedding-model", default=DEFAULT_QWEN_EMBEDDING_MODEL)
    parser.add_argument("--embedding-dimensions", type=int, default=DEFAULT_QWEN_EMBEDDING_DIMENSIONS)
    return parser.parse_args(argv)


def rebuild_postgres_qa_embeddings(
    *,
    postgres_connection: object,
    target_email: str,
    dashscope_api_key: str | None,
    limit: int,
    embedding_base_url: str = DEFAULT_QWEN_EMBEDDING_BASE_URL,
    embedding_model: str = DEFAULT_QWEN_EMBEDDING_MODEL,
    embedding_dimensions: int = DEFAULT_QWEN_EMBEDDING_DIMENSIONS,
    embedding_client: object | None = None,
) -> dict[str, object]:
    if not dashscope_api_key:
        raise RebuildError("DASHSCOPE_API_KEY is required; database was not modified")
    user_id = lookup_user_id(postgres_connection, normalize_email(target_email))
    if user_id is None:
        raise RebuildError(f"target user does not exist for email: {normalize_email(target_email)}")
    repository = PostgresQACardRepository(postgres_connection, user_id)
    owns_embedding_client = embedding_client is None
    client = embedding_client or QwenEmbeddingClient(
        api_key=dashscope_api_key,
        base_url=embedding_base_url,
        model=embedding_model,
        dimensions=embedding_dimensions,
    )
    semantic_index = PostgresQASemanticIndex(repository, client)  # type: ignore[arg-type]
    try:
        cards = repository.list_unvectorized_cards(limit=limit)
        indexed = 0
        failed_card_ids: list[str] = []
        for card in cards:
            try:
                semantic_index.upsert_card(card)
                indexed += 1
            except Exception:
                repository.update_embedding_status(card.id, status="failed")
                failed_card_ids.append(card.id)
        return {
            "user_id": user_id,
            "total": len(cards),
            "indexed": indexed,
            "failed": len(failed_card_ids),
            "failed_card_ids": failed_card_ids,
        }
    finally:
        if owns_embedding_client:
            semantic_index.close()


def lookup_user_id(postgres_connection: object, email: str) -> str | None:
    cursor = postgres_connection.execute(
        """
        SELECT user_id
        FROM users
        WHERE email = %s
        """,
        (email,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return str(row["user_id"])
    return str(row[0])


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized:
        raise RebuildError("target email must not be empty")
    return normalized


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    dashscope_api_key = read_secret("DASHSCOPE_API_KEY")
    if not dashscope_api_key:
        print("DASHSCOPE_API_KEY is required; database was not modified", file=sys.stderr)
        return 2
    database_url = args.database_url or read_secret("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    pool = create_postgres_pool(database_url, min_size=1, max_size=1)
    try:
        with pool.connection() as connection:
            summary = rebuild_postgres_qa_embeddings(
                postgres_connection=connection,
                target_email=args.target_email,
                dashscope_api_key=dashscope_api_key,
                limit=args.limit,
                embedding_base_url=args.embedding_base_url,
                embedding_model=args.embedding_model,
                embedding_dimensions=args.embedding_dimensions,
            )
    except RebuildError as exc:
        print(f"Rebuild failed: {exc}", file=sys.stderr)
        return 2
    finally:
        close_postgres_pool(pool)

    print(
        "rebuilt: "
        f"total={summary['total']} indexed={summary['indexed']} failed={summary['failed']} user_id={summary['user_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
