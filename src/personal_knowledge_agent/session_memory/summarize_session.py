from __future__ import annotations

import json
from typing import Protocol


class SummarizerLLM(Protocol):
    def chat(self, *, messages, tools, system_prompt): ...


class SessionSummarizer:
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
                if not summary:
                    raise ValueError("empty summary")
                return summary, attempt
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"session summary failed after {self.max_retries} attempts: {last_error}")


SUMMARY_SYSTEM_PROMPT = "\n".join(
    [
        "你负责把过长的 Agent 会话 transcript 压缩为可恢复的 session summary。",
        "保留当前目标、用户约束、重要上下文、已完成工作、工具结果和下一步。",
        "不要编造 transcript 中不存在的信息。",
        "不要包含 API key、secret 或完整内部 payload。",
    ]
)


def _summary_prompt(messages: list[dict]) -> str:
    return "\n".join(
        [
            "请将以下 messages[] 压缩为 Markdown session summary：",
            "",
            json.dumps(messages, ensure_ascii=False),
        ]
    )
