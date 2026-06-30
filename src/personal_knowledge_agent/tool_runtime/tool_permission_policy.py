from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .constants import ToolRuntimeConstants as tool_runtime_constants

PermissionBehavior = Literal["allow", "deny", "ask"]

@dataclass(frozen=True)
class PermissionDecision:
    behavior: PermissionBehavior
    reason: str = ""


@dataclass(frozen=True)
class ApprovalRequest:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


def check_permission(tool_name: str, arguments: dict[str, Any]) -> PermissionDecision:
    reason = tool_runtime_constants.TOOLS_REQUIRING_APPROVAL.get(tool_name)
    if reason is not None:
        return PermissionDecision(
            behavior=tool_runtime_constants.PERMISSION_BEHAVIOR_ASK,
            reason=reason,
        )
    return PermissionDecision(behavior=tool_runtime_constants.PERMISSION_BEHAVIOR_ALLOW)


def default_approval_callback(request: ApprovalRequest) -> bool:
    return False


def permission_denied_result(reason: str) -> dict[str, Any]:
    message = reason.strip() if reason.strip() else "Permission denied."
    return {
        tool_runtime_constants.RESULT_OK_FIELD: False,
        tool_runtime_constants.RESULT_ERROR_CODE_FIELD: tool_runtime_constants.ERROR_CODE_PERMISSION_DENIED,
        tool_runtime_constants.RESULT_MESSAGE_FIELD: message,
    }
