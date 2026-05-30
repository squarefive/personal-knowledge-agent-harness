from __future__ import annotations

import logging
import time
from typing import Any, Callable

from .schemas import ToolCall
from .tools import KnowledgeTools

logger = logging.getLogger(__name__)


class ToolDispatcher:
    def __init__(self, tools: KnowledgeTools):
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "save_qa_card": tools.save_qa_card,
            "search_qa_cards": tools.search_qa_cards,
            "read_qa_card": tools.read_qa_card,
            "list_recent_cards": tools.list_recent_cards,
        }

    def execute(self, tool_call: ToolCall) -> dict[str, Any]:
        started_at = time.monotonic()
        logger.info(
            "tool.dispatch.start",
            extra={"tool_name": tool_call.name, "tool_call_id": tool_call.id},
        )
        handler = self._handlers.get(tool_call.name)
        if handler is None:
            logger.warning(
                "tool.unknown",
                extra={"tool_name": tool_call.name, "tool_call_id": tool_call.id},
            )
            return {"ok": False, "error_code": "unknown_tool", "message": tool_call.name}
        try:
            result = handler(tool_call.arguments)
            logger.info(
                "tool.dispatch.success",
                extra={
                    "tool_name": tool_call.name,
                    "tool_call_id": tool_call.id,
                    "elapsed_ms": int((time.monotonic() - started_at) * 1000),
                },
            )
            return result
        except Exception as exc:
            logger.exception(
                "tool.dispatch.error",
                extra={"tool_name": tool_call.name, "tool_call_id": tool_call.id},
            )
            return {"ok": False, "error_code": "tool_error", "message": str(exc)}
