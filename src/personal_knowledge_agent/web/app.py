from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..agent_factory import create_agent_components
from ..config import AgentConfig, load_config
from ..events import AgentEvent


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

    def collect_event(event: AgentEvent) -> None:
        events.append(event.to_log_dict())

    if agent is None or tools is None:
        components = create_agent_components(config or load_config(), event_sink=collect_event)
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

    @app.post("/api/chat")
    def chat(request: ChatRequest) -> dict[str, Any]:
        message = request.message.strip()
        if not message:
            return _error("invalid_input", "message must be a non-empty string")
        try:
            with agent_lock:
                answer = agent.run(message)
        except Exception as exc:
            return _error("agent_error", f"Agent run failed: {exc}")
        return {"ok": True, "answer": answer, "events": events[-20:]}

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
