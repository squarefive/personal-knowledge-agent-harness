from __future__ import annotations

import json
import logging
import os
import ssl
import time
from typing import Any, Callable, Iterator
from urllib import error, request

from .schemas import LLMResponse, ToolCall

logger = logging.getLogger(__name__)

RETRYABLE_HTTP_STATUSES = {429, 500, 503}
RETRYABLE_NETWORK_ERRORS = (error.URLError, TimeoutError, ssl.SSLError, ConnectionError)


class DeepSeekClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        timeout_seconds: int = 60,
        max_retries: int = 2,
        retry_backoff_seconds: tuple[float, ...] = (0.5, 1.0),
    ):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is required")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system_prompt: str,
        on_text_delta: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        request_messages = [{"role": "system", "content": system_prompt}, *messages]
        payload = {
            "model": self.model,
            "messages": request_messages,
            "tools": tools,
            "tool_choice": "auto",
            "stream": True,
        }
        text_parts: list[str] = []
        tool_accumulator = _ToolCallAccumulator()
        for data in self._post_stream("/chat/completions", payload):
            delta = ((data.get("choices") or [{}])[0].get("delta")) or {}
            content = delta.get("content")
            if content:
                text_parts.append(content)
                if on_text_delta is not None:
                    on_text_delta(content)
            tool_accumulator.add_delta(delta.get("tool_calls") or [])
        return LLMResponse(
            text="".join(text_parts) or None,
            tool_calls=tool_accumulator.to_tool_calls(),
        )

    def _post_stream(self, path: str, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            emitted = False
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as response:
                    for event_data in self._iter_sse_response(response):
                        emitted = True
                        yield event_data
                    return
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                logger.error("llm.deepseek.http_error", extra={"status": exc.code})
                if not emitted and exc.code in RETRYABLE_HTTP_STATUSES and attempt < self.max_retries:
                    self._sleep_before_retry(attempt)
                    continue
                raise RuntimeError(
                    f"DeepSeek request failed with status {exc.code} after {attempt + 1} attempts: {detail}"
                ) from exc
            except RETRYABLE_NETWORK_ERRORS as exc:
                logger.error("llm.deepseek.url_error")
                if not emitted and attempt < self.max_retries:
                    self._sleep_before_retry(attempt)
                    continue
                raise RuntimeError(
                    f"DeepSeek request failed after {attempt + 1} attempts: {self._error_reason(exc)}"
                ) from exc
        raise RuntimeError("DeepSeek request failed unexpectedly")

    @staticmethod
    def _iter_sse_response(response: Any) -> Iterator[dict[str, Any]]:
        while True:
            raw_line = response.readline()
            if not raw_line:
                return
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if data == "[DONE]":
                return
            try:
                yield json.loads(data)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Invalid DeepSeek streaming response") from exc

    def _sleep_before_retry(self, attempt: int) -> None:
        if not self.retry_backoff_seconds:
            return
        backoff_index = min(attempt, len(self.retry_backoff_seconds) - 1)
        time.sleep(self.retry_backoff_seconds[backoff_index])

    @staticmethod
    def _error_reason(exc: BaseException) -> str:
        if isinstance(exc, error.URLError):
            return str(exc.reason)
        return str(exc)

class _ToolCallAccumulator:
    def __init__(self) -> None:
        self._items: dict[int, dict[str, Any]] = {}

    def add_delta(self, deltas: list[dict[str, Any]]) -> None:
        for fallback_index, raw_call in enumerate(deltas):
            index = raw_call.get("index", fallback_index)
            item = self._items.setdefault(
                index,
                {"id": None, "name": "", "arguments": ""},
            )
            if raw_call.get("id"):
                item["id"] = raw_call["id"]
            function = raw_call.get("function") or {}
            if function.get("name"):
                item["name"] += function["name"]
            if function.get("arguments"):
                item["arguments"] += function["arguments"]

    def to_tool_calls(self) -> list[ToolCall]:
        tool_calls: list[ToolCall] = []
        for index in sorted(self._items):
            item = self._items[index]
            if not item["name"]:
                continue
            raw_arguments = item["arguments"] or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid tool call arguments for {item['name']}") from exc
            tool_calls.append(
                ToolCall(
                    id=item["id"] or f"tool_call_{index}",
                    name=item["name"],
                    arguments=arguments,
                )
            )
        return tool_calls
