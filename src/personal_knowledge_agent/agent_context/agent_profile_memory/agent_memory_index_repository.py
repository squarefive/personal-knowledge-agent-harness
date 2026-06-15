from __future__ import annotations

from pathlib import Path

from ...schemas import MemoryIndex, MemoryIndexEntry

MEMORY_TYPES = {"user", "feedback", "project", "reference"}
REQUIRED_COLUMNS = ["name", "type", "description", "path"]


class MemoryIndexStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / ".memory" / "MEMORY.md"

    def load(self) -> MemoryIndex:
        if not self.path.exists():
            return MemoryIndex()

        rows = _parse_markdown_table(self.path.read_text(encoding="utf-8"))
        entries: list[MemoryIndexEntry] = []
        for row in rows:
            entry = MemoryIndexEntry(
                name=_required_cell(row, "name"),
                type=_required_cell(row, "type"),
                description=_required_cell(row, "description"),
                path=_required_cell(row, "path"),
            )
            if entry.type not in MEMORY_TYPES:
                raise ValueError(f"memory type must be one of {sorted(MEMORY_TYPES)}: {entry.type}")
            entries.append(entry)
        return MemoryIndex(entries=entries)


def _parse_markdown_table(content: str) -> list[dict[str, str]]:
    table_lines = [line.strip() for line in content.splitlines() if line.strip().startswith("|")]
    if not table_lines:
        return []

    headers = _split_row(table_lines[0])
    missing = [column for column in REQUIRED_COLUMNS if column not in headers]
    if missing:
        raise ValueError(f"memory index missing required columns: {', '.join(missing)}")

    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = _split_row(line)
        if len(cells) != len(headers):
            raise ValueError("memory index row does not match header column count")
        rows.append(dict(zip(headers, cells)))
    return rows


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _required_cell(row: dict[str, str], name: str) -> str:
    value = row.get(name, "").strip()
    if not value:
        raise ValueError(f"memory index field must not be empty: {name}")
    return value


AGENT_MEMORY_TYPES = MEMORY_TYPES
AgentMemoryIndexRepository = MemoryIndexStore
