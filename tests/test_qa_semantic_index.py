from pathlib import Path

from personal_knowledge_agent.qa_data_access import QACardSemanticIndex
from personal_knowledge_agent.qa_data_access import QACard


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHttpClient:
    def __init__(self):
        self.requests = []

    def post(self, url, *, headers, json):
        self.requests.append({"url": url, "headers": headers, "json": json})
        return FakeResponse({"data": [{"embedding": [0.1, 0.2, 0.3]}]})


class FakePoint:
    def __init__(self, payload, score):
        self.payload = payload
        self.score = score


class FakeQdrantClient:
    def __init__(self):
        self.collection_created = False
        self.upserted_points = []
        self.deleted_selectors = []

    def collection_exists(self, collection_name):
        return self.collection_created

    def create_collection(self, *, collection_name, vectors_config):
        self.collection_created = True
        self.collection_name = collection_name
        self.vectors_config = vectors_config

    def upsert(self, *, collection_name, points):
        self.upserted_points.extend(points)

    def delete(self, *, collection_name, points_selector):
        self.deleted_selectors.append(points_selector)

    def search(self, *, collection_name, query_vector, limit):
        return [FakePoint({"card_id": "qa_1"}, 0.91)]


def test_semantic_index_uses_qwen_embedding_request_and_card_id_payload():
    http_client = FakeHttpClient()
    qdrant_client = FakeQdrantClient()
    index = QACardSemanticIndex(
        dashscope_api_key="dashscope-key",
        embedding_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        embedding_model="text-embedding-v4",
        embedding_dimensions=1024,
        qdrant_path=Path(".knowledge/qdrant"),
        collection_name="qa_cards",
        http_client=http_client,
        qdrant_client=qdrant_client,
    )
    card = QACard(
        id="qa_1",
        question="问题？",
        answer="完整答案不应进入 Qdrant payload。",
        summary="摘要。",
        keywords=["关键词"],
        category="检索与知识库",
        source_type="manual_qa",
        created_at="2026-06-08T00:00:00+00:00",
        updated_at="2026-06-08T00:00:00+00:00",
    )

    index.upsert_card(card)

    request = http_client.requests[0]
    assert request["url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
    assert request["headers"]["Authorization"] == "Bearer dashscope-key"
    assert request["json"]["model"] == "text-embedding-v4"
    assert request["json"]["dimensions"] == 1024
    assert "问题？" in request["json"]["input"]
    assert "完整答案" not in request["json"]["input"]
    assert qdrant_client.upserted_points[0].payload == {"card_id": "qa_1"}


def test_semantic_index_search_returns_card_ids():
    index = QACardSemanticIndex(
        dashscope_api_key="dashscope-key",
        embedding_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        embedding_model="text-embedding-v4",
        embedding_dimensions=1024,
        qdrant_path=Path(".knowledge/qdrant"),
        collection_name="qa_cards",
        http_client=FakeHttpClient(),
        qdrant_client=FakeQdrantClient(),
    )

    hits = index.search("来源校验", limit=5)

    assert hits[0].card_id == "qa_1"
    assert hits[0].score == 0.91
