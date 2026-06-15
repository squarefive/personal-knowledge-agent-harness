from dataclasses import dataclass, field


@dataclass(frozen=True)
class MemoryIndexEntry:
    name: str
    type: str
    description: str
    path: str


@dataclass(frozen=True)
class MemoryIndex:
    entries: list[MemoryIndexEntry] = field(default_factory=list)


@dataclass(frozen=True)
class MemoryDocument:
    name: str
    type: str
    description: str
    path: str
    updated_at: str
    source_type: str
    source_ref: str | None
    content: str


@dataclass(frozen=True)
class MemoryCandidate:
    name: str
    type: str
    description: str
    content: str
    source_type: str
    source_ref: str | None
    confidence: str
    write_policy: str
