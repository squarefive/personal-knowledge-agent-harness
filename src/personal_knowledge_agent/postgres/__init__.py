"""PostgreSQL infrastructure helpers."""

from .auth_repository import PostgresAuthRepository
from .memory_repository import PostgresAgentMemoryRepository
from .postgres_pool import close_postgres_pool, create_postgres_pool
from .qa_repository import PostgresQACardRepository
from .qa_semantic_index import PostgresQASemanticIndex
from .constants import PostgresConstants as postgres_constants
from .schema import initialize_postgres_schema
from .session_repository import ConversationSessionRecord, PostgresConversationSessionRepository
from .session_runtime_adapters import (
    InMemoryToolResultCompactor,
    PostgresConversationTranscriptAdapter,
    PostgresRuntimeContextCompactor,
    PostgresSessionMetadataAdapter,
)
from .todo_repository import PostgresTodoRepository

__all__ = [
    "ConversationSessionRecord",
    "InMemoryToolResultCompactor",
    "POSTGRES_SCHEMA_STATEMENTS",
    "PostgresAuthRepository",
    "PostgresAgentMemoryRepository",
    "PostgresConversationSessionRepository",
    "PostgresConversationTranscriptAdapter",
    "PostgresQACardRepository",
    "PostgresQASemanticIndex",
    "PostgresRuntimeContextCompactor",
    "PostgresSessionMetadataAdapter",
    "PostgresTodoRepository",
    "close_postgres_pool",
    "create_postgres_pool",
    "initialize_postgres_schema",
]


def __getattr__(name: str) -> object:
    if name == "POSTGRES_SCHEMA_STATEMENTS":
        return postgres_constants.POSTGRES_SCHEMA_STATEMENTS
    raise AttributeError(name)
