from __future__ import annotations

from typing import Any, Callable

from ..schemas import MemoryIndex
from ..agent_context.agent_profile_memory.agent_memory_turn_finalizer import TurnMemoryFinalizer
from .answer_source_evidence import finalize_answer


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
        turn_messages: list[dict[str, Any]],
        memory_index: MemoryIndex | None,
        recent_messages: list[dict[str, Any]],
    ) -> str:
        trusted_answer = finalize_answer(answer, turn_messages)
        self.append_message({"role": "assistant", "content": trusted_answer.answer})
        self.emit(
            run_id,
            "evidence_checked",
            status="completed",
            turn=turn,
            source_count=trusted_answer.source_count,
            removed_model_sources=trusted_answer.removed_model_sources,
            removed_unsupported_claim=trusted_answer.removed_unsupported_claim,
        )
        self._finalize_memory(
            run_id=run_id,
            user_input=user_input,
            final_answer=trusted_answer.answer,
            memory_index=memory_index,
            recent_messages=recent_messages,
        )
        self.emit(run_id, "final_answer_generated", answer=trusted_answer.answer, turn=turn)
        return trusted_answer.answer

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


AgentAnswerFinalizer = AnswerFinishStep
