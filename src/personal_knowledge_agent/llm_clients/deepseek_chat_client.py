from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Callable, Iterator
from urllib import error, request

from ..tool_runtime.tool_models import ToolCall
from .constants import LLMClientConstants as llm_constants
from .llm_models import LLMResponse, LLMUsage

logger = logging.getLogger(__name__)

class LLMContextLengthExceeded(RuntimeError):
    pass


class DeepSeekChatClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = llm_constants.DEFAULT_DEEPSEEK_MODEL,
        base_url: str = llm_constants.DEFAULT_DEEPSEEK_BASE_URL,
        timeout_seconds: int = llm_constants.DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = llm_constants.DEFAULT_MAX_RETRIES,
        retry_backoff_seconds: tuple[float, ...] = llm_constants.DEFAULT_RETRY_BACKOFF_SECONDS,
        llm_provider_user_id: str | None = None,
    ):
        self.api_key = api_key or os.environ.get(llm_constants.DEEPSEEK_API_KEY_ENV)
        if not self.api_key:
            raise ValueError(f"{llm_constants.DEEPSEEK_API_KEY_ENV} is required")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        normalized_provider_user_id = llm_provider_user_id.strip() if llm_provider_user_id else None
        self.llm_provider_user_id = normalized_provider_user_id or None

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system_prompt: str,
        on_text_delta: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        request_messages = [
            {
                llm_constants.MESSAGE_ROLE_FIELD: llm_constants.MESSAGE_ROLE_SYSTEM,
                llm_constants.MESSAGE_CONTENT_FIELD: system_prompt,
            },
            *messages,
        ]
        payload = {
            llm_constants.PAYLOAD_MODEL_FIELD: self.model,
            llm_constants.PAYLOAD_MESSAGES_FIELD: request_messages,
            llm_constants.PAYLOAD_TOOLS_FIELD: tools,
            llm_constants.PAYLOAD_TOOL_CHOICE_FIELD: llm_constants.TOOL_CHOICE_AUTO,
            llm_constants.PAYLOAD_STREAM_FIELD: True,
            llm_constants.PAYLOAD_STREAM_OPTIONS_FIELD: {
                llm_constants.PAYLOAD_INCLUDE_USAGE_FIELD: True,
            },
        }
        if self.llm_provider_user_id:
            payload[llm_constants.PAYLOAD_USER_ID_FIELD] = self.llm_provider_user_id
        text_parts: list[str] = []
        tool_accumulator = _ToolCallAccumulator()
        usage: LLMUsage | None = None
        for data in self._post_stream("/chat/completions", payload):
            if data.get(llm_constants.RESPONSE_USAGE_FIELD) is not None:
                usage = _parse_usage(data.get(llm_constants.RESPONSE_USAGE_FIELD))
            delta = (
                (data.get(llm_constants.RESPONSE_CHOICES_FIELD) or [{}])[0].get(
                    llm_constants.RESPONSE_DELTA_FIELD
                )
            ) or {}
            tool_call_deltas = delta.get(llm_constants.RESPONSE_TOOL_CALLS_FIELD) or []
            content = delta.get(llm_constants.MESSAGE_CONTENT_FIELD)
            if content and not tool_call_deltas:
                text_parts.append(content)
                if on_text_delta is not None:
                    on_text_delta(content)
            tool_accumulator.add_delta(tool_call_deltas)
        return LLMResponse(
            text="".join(text_parts) or None,
            tool_calls=tool_accumulator.to_tool_calls(),
            usage=usage,
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
                if _is_context_limit_error(detail):
                    raise LLMContextLengthExceeded(
                        f"DeepSeek context length exceeded with status {exc.code}: {detail}"
                    ) from exc
                if not emitted and exc.code in llm_constants.RETRYABLE_HTTP_STATUSES and attempt < self.max_retries:
                    self._sleep_before_retry(attempt)
                    continue
                raise RuntimeError(
                    f"DeepSeek request failed with status {exc.code} after {attempt + 1} attempts: {detail}"
                ) from exc
            except llm_constants.RETRYABLE_NETWORK_ERRORS as exc:
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


def _parse_usage(payload: Any) -> LLMUsage | None:
    if not isinstance(payload, dict):
        return None
    return LLMUsage(
        prompt_tokens=_optional_int(payload.get(llm_constants.RESPONSE_PROMPT_TOKENS_FIELD)),
        completion_tokens=_optional_int(payload.get(llm_constants.RESPONSE_COMPLETION_TOKENS_FIELD)),
        total_tokens=_optional_int(payload.get(llm_constants.RESPONSE_TOTAL_TOKENS_FIELD)),
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _is_context_limit_error(detail: str) -> bool:
    lowered = detail.lower()
    return any(marker in lowered for marker in llm_constants.CONTEXT_LIMIT_ERROR_MARKERS)


class _ToolCallAccumulator:
    def __init__(self) -> None:
        self._items: dict[int, dict[str, Any]] = {}

    def add_delta(self, deltas: list[dict[str, Any]]) -> None:
        for fallback_index, raw_call in enumerate(deltas):
            index = raw_call.get(llm_constants.RESPONSE_TOOL_CALL_INDEX_FIELD, fallback_index)
            item = self._items.setdefault(
                index,
                {
                    llm_constants.RESPONSE_TOOL_CALL_ID_FIELD: None,
                    llm_constants.RESPONSE_TOOL_CALL_NAME_FIELD: "",
                    llm_constants.RESPONSE_TOOL_CALL_ARGUMENTS_FIELD: "",
                },
            )
            if raw_call.get(llm_constants.RESPONSE_TOOL_CALL_ID_FIELD):
                item[llm_constants.RESPONSE_TOOL_CALL_ID_FIELD] = raw_call[
                    llm_constants.RESPONSE_TOOL_CALL_ID_FIELD
                ]
            function = raw_call.get(llm_constants.RESPONSE_TOOL_CALL_FUNCTION_FIELD) or {}
            if function.get(llm_constants.RESPONSE_TOOL_CALL_NAME_FIELD):
                item[llm_constants.RESPONSE_TOOL_CALL_NAME_FIELD] += function[
                    llm_constants.RESPONSE_TOOL_CALL_NAME_FIELD
                ]
            if function.get(llm_constants.RESPONSE_TOOL_CALL_ARGUMENTS_FIELD):
                item[llm_constants.RESPONSE_TOOL_CALL_ARGUMENTS_FIELD] += function[
                    llm_constants.RESPONSE_TOOL_CALL_ARGUMENTS_FIELD
                ]

    def to_tool_calls(self) -> list[ToolCall]:
        tool_calls: list[ToolCall] = []
        for index in sorted(self._items):
            item = self._items[index]
            if not item[llm_constants.RESPONSE_TOOL_CALL_NAME_FIELD]:
                continue
            raw_arguments = item[llm_constants.RESPONSE_TOOL_CALL_ARGUMENTS_FIELD] or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid tool call arguments for {item[llm_constants.RESPONSE_TOOL_CALL_NAME_FIELD]}"
                ) from exc
            tool_calls.append(
                ToolCall(
                    id=item[llm_constants.RESPONSE_TOOL_CALL_ID_FIELD] or f"tool_call_{index}",
                    name=item[llm_constants.RESPONSE_TOOL_CALL_NAME_FIELD],
                    arguments=arguments,
                )
            )
        return tool_calls
