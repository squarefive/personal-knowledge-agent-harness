from __future__ import annotations

import json

from ..schemas import SessionRestoreResult
from .metadata import SessionMetadataStore
from .summarize_session import SessionSummarizer
from .transcript import SessionTranscript


class SessionRestore:
    def __init__(
        self,
        *,
        transcript: SessionTranscript,
        metadata_store: SessionMetadataStore,
        summarizer: SessionSummarizer | None = None,
        message_budget_chars: int = 120_000,
        first_messages_count: int = 6,
        recent_messages_count: int = 12,
    ):
        self.transcript = transcript
        self.metadata_store = metadata_store
        self.summarizer = summarizer
        self.message_budget_chars = message_budget_chars
        self.first_messages_count = first_messages_count
        self.recent_messages_count = recent_messages_count

    def restore(self) -> SessionRestoreResult:
        metadata = self.metadata_store.load_or_create()
        messages = self.transcript.load_messages()
        if _estimated_chars(messages) <= self.message_budget_chars:
            self.metadata_store.update_counts(
                event_count=self.transcript.event_count(),
                message_count=len(messages),
                last_restore_mode="full",
            )
            return SessionRestoreResult(messages=messages, mode="full")

        if self.summarizer is not None:
            try:
                summary, attempts = self.summarizer.summarize(messages)
                summary_path = self.metadata_store.root / metadata.summary_path
                summary_path.parent.mkdir(parents=True, exist_ok=True)
                summary_path.write_text(summary, encoding="utf-8")
                recent = _recent_messages(messages, self.recent_messages_count)
                restored = [_summary_message(summary)] + recent
                self.metadata_store.update_counts(
                    event_count=self.transcript.event_count(),
                    message_count=len(messages),
                    summary_status="valid",
                    summary_attempts=attempts,
                    last_restore_mode="summary_plus_recent",
                )
                return SessionRestoreResult(messages=restored, mode="summary_plus_recent", summary=summary)
            except Exception as exc:
                return self._fallback(messages, str(exc))

        return self._fallback(messages, "summarizer is not configured")

    def _fallback(self, messages: list[dict], error: str) -> SessionRestoreResult:
        notice = _recovery_notice(error, self.first_messages_count, self.recent_messages_count)
        restored = (
            messages[: self.first_messages_count]
            + [{"role": "user", "content": notice}]
            + _recent_messages(messages, self.recent_messages_count)
        )
        self.metadata_store.update_counts(
            event_count=self.transcript.event_count(),
            message_count=len(messages),
            summary_status="failed",
            summary_attempts=(self.summarizer.max_retries if self.summarizer is not None else 0),
            last_restore_mode="first_and_recent",
            summary_error=error[:240],
        )
        return SessionRestoreResult(messages=restored, mode="first_and_recent", warning=notice)


def _estimated_chars(messages: list[dict]) -> int:
    return len(json.dumps(messages, ensure_ascii=False))


def _summary_message(summary: str) -> dict[str, str]:
    return {"role": "user", "content": f"[Previous session summary]\n\n{summary}\n\nContinue from this state."}


def _recent_messages(messages: list[dict], count: int) -> list[dict]:
    if count <= 0:
        return []
    return messages[-count:]


def _recovery_notice(error: str, first_count: int, recent_count: int) -> str:
    return "\n".join(
        [
            "[Session recovery notice]",
            "",
            "之前的 transcript 超过上下文预算，但自动总结失败。",
            f"当前上下文只恢复最初 {first_count} 条消息和最近 {recent_count} 条消息。",
            "中间对话可能缺失；必要时可查看 transcript.jsonl。",
            f"summary_error: {error}",
        ]
    )
