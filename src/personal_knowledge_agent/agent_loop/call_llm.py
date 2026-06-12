from __future__ import annotations

from typing import Any, Callable

from ..llm_client import DeepSeekClient
from ..schemas import LLMResponse


class LLMCallStep:
    def __init__(self, llm: DeepSeekClient, emit: Callable[..., None]):
        self.llm = llm
        self.emit = emit

    def run(
        self,
        *,
        run_id: str,
        turn: int,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system_prompt: str,
    ) -> LLMResponse:
        self.emit(run_id, "llm_call_started", stage="next_action", turn=turn)
        try:
            response = self.llm.chat(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                on_text_delta=lambda text: self.emit(run_id, "answer_delta", turn=turn, text=text),
            )
        except Exception as exc:
            self.emit(
                run_id,
                "llm_call_finished",
                stage="next_action",
                turn=turn,
                status="error",
                error_message=str(exc),
            )
            self.emit(run_id, "error", stage="llm_call", message=str(exc))
            raise
        self.emit(
            run_id,
            "llm_call_finished",
            stage="next_action",
            turn=turn,
            status="success",
            tool_calls_count=len(response.tool_calls),
        )
        return response
