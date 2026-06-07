from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointIdsList, PointStruct, VectorParams

from .schemas import QACard


class QASemanticIndexError(RuntimeError):
    pass


@dataclass(frozen=True)
class SemanticSearchHit:
    card_id: str
    score: float


class QASemanticIndex:
    def __init__(
        self,
        *,
        dashscope_api_key: str | None,
        embedding_base_url: str,
        embedding_model: str,
        embedding_dimensions: int,
        qdrant_path: Path,
        collection_name: str,
        http_client: httpx.Client | None = None,
        qdrant_client: QdrantClient | None = None,
    ):
        self.dashscope_api_key = dashscope_api_key
        self.embedding_base_url = embedding_base_url.rstrip("/")
        self.embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions
        self.collection_name = collection_name
        self._http_client = http_client or httpx.Client(timeout=30.0)
        self._owns_http_client = http_client is None
        self._qdrant_client = qdrant_client
        self._qdrant_path = Path(qdrant_path)

    def is_enabled(self) -> bool:
        return bool(self.dashscope_api_key)

    def upsert_card(self, card: QACard) -> None:
        vector = self.embed_text(self._index_text(card))
        self._ensure_collection()
        self._client().upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=self._point_id(card.id),
                    vector=vector,
                    payload={"card_id": card.id},
                )
            ],
        )

    def delete_card(self, card_id: str) -> None:
        self._ensure_collection()
        self._client().delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=[self._point_id(card_id)]),
        )

    def search(self, query: str, limit: int) -> list[SemanticSearchHit]:
        vector = self.embed_text(query)
        self._ensure_collection()
        response = self._search_points(vector, limit)
        hits: list[SemanticSearchHit] = []
        for point in response:
            payload = getattr(point, "payload", None) or {}
            card_id = payload.get("card_id")
            if isinstance(card_id, str) and card_id:
                hits.append(SemanticSearchHit(card_id=card_id, score=float(point.score)))
        return hits

    def embed_text(self, text: str) -> list[float]:
        if not self.dashscope_api_key:
            raise QASemanticIndexError("DASHSCOPE_API_KEY is not configured")
        response = self._http_client.post(
            f"{self.embedding_base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.dashscope_api_key}"},
            json={
                "model": self.embedding_model,
                "input": text,
                "dimensions": self.embedding_dimensions,
            },
        )
        try:
            response.raise_for_status()
            payload = response.json()
            vector = payload["data"][0]["embedding"]
        except Exception as exc:
            raise QASemanticIndexError(f"embedding request failed: {exc}") from exc
        if not isinstance(vector, list) or not all(isinstance(value, int | float) for value in vector):
            raise QASemanticIndexError("embedding response did not contain a numeric vector")
        return [float(value) for value in vector]

    def close(self) -> None:
        if self._owns_http_client:
            self._http_client.close()

    def _client(self) -> QdrantClient:
        if self._qdrant_client is None:
            self._qdrant_path.parent.mkdir(parents=True, exist_ok=True)
            self._qdrant_client = QdrantClient(path=str(self._qdrant_path))
        return self._qdrant_client

    def _ensure_collection(self) -> None:
        client = self._client()
        if client.collection_exists(self.collection_name):
            return
        client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.embedding_dimensions, distance=Distance.COSINE),
        )

    def _search_points(self, vector: list[float], limit: int) -> list[Any]:
        client = self._client()
        if hasattr(client, "search"):
            return client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                limit=limit,
            )
        result = client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=limit,
        )
        return list(result.points)

    @staticmethod
    def _index_text(card: QACard) -> str:
        return "\n".join(
            [
                card.question,
                card.summary,
                " ".join(card.keywords),
            ]
        )

    @staticmethod
    def _point_id(card_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"qa-card:{card_id}"))
