from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .conversation_session_summarizer import ConversationSessionSummarizer


@dataclass(frozen=True)
class RuntimeCompactionResult:
    messages: list[dict[str, Any]]
    session_summary: str
    mode: str
    warning: str | None = None


class RuntimeContextCompactor:
    def __init__(
        self,
        root: str | Path,
        *,
        summarizer: ConversationSessionSummarizer,
        session_id: str = "default",
        recent_messages_count: int = 12,
    ):
        self.root = Path(root)
        self.summarizer = summarizer
        self.session_id = session_id
        self.recent_messages_count = recent_messages_count
        self.summary_path = self.root / ".sessions" / session_id / "summary.md"

    def compact(
        self,
        messages: list[dict[str, Any]],
        *,
        existing_summary: str | None = None,
    ) -> RuntimeCompactionResult:
        summary_input = _summary_input(messages, existing_summary)
        try:
            summary, _attempts = self.summarizer.summarize(summary_input)
        except Exception as exc:
            notice = _recovery_notice(str(exc), self.recent_messages_count)
            return RuntimeCompactionResult(
                messages=_recent_messages(messages, self.recent_messages_count),
                session_summary=notice,
                mode="recent_with_recovery_notice",
                warning=notice,
            )

        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        self.summary_path.write_text(summary, encoding="utf-8")
        return RuntimeCompactionResult(
            messages=_recent_messages(messages, self.recent_messages_count),
            session_summary=summary,
            mode="summary_plus_recent",
        )


def _summary_input(
    messages: list[dict[str, Any]],
    existing_summary: str | None,
) -> list[dict[str, Any]]:
    if existing_summary is None:
        return messages
    return [{"role": "user", "content": f"[Existing session summary]\n\n{existing_summary}"}] + messages


def _recent_messages(messages: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    return messages[-count:]


def _recovery_notice(error: str, recent_count: int) -> str:
    return "\n".join(
        [
            "[Session recovery notice]",
            "",
            "runtime messages 已超过上下文预算，但自动总结失败。",
            f"当前上下文只保留最近 {recent_count} 条消息。",
            "中间对话可能缺失；必要时可查看 transcript.jsonl。",
            f"summary_error: {error}",
        ]
    )
