from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from ..llm_clients import LLMResponse
from .constants import AgentRuntimeConstants as runtime_constants


def format_assistant_tool_call_message(response: LLMResponse) -> dict[str, Any]:
    message: dict[str, Any] = {
        runtime_constants.MESSAGE_ROLE_FIELD: runtime_constants.MESSAGE_ROLE_ASSISTANT,
        runtime_constants.MESSAGE_CONTENT_FIELD: response.text,
        runtime_constants.MESSAGE_TOOL_CALLS_FIELD: [],
    }
    for tool_call in response.tool_calls:
        message[runtime_constants.MESSAGE_TOOL_CALLS_FIELD].append(
            {
                runtime_constants.TOOL_CALL_ID_PAYLOAD_FIELD: tool_call.id,
                runtime_constants.TOOL_CALL_TYPE_FIELD: runtime_constants.TOOL_CALL_TYPE_FUNCTION,
                runtime_constants.TOOL_CALL_FUNCTION_FIELD: {
                    runtime_constants.TOOL_CALL_NAME_FIELD: tool_call.name,
                    runtime_constants.TOOL_CALL_ARGUMENTS_FIELD: json.dumps(
                        tool_call.arguments,
                        ensure_ascii=False,
                    ),
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
            {
                runtime_constants.RESULT_OK_FIELD: result.get(runtime_constants.RESULT_OK_FIELD, True),
                runtime_constants.RESULT_COMPACT_RECORD_FIELD: asdict(compact_record),
            },
            ensure_ascii=False,
        )
    return {
        runtime_constants.MESSAGE_ROLE_FIELD: runtime_constants.MESSAGE_ROLE_TOOL,
        runtime_constants.TOOL_CALL_ID_FIELD: tool_call_id,
        runtime_constants.MESSAGE_CONTENT_FIELD: content,
    }
