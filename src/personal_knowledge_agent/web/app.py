from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..agent_factory import create_agent_components
from ..config import AgentConfig, load_config
from ..events import AgentEvent, new_run_id
from ..permissions import default_approval_callback


class ChatAgent(Protocol):
    def run(self, user_input: str) -> str: ...


class CardTools(Protocol):
    def list_recent_cards(self, arguments: dict[str, Any]) -> dict[str, Any]: ...

    def search_qa_cards(self, arguments: dict[str, Any]) -> dict[str, Any]: ...

    def read_qa_card(self, arguments: dict[str, Any]) -> dict[str, Any]: ...


class ChatRequest(BaseModel):
    message: str


def create_web_app(
    *,
    config: AgentConfig | None = None,
    agent: ChatAgent | None = None,
    tools: CardTools | None = None,
) -> FastAPI:
    events: list[dict[str, Any]] = []
    agent_lock = threading.Lock()
    active_event_queue: queue.Queue[dict[str, Any] | object] | None = None
    active_event_queue_lock = threading.Lock()

    def collect_event(event: AgentEvent) -> None:
        event_dict = event.to_log_dict()
        if event.event_type != "answer_delta":
            events.append(event_dict)
        with active_event_queue_lock:
            current_queue = active_event_queue
        if current_queue is not None:
            current_queue.put(event_dict)

    if agent is None or tools is None:
        components = create_agent_components(
            config or load_config(),
            event_sink=collect_event,
            approval_callback=default_approval_callback,
        )
        agent = components.agent
        tools = components.tools

    app = FastAPI(title="Personal Knowledge Agent")
    app.state.agent_events = events

    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True}

    @app.post("/api/chat/stream")
    def chat_stream(request: ChatRequest) -> StreamingResponse:
        message = request.message.strip()
        event_queue: queue.Queue[dict[str, Any] | object] = queue.Queue()
        done = object()

        def run_agent() -> None:
            nonlocal active_event_queue
            if not message:
                event_queue.put(_event_error("invalid_input", "message must be a non-empty string"))
                event_queue.put(done)
                return
            try:
                with agent_lock:
                    with active_event_queue_lock:
                        active_event_queue = event_queue
                    try:
                        event_count_before = event_queue.qsize()
                        answer = agent.run(message)
                        if event_queue.qsize() == event_count_before and isinstance(answer, str):
                            event_queue.put(
                                {
                                    "run_id": new_run_id(),
                                    "event_type": "final_answer_generated",
                                    "answer": answer,
                                }
                            )
                    finally:
                        with active_event_queue_lock:
                            active_event_queue = None
            except Exception as exc:
                event_queue.put(_event_error("agent_error", f"Agent run failed: {exc}"))
            finally:
                event_queue.put(done)

        def event_stream():
            thread = threading.Thread(target=run_agent, daemon=True)
            thread.start()
            while True:
                item = event_queue.get()
                if item is done:
                    break
                yield _sse(item)
            thread.join(timeout=1)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/api/cards/recent")
    def recent_cards(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, Any]:
        try:
            return tools.list_recent_cards({"limit": limit})
        except Exception as exc:
            return _error("card_read_error", str(exc))

    @app.get("/api/cards/search")
    def search_cards(
        q: str = Query(default="", alias="q"),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> dict[str, Any]:
        query = q.strip()
        if not query:
            return _error("invalid_input", "q must be a non-empty string")
        try:
            return tools.search_qa_cards({"query": query, "limit": limit})
        except Exception as exc:
            return _error("card_search_error", str(exc))

    @app.get("/api/cards/{card_id}")
    def read_card(card_id: str) -> dict[str, Any]:
        try:
            return tools.read_qa_card({"card_id": card_id})
        except Exception as exc:
            return _error("card_read_error", str(exc))

    return app


def _error(error_code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error_code": error_code, "message": message}


def _event_error(error_code: str, message: str) -> dict[str, Any]:
    return {
        "run_id": new_run_id(),
        "event_type": "error",
        "error_code": error_code,
        "message": message,
    }


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
