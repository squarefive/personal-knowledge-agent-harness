from __future__ import annotations

from pathlib import Path

from .agent_memory_index_repository import AGENT_MEMORY_TYPES
from .agent_memory_models import MemoryDocument, MemoryIndexEntry

REQUIRED_FRONTMATTER_FIELDS = ["name", "type", "description", "updated_at", "source_type"]


class AgentMemoryDocumentRepository:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def read_by_entry(self, entry: MemoryIndexEntry) -> MemoryDocument:
        return self.read_path(entry.path)

    def read_path(self, path: str | Path) -> MemoryDocument:
        memory_path = self._resolve_memory_path(path)
        if not memory_path.exists():
            raise FileNotFoundError(f"memory not found: {path}")

        metadata, content = _parse_frontmatter(memory_path.read_text(encoding="utf-8"))
        for field in REQUIRED_FRONTMATTER_FIELDS:
            if not metadata.get(field):
                raise ValueError(f"memory frontmatter missing required field: {field}")
        if metadata["type"] not in AGENT_MEMORY_TYPES:
            raise ValueError(
                f"memory type must be one of {sorted(AGENT_MEMORY_TYPES)}: {metadata['type']}"
            )

        return MemoryDocument(
            name=metadata["name"],
            type=metadata["type"],
            description=metadata["description"],
            path=str(memory_path.relative_to(self.root)),
            updated_at=metadata["updated_at"],
            source_type=metadata["source_type"],
            source_ref=metadata.get("source_ref") or None,
            content=content.strip(),
        )

    def _resolve_memory_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            raise ValueError("memory path must be relative")
        memory_root = (self.root / ".memory").resolve()
        resolved = (self.root / candidate).resolve()
        if not resolved.is_relative_to(memory_root):
            raise ValueError("memory path must stay under .memory")
        return resolved


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    if not raw.startswith("---\n"):
        raise ValueError("memory frontmatter is required")

    end = raw.find("\n---\n", 4)
    if end == -1:
        raise ValueError("memory frontmatter is not closed")

    metadata: dict[str, str] = {}
    for line in raw[4:end].splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')

    content = raw[end + len("\n---\n") :]
    return metadata, content
