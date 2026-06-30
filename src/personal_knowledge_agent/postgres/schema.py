from __future__ import annotations

from typing import Protocol

from .constants import PostgresConstants as postgres_constants


class SchemaConnection(Protocol):
    def execute(self, query: str) -> object: ...

def initialize_postgres_schema(connection: SchemaConnection) -> None:
    for statement in postgres_constants.POSTGRES_SCHEMA_STATEMENTS:
        connection.execute(statement)

    commit = getattr(connection, "commit", None)
    if callable(commit):
        commit()
