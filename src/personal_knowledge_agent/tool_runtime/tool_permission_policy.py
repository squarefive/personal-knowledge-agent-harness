from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PermissionBehavior = Literal["allow", "deny", "ask"]

TOOLS_REQUIRING_APPROVAL = {
    "update_qa_card": "This operation changes Q&A knowledge.",
    "delete_qa_card": "This operation deletes Q&A knowledge.",
    "merge_qa_cards": "This operation merges Q&A knowledge.",
    "update_todo": "This operation changes a todo item.",
}


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
    reason = TOOLS_REQUIRING_APPROVAL.get(tool_name)
    if reason is not None:
        return PermissionDecision(
            behavior="ask",
            reason=reason,
        )
    return PermissionDecision(behavior="allow")


def default_approval_callback(request: ApprovalRequest) -> bool:
    return False


def permission_denied_result(reason: str) -> dict[str, Any]:
    message = reason.strip() if reason.strip() else "Permission denied."
    return {
        "ok": False,
        "error_code": "permission_denied",
        "message": message,
    }
