from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..qa_data_access import QACard, SemanticSearchHit

from .qa_repository import PostgresQACardRepository


class EmbeddingClient(Protocol):
    model: str

    def is_enabled(self) -> bool: ...

    def embed_text(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class PostgresQASemanticIndex:
    repository: PostgresQACardRepository
    embedding_client: EmbeddingClient

    def is_enabled(self) -> bool:
        return self.embedding_client.is_enabled()

    def search(self, query: str, limit: int) -> list[SemanticSearchHit]:
        vector = self.embedding_client.embed_text(query)
        return self.repository.search_vector_cards(vector, limit=limit)

    def upsert_card(self, card: QACard) -> None:
        vector = self.embedding_client.embed_text(_index_text(card))
        updated = self.repository.update_embedding_status(
            card.id,
            status="ready",
            embedding=vector,
            embedding_model=self.embedding_client.model,
        )
        if not updated:
            raise RuntimeError(f"card not found or not owned: {card.id}")

    def delete_card(self, card_id: str) -> None:
        self.repository.update_embedding_status(card_id, status="pending")

    def close(self) -> None:
        close = getattr(self.embedding_client, "close", None)
        if callable(close):
            close()


def _index_text(card: QACard) -> str:
    return "\n".join(
        [
            card.question,
            card.summary,
            " ".join(card.keywords),
        ]
    )
