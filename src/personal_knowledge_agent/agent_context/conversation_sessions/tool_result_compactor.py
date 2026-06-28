from __future__ import annotations

from typing import Protocol

from .conversation_session_models import CompactRecord
from .session_utils import _summary


class ToolResultCompactor(Protocol):
    def compact_tool_result(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        result_text: str,
    ) -> CompactRecord | None: ...
