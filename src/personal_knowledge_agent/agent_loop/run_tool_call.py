from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

from ..schemas import CompactRecord, ToolCall
from ..session_memory.compact_tool_result import ContextCompactor
from ..tools.dispatch_tool_call import ToolDispatcher


@dataclass
class ToolCallResult:
    result: dict[str, Any]
    compact_record: CompactRecord | None


class ToolCallStep:
    def __init__(
        self,
        *,
        dispatcher: ToolDispatcher,
        context_compactor: ContextCompactor | None = None,
        emit: Callable[..., None],
    ):
        self.dispatcher = dispatcher
        self.context_compactor = context_compactor
        self.emit = emit

    def run(self, *, run_id: str, turn: int, tool_call: ToolCall) -> ToolCallResult:
        display_input = self.dispatcher.display_input(tool_call.name, tool_call.arguments)
        self.emit(
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
        compact_record = self._compact_tool_result(
            run_id=run_id,
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            result=result,
        )
        display_output = self.dispatcher.display_output(tool_call.name, result)
        self.emit(
            run_id,
            "tool_call_finished",
            turn=turn,
            tool_name=tool_call.name,
            tool_call_id=tool_call.id,
            status="success" if result.get("ok") is not False else "error",
            duration_ms=duration_ms,
            output=display_output,
        )
        if compact_record is not None:
            self.emit(
                run_id,
                "context_compacted",
                turn=turn,
                tool_name=tool_call.name,
                tool_call_id=tool_call.id,
                compact_record=asdict(compact_record),
            )
        return ToolCallResult(result=result, compact_record=compact_record)

    def _compact_tool_result(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        result: dict[str, Any],
    ) -> CompactRecord | None:
        if self.context_compactor is None:
            return None
        return self.context_compactor.compact_tool_result(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            result_text=json.dumps(result, ensure_ascii=False),
        )
