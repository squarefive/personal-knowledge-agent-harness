from __future__ import annotations

from pathlib import Path

from .conversation_session_models import CompactRecord


class ToolResultCompactor:
    def __init__(
        self,
        root: str | Path,
        *,
        artifacts_dir: str | Path | None = None,
        threshold_chars: int = 8000,
    ):
        self.root = Path(root)
        if artifacts_dir is None:
            self.artifacts_dir = self.root / ".sessions" / "default" / "artifacts"
        else:
            self.artifacts_dir = self.root / artifacts_dir
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

        artifact_path = self._write_artifact(
            run_id=run_id,
            artifact_name=f"{tool_call_id}.txt",
            content=result_text,
        )
        return CompactRecord(
            artifact_path=str(artifact_path.relative_to(self.root)),
            summary=_summary(tool_name, result_text),
            relevance=f"该 tool result 来自 {tool_name}，因长度超过阈值已落盘供当前任务回读。",
            must_keep=[],
        )

    def _write_artifact(self, *, run_id: str, artifact_name: str, content: str) -> Path:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        filename = _safe_filename(f"{run_id}-{artifact_name}")
        path = self.artifacts_dir / filename
        path.write_text(content, encoding="utf-8")
        return path


def _summary(tool_name: str, result_text: str) -> str:
    length = len(result_text)
    first_line = next((line.strip() for line in result_text.splitlines() if line.strip()), "")
    if first_line:
        return f"{tool_name} 返回了 {length} 个字符；开头内容：{first_line[:120]}"
    return f"{tool_name} 返回了 {length} 个字符。"


def _safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in ("-", "_", ".") else "-" for char in value)
