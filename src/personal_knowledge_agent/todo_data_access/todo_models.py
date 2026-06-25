from dataclasses import dataclass


@dataclass(frozen=True)
class TodoItem:
    id: str
    title: str
    notes: str
    status: str
    due_at: str | None
    created_at: str
    updated_at: str
