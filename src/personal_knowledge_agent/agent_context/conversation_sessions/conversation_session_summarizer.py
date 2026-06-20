from __future__ import annotations

import json
from typing import Protocol


class SummarizerLLM(Protocol):
    def chat(self, *, messages, tools, system_prompt): ...


class ConversationSessionSummarizer:
    def __init__(self, llm: SummarizerLLM, *, max_retries: int = 3):
        self.llm = llm
        self.max_retries = max_retries

    def summarize(self, messages: list[dict]) -> tuple[str, int]:
        last_error: Exception | None = None
        prompt = _summary_prompt(messages)
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    tools=[],
                    system_prompt=SUMMARY_SYSTEM_PROMPT,
                )
                summary = (response.text or "").strip()
                _validate_summary(summary)
                return summary, attempt
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"session summary failed after {self.max_retries} attempts: {last_error}")


SUMMARY_SYSTEM_PROMPT = "\n".join(
    [
        "你负责把过长的 Agent 会话 transcript 压缩为可恢复的 session summary。",
        "必须输出固定 Markdown 规格，包含 # Session Summary 以及所有要求的二级标题。",
        "保留当前目标、用户约束、重要上下文、已完成工作和下一步。",
        "不要编造 transcript 中不存在的信息。",
        "不要包含 API key、secret 或完整内部 payload。",
        "Boundaries 必须说明 summary 不是用户新请求、不是长期 memory、不是 Q&A 知识来源。",
    ]
)

REQUIRED_SUMMARY_HEADINGS = (
    "# Session Summary",
    "## Current Goal",
    "## User Constraints",
    "## Known Context",
    "## Completed Work",
    "## Next Step",
    "## Boundaries",
)

REQUIRED_BOUNDARY_STATEMENTS = (
    "不是用户新请求",
    "不是长期 memory",
    "不是 Q&A 知识来源",
)


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
    for heading in REQUIRED_SUMMARY_HEADINGS:
        if heading not in summary:
            raise ValueError(f"summary missing required heading: {heading}")
    boundaries = summary.split("## Boundaries", maxsplit=1)[-1]
    for statement in REQUIRED_BOUNDARY_STATEMENTS:
        if statement not in boundaries:
            raise ValueError(f"summary missing required boundary statement: {statement}")
