from __future__ import annotations

import json
import queue
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ...agent_bootstrap import AgentConfig, create_agent_components, load_config
from ...agent_context.conversation_sessions import (
    ConversationSessionMetadataRepository,
    ConversationTranscriptRepository,
    SessionMetadata,
    validate_session_id,
)
from ...agent_runtime import AgentEvent, new_run_id
from ...tool_runtime import ApprovalRequest, default_approval_callback

SESSION_ID_SUFFIX_CHARS = 12
THREAD_JOIN_TIMEOUT_SECONDS = 1
APPROVAL_TIMEOUT_SECONDS = 300
APPROVAL_SUMMARY_TEXT_LIMIT = 180
APPROVAL_SUMMARY_ELLIPSIS = "..."
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


class ApprovalDecisionRequest(BaseModel):
    """Browser decision for a pending high-risk tool approval."""

    decision: str


@dataclass
class PendingApproval:
    """In-memory approval request waiting for a browser decision.

    Attributes:
        approval_id: Browser-facing identifier for the pending request.
        session_id: Conversation session that owns the request.
        summary: Safe, truncated fields rendered in the confirmation card.
        expires_at: ISO timestamp for the automatic denial deadline.
        decision_event: Synchronization event released by browser decisions.
        approved: Whether the browser allowed the tool execution.
        status: Current lifecycle state for the request.
    """

    approval_id: str
    session_id: str
    summary: dict[str, Any]
    expires_at: str
    decision_event: threading.Event = field(default_factory=threading.Event)
    approved: bool = False
    status: str = "pending"


class WebApprovalManager:
    """Coordinates one-shot Web approvals for high-risk tool calls."""

    def __init__(self, *, timeout_seconds: float = APPROVAL_TIMEOUT_SECONDS):
        self.timeout_seconds = timeout_seconds
        self.pending_approvals: dict[str, PendingApproval] = {}
        self.lock = threading.Lock()

    def request_approval(
        self,
        *,
        session_id: str,
        request: ApprovalRequest,
        emit_event: Callable[[dict[str, Any]], bool],
    ) -> bool:
        """Wait for a browser approval decision.

        Inputs:
            session_id: Conversation session that owns the pending approval.
            request: High-risk tool request from the agent runtime.
            emit_event: Callback used to publish SSE-compatible permission events.
        Outputs:
            True when the browser explicitly approves before timeout; otherwise False.
        Side Effects:
            Registers a pending approval, emits request/resolution events, and blocks until
            a decision, timeout, or stream disconnect.
        """

        pending = self._create_pending(session_id, request)
        event_sent = emit_event(
            {
                "run_id": new_run_id(),
                "event_type": "permission_requested",
                "approval_id": pending.approval_id,
                "summary": pending.summary,
                "timeout_seconds": self.timeout_seconds,
                "expires_at": pending.expires_at,
            }
        )
        if not event_sent:
            self._remove_pending(pending)
            return False

        if not pending.decision_event.wait(self.timeout_seconds):
            self._remove_pending(pending)
            pending.status = "expired"
            pending.approved = False

        emit_event(
            {
                "run_id": new_run_id(),
                "event_type": "permission_resolved",
                "approval_id": pending.approval_id,
                "status": pending.status,
            }
        )
        return pending.approved

    def resolve(self, approval_id: str, decision: str) -> dict[str, Any]:
        """Resolve a pending approval from the browser confirmation API.

        Inputs:
            approval_id: Identifier previously emitted in a permission request event.
            decision: Browser decision, either approve or deny.
        Outputs:
            API payload describing the accepted decision or validation error.
        Side Effects:
            Removes the pending approval and releases the blocked agent run.
        """

        normalized_decision = decision.strip().lower()
        if normalized_decision not in {"approve", "deny"}:
            return _error("invalid_input", "decision must be approve or deny")
        pending = self._pop_pending(approval_id)
        if pending is None or pending.status != "pending":
            return _error("approval_not_found", "approval request is not pending")
        pending.approved = normalized_decision == "approve"
        pending.status = "approved" if pending.approved else "denied"
        pending.decision_event.set()
        return {"ok": True, "approval_id": approval_id, "status": pending.status}

    def cancel_session(self, session_id: str) -> None:
        """Cancel all pending approvals for a disconnected session stream.

        Inputs:
            session_id: Conversation session whose stream disconnected.
        Outputs:
            None.
        Side Effects:
            Marks matching pending approvals as cancelled and releases waiting runs.
        """

        with self.lock:
            cancelled = [
                pending
                for pending in self.pending_approvals.values()
                if pending.session_id == session_id and pending.status == "pending"
            ]
            for pending in cancelled:
                self.pending_approvals.pop(pending.approval_id, None)
                pending.status = "cancelled"
                pending.approved = False
                pending.decision_event.set()

    def _create_pending(self, session_id: str, request: ApprovalRequest) -> PendingApproval:
        """Create and register a pending approval."""

        expires_at = datetime.now(UTC) + timedelta(seconds=self.timeout_seconds)
        pending = PendingApproval(
            approval_id=f"approval_{uuid.uuid4().hex}",
            session_id=session_id,
            summary=build_approval_summary(request),
            expires_at=expires_at.isoformat(),
        )
        with self.lock:
            self.pending_approvals[pending.approval_id] = pending
        return pending

    def _pop_pending(self, approval_id: str) -> PendingApproval | None:
        """Remove and return a pending approval by ID."""

        with self.lock:
            return self.pending_approvals.pop(approval_id, None)

    def _remove_pending(self, pending: PendingApproval) -> None:
        """Remove a pending approval if it is still registered."""

        with self.lock:
            if self.pending_approvals.get(pending.approval_id) is pending:
                self.pending_approvals.pop(pending.approval_id)


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
        self.put_event(event_dict)

    def put_event(self, event: dict[str, Any]) -> bool:
        with self.active_event_queue_lock:
            current_queue = self.active_event_queue
        if current_queue is not None:
            current_queue.put(event)
            return True
        return False


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
    approval_manager = WebApprovalManager(timeout_seconds=APPROVAL_TIMEOUT_SECONDS)
    workspace_root = Path.cwd()

    def request_web_approval(runner: WebSessionRunner, request: ApprovalRequest) -> bool:
        return approval_manager.request_approval(
            session_id=runner.session_id,
            request=request,
            emit_event=runner.put_event,
        )

    def make_approval_callback(runner: WebSessionRunner) -> Callable[[ApprovalRequest], bool]:
        return lambda request: request_web_approval(runner, request)

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
                    approval_callback=make_approval_callback(placeholder),
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
    app.state.approval_manager = approval_manager

    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True}

    @app.post("/api/approvals/{approval_id}")
    def resolve_approval(approval_id: str, request: ApprovalDecisionRequest) -> dict[str, Any]:
        return approval_manager.resolve(approval_id, request.decision)

    @app.post("/api/sessions")
    def create_session() -> dict[str, Any]:
        session_id = f"session_{uuid.uuid4().hex[:SESSION_ID_SUFFIX_CHARS]}"
        metadata = ConversationSessionMetadataRepository(
            workspace_root,
            session_id=session_id,
        ).load_or_create()
        return {"ok": True, "session": _metadata_payload(metadata)}

    @app.get("/api/sessions")
    def list_sessions() -> dict[str, Any]:
        sessions = ConversationSessionMetadataRepository(workspace_root).list_sessions()
        return {"ok": True, "sessions": [_metadata_payload(metadata) for metadata in sessions]}

    @app.patch("/api/sessions/{session_id}")
    def rename_session(session_id: str, request: RenameSessionRequest) -> dict[str, Any]:
        try:
            metadata = ConversationSessionMetadataRepository(
                workspace_root,
                session_id=session_id,
            ).rename_session(request.title)
            return {"ok": True, "session": _metadata_payload(metadata)}
        except Exception as exc:
            return _error("session_rename_error", str(exc))

    @app.get("/api/sessions/{session_id}/messages")
    def read_session_messages(session_id: str) -> dict[str, Any]:
        try:
            transcript = ConversationTranscriptRepository(workspace_root, session_id=session_id)
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
            try:
                while True:
                    item = event_queue.get()
                    if item is done:
                        break
                    yield _sse(item)
            finally:
                approval_manager.cancel_session(session_id)
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


