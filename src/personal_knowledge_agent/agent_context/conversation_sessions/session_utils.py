from __future__ import annotations

from datetime import UTC, datetime

from .constants import ConversationSessionConstants as session_constants


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def validate_session_id(session_id: str) -> str:
    if not session_constants.SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError("session_id must contain only letters, numbers, underscores, and hyphens")
    return session_id


def recent_messages(messages: list[dict], count: int) -> list[dict]:
    if count <= 0:
        return []
    return messages[-count:]


def recovery_notice(error: str, recent_count: int, *, first_count: int | None = None) -> str:
    if first_count is None:
        body = [
            "runtime messages 已超过上下文预算，但自动总结失败。",
            f"当前上下文只保留最近 {recent_count} 条消息。",
        ]
    else:
        body = [
            "之前的 transcript 超过上下文预算，但自动总结失败。",
            f"当前上下文只恢复最初 {first_count} 条消息和最近 {recent_count} 条消息。",
        ]
    return "\n".join(
        [
            "[Session recovery notice]",
            "",
            *body,
            "中间对话可能缺失；必要时可查看服务端 session 记录。",
            f"summary_error: {error}",
        ]
    )


def summary_input(
    messages: list[dict],
    existing_summary: str | None,
) -> list[dict]:
    if existing_summary is None:
        return messages
    return [
        {
            session_constants.MESSAGE_ROLE_FIELD: session_constants.MESSAGE_ROLE_USER,
            session_constants.MESSAGE_CONTENT_FIELD: f"[Existing session summary]\n\n{existing_summary}",
        }
    ] + messages


def summarize_tool_result(tool_name: str, result_text: str) -> str:
    length = len(result_text)
    first_line = next((line.strip() for line in result_text.splitlines() if line.strip()), "")
    if first_line:
        return f"{tool_name} 返回了 {length} 个字符；开头内容：{first_line[:120]}"
    return f"{tool_name} 返回了 {length} 个字符。"


_recent_messages = recent_messages
_recovery_notice = recovery_notice
_summary_input = summary_input
_summary = summarize_tool_result
