from __future__ import annotations

import json
from typing import Protocol

from .constants import ConversationSessionConstants as session_constants


class SummarizerLLM(Protocol):
    def chat(self, *, messages, tools, system_prompt): ...


class ConversationSessionSummarizer:
    def __init__(self, llm: SummarizerLLM, *, max_retries: int = session_constants.SUMMARY_MAX_RETRIES):
        self.llm = llm
        self.max_retries = max_retries

    def summarize(self, messages: list[dict]) -> tuple[str, int]:
        last_error: Exception | None = None
        prompt = _summary_prompt(messages)
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.llm.chat(
                    messages=[
                        {
                            session_constants.MESSAGE_ROLE_FIELD: session_constants.MESSAGE_ROLE_USER,
                            session_constants.MESSAGE_CONTENT_FIELD: prompt,
                        }
                    ],
                    tools=[],
                    system_prompt=session_constants.SUMMARY_SYSTEM_PROMPT,
                )
                summary = (response.text or "").strip()
                _validate_summary(summary)
                return summary, attempt
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"session summary failed after {self.max_retries} attempts: {last_error}")


def _summary_prompt(messages: list[dict]) -> str:
    return "\n".join(
        [
            "请将以下 messages[] 压缩为 Markdown session summary：",
            "",
            "必须使用以下固定结构：",
            "",
            "# Session Summary",
            "",
            "## Current Goal",
            "",
            "## User Constraints",
            "",
            "## Known Context",
            "",
            "## Completed Work",
            "",
            "## Next Step",
            "",
            "## Boundaries",
            "",
            "Boundaries 必须说明：summary 不是用户新请求、不是长期 memory、不是 Q&A 知识来源。",
            "",
            json.dumps(messages, ensure_ascii=False),
        ]
    )


def _validate_summary(summary: str) -> None:
    if not summary:
        raise ValueError("empty summary")
    for heading in session_constants.REQUIRED_SUMMARY_HEADINGS:
        if heading not in summary:
            raise ValueError(f"summary missing required heading: {heading}")
    boundaries = summary.split("## Boundaries", maxsplit=1)[-1]
    for statement in session_constants.REQUIRED_BOUNDARY_STATEMENTS:
        if statement not in boundaries:
            raise ValueError(f"summary missing required boundary statement: {statement}")
