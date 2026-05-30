from __future__ import annotations

from .schemas import CompactRecord
from .session_store import SessionStore


class ContextCompactor:
    def __init__(self, session_store: SessionStore, threshold_chars: int = 8000):
        self.session_store = session_store
        self.threshold_chars = threshold_chars

    def compact_tool_result(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        result_text: str,
    ) -> CompactRecord | None:
        if len(result_text) <= self.threshold_chars:
            return None

        artifact_path = self.session_store.write_artifact(
            run_id=run_id,
            artifact_name=f"{tool_call_id}.txt",
            content=result_text,
        )
        return CompactRecord(
            artifact_path=str(artifact_path.relative_to(self.session_store.root)),
            summary=_summary(tool_name, result_text),
            relevance=f"该 tool result 来自 {tool_name}，因长度超过阈值已落盘供当前任务回读。",
            must_keep=[],
        )


def _summary(tool_name: str, result_text: str) -> str:
    length = len(result_text)
    first_line = next((line.strip() for line in result_text.splitlines() if line.strip()), "")
    if first_line:
        return f"{tool_name} 返回了 {length} 个字符；开头内容：{first_line[:120]}"
    return f"{tool_name} 返回了 {length} 个字符。"
