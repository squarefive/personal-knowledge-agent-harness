#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from personal_knowledge_agent.postgres import close_postgres_pool, create_postgres_pool, initialize_postgres_schema
from personal_knowledge_agent.security.secrets import read_secret


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize the PostgreSQL schema.")
    parser.add_argument("--database-url", help="PostgreSQL database URL. Defaults to DATABASE_URL/_FILE.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    database_url = args.database_url or read_secret("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    pool = create_postgres_pool(database_url, min_size=1, max_size=1)
    try:
        with pool.connection() as connection:
            initialize_postgres_schema(connection)
    finally:
        close_postgres_pool(pool)

    print("PostgreSQL schema initialized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
