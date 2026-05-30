from __future__ import annotations

import json
import time
from typing import Any, Callable

from .events import AgentEvent, new_run_id
from .llm_client import DeepSeekClient
from .prompt_builder import build_system_prompt
from .schemas import LLMResponse
from .tool_dispatcher import ToolDispatcher
from .tools import KnowledgeTools

EventSink = Callable[[AgentEvent], None]


class AgentLoop:
    def __init__(
        self,
        *,
        llm: DeepSeekClient,
        tools: KnowledgeTools,
        dispatcher: ToolDispatcher,
        max_turns: int = 8,
        event_sink: EventSink | None = None,
    ):
        self.llm = llm
        self.tools = tools
        self.dispatcher = dispatcher
        self.max_turns = max_turns
        self.event_sink = event_sink

    def run(self, user_input: str) -> str:
        run_id = new_run_id()
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_input}]
        system_prompt = build_system_prompt()
        tool_definitions = self.tools.definitions()
        self._emit(run_id, "user_input_received", user_input=user_input)

        for turn in range(self.max_turns):
            self._emit(run_id, "llm_call_started", stage="next_action", turn=turn)
            try:
                response = self.llm.chat(
                    messages=messages,
                    tools=tool_definitions,
                    system_prompt=system_prompt,
                )
            except Exception as exc:
                self._emit(
                    run_id,
                    "llm_call_finished",
                    stage="next_action",
                    turn=turn,
                    status="error",
                    error_message=str(exc),
                )
                self._emit(run_id, "error", stage="llm_call", message=str(exc))
                raise
            self._emit(
                run_id,
                "llm_call_finished",
                stage="next_action",
                turn=turn,
                status="success",
                tool_calls_count=len(response.tool_calls),
            )
            if not response.tool_calls:
                answer = response.text or ""
                self._emit(run_id, "evidence_checked", status="completed", turn=turn)
                self._emit(run_id, "final_answer_generated", answer=answer, turn=turn)
                return answer

            messages.append(self._assistant_message(response))
            for tool_call in response.tool_calls:
                display_input = self.dispatcher.display_input(tool_call.name, tool_call.arguments)
                self._emit(
                    run_id,
                    "tool_call_started",
                    turn=turn,
                    tool_name=tool_call.name,
                    tool_call_id=tool_call.id,
                    input=display_input,
                )
                started_at = time.monotonic()
                result = self.dispatcher.execute(tool_call)
                duration_ms = int((time.monotonic() - started_at) * 1000)
                display_output = self.dispatcher.display_output(tool_call.name, result)
                self._emit(
                    run_id,
                    "tool_call_finished",
                    turn=turn,
                    tool_name=tool_call.name,
                    tool_call_id=tool_call.id,
                    status="success" if result.get("ok") is not False else "error",
                    duration_ms=duration_ms,
                    output=display_output,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        answer = "工具调用次数过多，已停止本轮处理。"
        self._emit(run_id, "error", stage="agent_loop", message=answer)
        self._emit(run_id, "final_answer_generated", answer=answer)
        return answer

    def _emit(self, run_id: str, event_type: str, **payload: Any) -> None:
        if self.event_sink is None:
            return
        self.event_sink(AgentEvent(run_id=run_id, event_type=event_type, payload=payload))

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
