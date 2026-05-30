from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib import error, request

from .schemas import LLMResponse, ToolCall

logger = logging.getLogger(__name__)


class DeepSeekClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        timeout_seconds: int = 60,
    ):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is required")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

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
        logger.info("llm.deepseek.request", extra={"model": self.model})
        data = self._post_json("/chat/completions", payload)
        response = self._parse_response(data)
        logger.info(
            "llm.deepseek.response",
            extra={"tool_calls_count": len(response.tool_calls)},
        )
        return response

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
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            logger.error("llm.deepseek.http_error", extra={"status": exc.code})
            raise RuntimeError(f"DeepSeek request failed with status {exc.code}: {detail}") from exc
        except error.URLError as exc:
            logger.error("llm.deepseek.url_error")
            raise RuntimeError(f"DeepSeek request failed: {exc.reason}") from exc

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
