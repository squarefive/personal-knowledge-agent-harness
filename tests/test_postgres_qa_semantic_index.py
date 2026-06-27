from __future__ import annotations

from personal_knowledge_agent.postgres.qa_semantic_index import PostgresQASemanticIndex
from personal_knowledge_agent.qa_data_access import QACard, SemanticSearchHit


class FakeRepository:
    def __init__(self) -> None:
        self.searches = []
        self.embedding_updates = []

    def search_vector_cards(self, embedding, *, limit=5):
        self.searches.append((embedding, limit))
        return [SemanticSearchHit(card_id="qa_1", score=0.88)]

    def update_embedding_status(self, card_id, *, status, embedding=None, embedding_model=None):
        self.embedding_updates.append((card_id, status, embedding, embedding_model))
        return True


class FakeEmbeddingClient:
    model = "text-embedding-v4"

    def __init__(self) -> None:
        self.texts = []

    def is_enabled(self):
        return True

    def embed_text(self, text):
        self.texts.append(text)
        return [0.1, 0.2, 0.3]


def test_postgres_semantic_index_upsert_generates_embedding_and_writes_postgres() -> None:
    repository = FakeRepository()
    embedding_client = FakeEmbeddingClient()
    index = PostgresQASemanticIndex(repository, embedding_client)
    card = QACard(
        id="qa_1",
        question="问题",
        answer="答案",
        summary="摘要",
        keywords=["pgvector", "PostgreSQL"],
        category="Agent边界",
        source_type="manual_qa",
        created_at="",
        updated_at="",
    )

    index.upsert_card(card)

    assert embedding_client.texts == ["问题\n摘要\npgvector PostgreSQL"]
    assert repository.embedding_updates == [
        ("qa_1", "ready", [0.1, 0.2, 0.3], "text-embedding-v4")
    ]


def test_postgres_semantic_index_search_uses_postgres_vector_query() -> None:
    repository = FakeRepository()
    embedding_client = FakeEmbeddingClient()
    index = PostgresQASemanticIndex(repository, embedding_client)

    hits = index.search("怎么检索？", limit=4)

    assert hits == [SemanticSearchHit(card_id="qa_1", score=0.88)]
    assert embedding_client.texts == ["怎么检索？"]
    assert repository.searches == [([0.1, 0.2, 0.3], 4)]
