from __future__ import annotations

import json
import queue
import threading
import uuid
from dataclasses import asdict
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
from ..schemas import SessionMetadata
from ..session_memory import SessionMetadataStore, SessionTranscript, validate_session_id

SESSION_ID_SUFFIX_CHARS = 12
THREAD_JOIN_TIMEOUT_SECONDS = 1
DEFAULT_CARD_LIMIT = 10
MIN_CARD_LIMIT = 1
MAX_CARD_LIMIT = 50


class ChatAgent(Protocol):
    def run(self, user_input: str) -> str: ...


class CardTools(Protocol):
    def list_recent_cards(self, arguments: dict[str, Any]) -> dict[str, Any]: ...

    def search_qa_cards(self, arguments: dict[str, Any]) -> dict[str, Any]: ...

    def read_qa_card(self, arguments: dict[str, Any]) -> dict[str, Any]: ...


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class RenameSessionRequest(BaseModel):
    title: str


class WebSessionRunner:
    def __init__(self, *, session_id: str, agent: ChatAgent | None, events: list[dict[str, Any]]):
        self.session_id = session_id
        self.agent = agent
        self.events = events
        self.lock = threading.Lock()
        self.active_event_queue: queue.Queue[dict[str, Any] | object] | None = None
        self.active_event_queue_lock = threading.Lock()

    def collect_event(self, event: AgentEvent) -> None:
        event_dict = event.to_log_dict()
        if event.event_type != "answer_delta":
            self.events.append(event_dict)
        with self.active_event_queue_lock:
            current_queue = self.active_event_queue
        if current_queue is not None:
            current_queue.put(event_dict)


def create_web_app(
    *,
    config: AgentConfig | None = None,
    agent: ChatAgent | None = None,
    tools: CardTools | None = None,
) -> FastAPI:
    events: list[dict[str, Any]] = []
    resolved_config = config or (load_config() if agent is None or tools is None else None)
    runners: dict[str, WebSessionRunner] = {}
    runners_lock = threading.Lock()
    workspace_root = Path.cwd()

    def get_runner(session_id: str) -> WebSessionRunner:
        safe_session_id = validate_session_id(session_id)
        with runners_lock:
            if safe_session_id in runners:
                return runners[safe_session_id]
            if agent is not None:
                runner = WebSessionRunner(session_id=safe_session_id, agent=agent, events=events)
            else:
                placeholder = WebSessionRunner(session_id=safe_session_id, agent=None, events=events)
                components = create_agent_components(
                    resolved_config,
                    event_sink=placeholder.collect_event,
                    approval_callback=default_approval_callback,
                    session_id=safe_session_id,
                )
                placeholder.agent = components.agent
                runner = placeholder
            runners[safe_session_id] = runner
            return runner

    if tools is None:
        tools = create_agent_components(
            resolved_config,
            approval_callback=default_approval_callback,
            session_id="default",
        ).tools

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

    @app.post("/api/sessions")
    def create_session() -> dict[str, Any]:
        session_id = f"session_{uuid.uuid4().hex[:SESSION_ID_SUFFIX_CHARS]}"
        metadata = SessionMetadataStore(workspace_root, session_id=session_id).load_or_create()
        return {"ok": True, "session": _metadata_payload(metadata)}

    @app.get("/api/sessions")
    def list_sessions() -> dict[str, Any]:
        sessions = SessionMetadataStore(workspace_root).list_sessions()
        return {"ok": True, "sessions": [_metadata_payload(metadata) for metadata in sessions]}

    @app.patch("/api/sessions/{session_id}")
    def rename_session(session_id: str, request: RenameSessionRequest) -> dict[str, Any]:
        try:
            metadata = SessionMetadataStore(workspace_root, session_id=session_id).rename_session(request.title)
            return {"ok": True, "session": _metadata_payload(metadata)}
        except Exception as exc:
            return _error("session_rename_error", str(exc))

    @app.get("/api/sessions/{session_id}/messages")
    def read_session_messages(session_id: str) -> dict[str, Any]:
        try:
            transcript = SessionTranscript(workspace_root, session_id=session_id)
            return {"ok": True, "messages": transcript.load_display_messages()}
        except Exception as exc:
            return _error("session_read_error", str(exc))

    @app.post("/api/chat/stream")
    def chat_stream(request: ChatRequest) -> StreamingResponse:
        message = request.message.strip()
        session_id = request.session_id or "default"
        event_queue: queue.Queue[dict[str, Any] | object] = queue.Queue()
        done = object()

        def run_agent() -> None:
            if not message:
                event_queue.put(_event_error("invalid_input", "message must be a non-empty string"))
                event_queue.put(done)
                return
            try:
                runner = get_runner(session_id)
                with runner.lock:
                    with runner.active_event_queue_lock:
                        runner.active_event_queue = event_queue
                    try:
                        event_count_before = event_queue.qsize()
                        if runner.agent is None:
                            raise RuntimeError("session runner is not initialized")
                        answer = runner.agent.run(message)
                        if event_queue.qsize() == event_count_before and isinstance(answer, str):
                            event_queue.put(
                                {
                                    "run_id": new_run_id(),
                                    "event_type": "final_answer_generated",
                                    "answer": answer,
                                }
                            )
                    finally:
                        with runner.active_event_queue_lock:
                            runner.active_event_queue = None
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
            thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/api/cards/recent")
    def recent_cards(
        limit: int = Query(default=DEFAULT_CARD_LIMIT, ge=MIN_CARD_LIMIT, le=MAX_CARD_LIMIT),
    ) -> dict[str, Any]:
        try:
            return tools.list_recent_cards({"limit": limit})
        except Exception as exc:
            return _error("card_read_error", str(exc))

    @app.get("/api/cards/search")
    def search_cards(
        q: str = Query(default="", alias="q"),
        limit: int = Query(default=DEFAULT_CARD_LIMIT, ge=MIN_CARD_LIMIT, le=MAX_CARD_LIMIT),
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


def _metadata_payload(metadata: SessionMetadata) -> dict[str, Any]:
    return asdict(metadata)


def _event_error(error_code: str, message: str) -> dict[str, Any]:
    return {
        "run_id": new_run_id(),
        "event_type": "error",
        "error_code": error_code,
        "message": message,
    }


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
