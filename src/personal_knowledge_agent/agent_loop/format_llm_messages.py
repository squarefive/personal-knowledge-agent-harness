from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from ..schemas import LLMResponse


def format_assistant_tool_call_message(response: LLMResponse) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": response.text,
        "tool_calls": [],
    }
    for tool_call in response.tool_calls:
        message["tool_calls"].append(
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": json.dumps(tool_call.arguments, ensure_ascii=False),
                },
            }
        )
    return message


def format_tool_result_message(
    *,
    tool_call_id: str,
    result: dict[str, Any],
    compact_record: Any | None,
) -> dict[str, Any]:
    content = json.dumps(result, ensure_ascii=False)
    if compact_record is not None:
        content = json.dumps(
            {"ok": result.get("ok", True), "compact_record": asdict(compact_record)},
            ensure_ascii=False,
        )
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    }
