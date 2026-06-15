from dataclasses import dataclass, field

from ..tool_runtime.tool_models import ToolCall


@dataclass(frozen=True)
class LLMResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
