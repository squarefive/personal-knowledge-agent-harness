from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex}"


@dataclass(frozen=True)
class AgentEvent:
    run_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_log_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            **self.payload,
        }
