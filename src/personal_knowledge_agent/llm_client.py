from __future__ import annotations

import json
import logging
import os
import ssl
import time
from typing import Any
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
    ) -> LLMResponse:
        request_messages = [{"role": "system", "content": system_prompt}, *messages]
        payload = {
            "model": self.model,
            "messages": request_messages,
            "tools": tools,
            "tool_choice": "auto",
        }
        data = self._post_json("/chat/completions", payload)
        return self._parse_response(data)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
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
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                logger.error("llm.deepseek.http_error", extra={"status": exc.code})
                if exc.code in RETRYABLE_HTTP_STATUSES and attempt < self.max_retries:
                    self._sleep_before_retry(attempt)
                    continue
                raise RuntimeError(
                    f"DeepSeek request failed with status {exc.code} after {attempt + 1} attempts: {detail}"
                ) from exc
            except RETRYABLE_NETWORK_ERRORS as exc:
                logger.error("llm.deepseek.url_error")
                if attempt < self.max_retries:
                    self._sleep_before_retry(attempt)
                    continue
                raise RuntimeError(
                    f"DeepSeek request failed after {attempt + 1} attempts: {self._error_reason(exc)}"
                ) from exc
        raise RuntimeError("DeepSeek request failed unexpectedly")

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

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> LLMResponse:
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("DeepSeek response did not include choices")
        message = choices[0].get("message") or {}
        tool_calls: list[ToolCall] = []
        for index, raw_call in enumerate(message.get("tool_calls") or []):
            function = raw_call.get("function") or {}
            raw_arguments = function.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid tool call arguments for {function.get('name')}") from exc
            tool_calls.append(
                ToolCall(
                    id=raw_call.get("id") or f"tool_call_{index}",
                    name=function.get("name") or "",
                    arguments=arguments,
                )
            )
        return LLMResponse(text=message.get("content"), tool_calls=tool_calls)