def build_approval_summary(request: ApprovalRequest) -> dict[str, Any]:
    """Build the safe browser-facing summary for a tool approval request.

    Inputs:
        request: High-risk tool approval request from the agent runtime.
    Outputs:
        Truncated summary fields that intentionally exclude complete JSON arguments.
    Side Effects:
        None.
    """

    arguments = request.arguments
    if request.tool_name == "delete_qa_card":
        return {
            "title": "删除知识卡片",
            "tool_name": request.tool_name,
            "tool_label": "删除知识卡片",
            "target_label": "卡片 ID",
            "target": _truncate_summary_text(str(arguments.get("card_id") or "")),
            "changes": [],
            "preview": "",
            "risk": "将物理删除本地知识卡片。",
            "reason": _truncate_summary_text(request.reason),
        }
    if request.tool_name == "update_qa_card":
        changed_fields = [
            label
            for field_name, label in [
                ("question", "原始问题"),
                ("answer", "原始答案"),
                ("summary", "摘要"),
                ("keywords", "关键词"),
                ("category", "分类"),
            ]
            if field_name in arguments
        ]
        return {
            "title": "更新知识卡片",
            "tool_name": request.tool_name,
            "tool_label": "更新知识卡片",
            "target_label": "卡片 ID",
            "target": _truncate_summary_text(str(arguments.get("card_id") or "")),
            "changes": changed_fields,
            "preview": _truncate_summary_text(_first_update_preview(arguments)),
            "risk": "将覆盖当前卡片内容。",
            "reason": _truncate_summary_text(request.reason),
        }
    return {
        "title": "确认高风险工具",
        "tool_name": request.tool_name,
        "tool_label": request.tool_name,
        "target_label": "工具",
        "target": request.tool_name,
        "changes": [],
        "preview": "",
        "risk": "该操作会修改本地数据。",
        "reason": _truncate_summary_text(request.reason),
    }


def _first_update_preview(arguments: dict[str, Any]) -> str:
    """Return the first meaningful update value for the confirmation preview."""

    for field_name in ["question", "answer", "summary", "category", "keywords"]:
        value = arguments.get(field_name)
        if isinstance(value, list) and value:
            return ", ".join(str(item) for item in value)
        if value:
            return str(value)
    return ""


def _truncate_summary_text(value: str, limit: int = APPROVAL_SUMMARY_TEXT_LIMIT) -> str:
    """Truncate approval summary text, including the ellipsis in the limit."""

    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - len(APPROVAL_SUMMARY_ELLIPSIS)]}{APPROVAL_SUMMARY_ELLIPSIS}"
