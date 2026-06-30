from __future__ import annotations

from typing import Protocol

import httpx

from .constants import LLMClientConstants as llm_constants


class QwenEmbeddingClientError(RuntimeError):
    pass


class HttpClient(Protocol):
    def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> object: ...


class QwenEmbeddingClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        dimensions: int,
        http_client: HttpClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self._http_client = http_client
        self._owns_http_client = http_client is None

    def is_enabled(self) -> bool:
        return bool(self.api_key)

    def embed_text(self, text: str) -> list[float]:
        if not self.api_key:
            raise QwenEmbeddingClientError(f"{llm_constants.DASHSCOPE_API_KEY_ENV} is not configured")
        response = self._client().post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "input": text,
                "dimensions": self.dimensions,
            },
        )
        try:
            response.raise_for_status()
            payload = response.json()
            vector = payload["data"][0]["embedding"]
        except Exception as exc:
            raise QwenEmbeddingClientError(f"embedding request failed: {exc}") from exc
        if not isinstance(vector, list) or not all(isinstance(value, int | float) for value in vector):
            raise QwenEmbeddingClientError("embedding response did not contain a numeric vector")
        return [float(value) for value in vector]

    def close(self) -> None:
        if self._owns_http_client and self._http_client is not None:
            close = getattr(self._http_client, "close", None)
            if callable(close):
                close()

    def _client(self) -> HttpClient:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=llm_constants.DEFAULT_QWEN_HTTP_TIMEOUT_SECONDS)
        return self._http_client
