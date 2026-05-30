from __future__ import annotations

import re
from pathlib import Path

from .schemas import SessionSummary


class SessionStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.session_dir = self.root / ".session"
        self.current_path = self.session_dir / "current.md"
        self.artifacts_dir = self.session_dir / "artifacts"

    def load_current(self) -> SessionSummary:
        if not self.current_path.exists():
            return SessionSummary()
        return _parse_session_summary(self.current_path.read_text(encoding="utf-8"))

    def write_current(self, summary: SessionSummary) -> Path:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.current_path.write_text(_render_session_summary(summary), encoding="utf-8")
        return self.current_path

    def write_artifact(self, run_id: str, artifact_name: str, content: str) -> Path:
        if not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        if not artifact_name.strip():
            raise ValueError("artifact_name must be a non-empty string")

        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        filename = _safe_filename(f"{run_id}-{artifact_name}")
        path = self.artifacts_dir / filename
        path.write_text(content, encoding="utf-8")
        return path


def _render_session_summary(summary: SessionSummary) -> str:
    sections = [
        "# Current Session",
        "",
        "## Current Goal",
        summary.current_goal,
        "",
        "## Confirmed Decisions",
        *_render_list(summary.confirmed_decisions),
        "",
        "## Open Questions",
        *_render_list(summary.open_questions),
        "",
        "## Next Steps",
        *_render_list(summary.next_steps),
        "",
    ]
    return "\n".join(sections)


def _parse_session_summary(content: str) -> SessionSummary:
    return SessionSummary(
        current_goal=_section_text(content, "Current Goal"),
        confirmed_decisions=_section_list(content, "Confirmed Decisions"),
        open_questions=_section_list(content, "Open Questions"),
        next_steps=_section_list(content, "Next Steps"),
    )


def _section_text(content: str, title: str) -> str:
    return "\n".join(_section_lines(content, title)).strip()


def _section_list(content: str, title: str) -> list[str]:
    items: list[str] = []
    for line in _section_lines(content, title):
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def _section_lines(content: str, title: str) -> list[str]:
    lines = content.splitlines()
    marker = f"## {title}"
    try:
        start = lines.index(marker) + 1
    except ValueError:
        return []

    collected: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        collected.append(line)
    return collected


def _render_list(items: list[str]) -> list[str]:
    if not items:
        return []
    return [f"- {item}" for item in items]


def _safe_filename(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-")
    if not name:
        raise ValueError("artifact filename must not be empty")
    return name
