from __future__ import annotations

from typing import Any, Callable

from ..events import AgentEvent

EventSink = Callable[[AgentEvent], None]


class AgentEventEmitter:
    def __init__(self, event_sink: EventSink | None = None):
        self.event_sink = event_sink

    def emit(self, run_id: str, event_type: str, **payload: Any) -> None:
        if self.event_sink is None:
            return
        self.event_sink(AgentEvent(run_id=run_id, event_type=event_type, payload=payload))
