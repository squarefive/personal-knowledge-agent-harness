from __future__ import annotations

from typing import Any, Protocol

from .conversation_session_models import RuntimeCompactionResult


class RuntimeContextCompactor(Protocol):
    def compact(
        self,
        messages: list[dict[str, Any]],
        *,
        existing_summary: str | None = None,
    ) -> RuntimeCompactionResult: ...
