from __future__ import annotations

import json
import queue
import sys
import threading
from pathlib import Path
from typing import Final

from ..agent_runtime.agent_events import AgentEvent

_STOP: Final = object()


class AgentEventJsonlLogger:
    def __init__(
        self,
        path: str | Path = ".logs/agent.log",
        *,
        max_queue_size: int = 1000,
        flush_timeout_seconds: float = 2.0,
    ):
        self.path = Path(path)
        self.flush_timeout_seconds = flush_timeout_seconds
        self._queue: queue.Queue[AgentEvent | object] = queue.Queue(maxsize=max_queue_size)
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._disabled = False
        self._warned = False
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def write(self, event: AgentEvent) -> None:
        if self._disabled:
            return
        if not self._started:
            self.start()
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self._warn_once("agent log queue full; dropping log events")

    def close(self) -> None:
        if not self._started:
            return
        try:
            self._queue.put_nowait(_STOP)
        except queue.Full:
            self._warn_once("agent log queue full during shutdown; log flush may be incomplete")
        self._thread.join(timeout=self.flush_timeout_seconds)

    def _worker(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._disable(f"failed to create agent log directory: {exc}")
            return

        while True:
            item = self._queue.get()
            if item is _STOP:
                self._queue.task_done()
                return
            try:
                self._append(item)
            except OSError as exc:
                self._disable(f"failed to write agent log; logger disabled: {exc}")
                self._queue.task_done()
                return
            self._queue.task_done()

    def _append(self, event: AgentEvent | object) -> None:
        if not isinstance(event, AgentEvent):
            return
        line = json.dumps(event.to_log_dict(), ensure_ascii=False, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")

    def _disable(self, message: str) -> None:
        self._disabled = True
        self._warn_once(message)

    def _warn_once(self, message: str) -> None:
        if self._warned:
            return
        self._warned = True
        print(message, file=sys.stderr)
