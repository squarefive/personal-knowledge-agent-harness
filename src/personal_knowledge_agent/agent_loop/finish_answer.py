from __future__ import annotations

from typing import Any, Callable

from ..schemas import MemoryIndex
from .finalize_turn_memory import TurnMemoryFinalizer


class AnswerFinishStep:
    def __init__(
        self,
        *,
        append_message: Callable[[dict[str, Any]], None],
        turn_memory_finalizer: TurnMemoryFinalizer,
        emit: Callable[..., None],
    ):
        self.append_message = append_message
        self.turn_memory_finalizer = turn_memory_finalizer
        self.emit = emit

    def finish(
        self,
        *,
        run_id: str,
        turn: int,
        user_input: str,
        answer: str,
        memory_index: MemoryIndex | None,
        recent_messages: list[dict[str, Any]],
    ) -> str:
        self.append_message({"role": "assistant", "content": answer})
        self.emit(run_id, "evidence_checked", status="completed", turn=turn)
        self._finalize_memory(
            run_id=run_id,
            user_input=user_input,
            final_answer=answer,
            memory_index=memory_index,
            recent_messages=recent_messages,
        )
        self.emit(run_id, "final_answer_generated", answer=answer, turn=turn)
        return answer

    def stop_for_too_many_tool_calls(
        self,
        *,
        run_id: str,
        user_input: str,
        memory_index: MemoryIndex | None,
        recent_messages: list[dict[str, Any]],
    ) -> str:
        answer = "工具调用次数过多，已停止本轮处理。"
        self.append_message({"role": "assistant", "content": answer})
        self.emit(run_id, "error", stage="agent_loop", message=answer)
        self._finalize_memory(
            run_id=run_id,
            user_input=user_input,
            final_answer=answer,
            memory_index=memory_index,
            recent_messages=recent_messages,
        )
        self.emit(run_id, "final_answer_generated", answer=answer)
        return answer

    def _finalize_memory(
        self,
        *,
        run_id: str,
        user_input: str,
        final_answer: str,
        memory_index: MemoryIndex | None,
        recent_messages: list[dict[str, Any]],
    ) -> None:
        self.turn_memory_finalizer.finalize(
            run_id=run_id,
            user_input=user_input,
            final_answer=final_answer,
            memory_index=memory_index,
            recent_messages=recent_messages,
            emit=self.emit,
        )
