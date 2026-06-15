from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PermissionBehavior = Literal["allow", "deny", "ask"]

DANGEROUS_TOOLS = {"update_qa_card", "delete_qa_card"}


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
    if tool_name in DANGEROUS_TOOLS:
        return PermissionDecision(
            behavior="ask",
            reason="This operation changes local Q&A knowledge.",
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
