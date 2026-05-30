from __future__ import annotations

import json
import logging
from typing import Any

from .llm_client import DeepSeekClient
from .prompt_builder import build_system_prompt
from .schemas import LLMResponse
from .tool_dispatcher import ToolDispatcher
from .tools import KnowledgeTools

logger = logging.getLogger(__name__)


class AgentLoop:
    def __init__(
        self,
        *,
        llm: DeepSeekClient,
        tools: KnowledgeTools,
        dispatcher: ToolDispatcher,
        max_turns: int = 8,
    ):
        self.llm = llm
        self.tools = tools
        self.dispatcher = dispatcher
        self.max_turns = max_turns

    def run(self, user_input: str) -> str:
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_input}]
        system_prompt = build_system_prompt()
        tool_definitions = self.tools.definitions()
        logger.info("agent_loop.start")

        for turn in range(self.max_turns):
            response = self.llm.chat(
                messages=messages,
                tools=tool_definitions,
                system_prompt=system_prompt,
            )
            if not response.tool_calls:
                logger.info("agent_loop.final_answer", extra={"turn": turn})
                return response.text or ""

            logger.info(
                "tool_calls.detected",
                extra={"turn": turn, "count": len(response.tool_calls)},
            )
            messages.append(self._assistant_message(response))
            for tool_call in response.tool_calls:
                result = self.dispatcher.execute(tool_call)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
                logger.info(
                    "tool_result.appended",
                    extra={"turn": turn, "tool_name": tool_call.name},
                )

        logger.warning("agent_loop.max_turns_reached", extra={"max_turns": self.max_turns})
        return "工具调用次数过多，已停止本轮处理。"

    @staticmethod
    def _assistant_message(response: LLMResponse) -> dict[str, Any]:
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
