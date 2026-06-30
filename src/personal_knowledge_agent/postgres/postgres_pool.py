from __future__ import annotations

from psycopg_pool import ConnectionPool

from .constants import PostgresConstants as postgres_constants


def create_postgres_pool(
    database_url: str,
    *,
    min_size: int = postgres_constants.DEFAULT_POOL_MIN_SIZE,
    max_size: int = postgres_constants.DEFAULT_POOL_MAX_SIZE,
    open: bool = True,
) -> ConnectionPool:
    if not database_url or not database_url.strip():
        raise ValueError("database_url must not be empty")
    return ConnectionPool(
        conninfo=database_url,
        min_size=min_size,
        max_size=max_size,
        open=open,
    )


def close_postgres_pool(pool: ConnectionPool) -> None:
    pool.close()
