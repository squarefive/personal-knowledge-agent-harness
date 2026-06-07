from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

from ..permissions import (
    ApprovalRequest,
    PermissionDecision,
    check_permission,
    default_approval_callback,
    permission_denied_result,
)
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
        permission_checker: Callable[[str, dict[str, Any]], PermissionDecision] = check_permission,
        approval_callback: Callable[[ApprovalRequest], bool] = default_approval_callback,
        emit: Callable[..., None],
    ):
        self.dispatcher = dispatcher
        self.context_compactor = context_compactor
        self.permission_checker = permission_checker
        self.approval_callback = approval_callback
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
        decision = self.permission_checker(tool_call.name, tool_call.arguments)
        approved = False
        if decision.behavior == "allow":
            result = self.dispatcher.execute(tool_call)
        elif decision.behavior == "ask":
            request = ApprovalRequest(
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
                reason=decision.reason,
            )
            try:
                approved = self.approval_callback(request)
            except Exception as exc:
                result = permission_denied_result(f"Permission approval failed: {exc}")
            else:
                if approved:
                    result = self.dispatcher.execute(tool_call)
                else:
                    result = permission_denied_result("Permission denied by user.")
        else:
            result = permission_denied_result(decision.reason)
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
            permission_behavior=decision.behavior,
            permission_reason=decision.reason,
            permission_approved=approved,
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
