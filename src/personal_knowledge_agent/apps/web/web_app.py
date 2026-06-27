from __future__ import annotations

import json
import math
import queue
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol

from fastapi import Cookie, FastAPI, Query, Response
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
from ...agent_observability import AgentEventJsonlLogger
from ...agent_runtime import AgentEvent, new_run_id
from ...postgres import (
    InMemoryToolResultCompactor,
    PostgresConversationSessionRepository,
    PostgresConversationTranscriptAdapter,
    PostgresRuntimeContextCompactor,
    PostgresSessionMetadataAdapter,
)
from ...tool_runtime import ApprovalRequest, default_approval_callback
from .cloud_dependencies import CloudUserToolFactory

SESSION_ID_SUFFIX_CHARS = 12
THREAD_JOIN_TIMEOUT_SECONDS = 1
APPROVAL_TIMEOUT_SECONDS = 300
APPROVAL_SUMMARY_TEXT_LIMIT = 180
APPROVAL_SUMMARY_ELLIPSIS = "..."
DEFAULT_CARD_LIMIT = 10
MIN_CARD_LIMIT = 1
MAX_CARD_LIMIT = 50
MERGE_TOOL_NAME = "merge_qa_cards"
AUTH_COOKIE_NAME = "pka_session"


class ChatAgent(Protocol):
    def run(self, user_input: str) -> str: ...


class CardTools(Protocol):
    def list_recent_cards(self, arguments: dict[str, Any]) -> dict[str, Any]: ...

    def search_qa_cards(self, arguments: dict[str, Any]) -> dict[str, Any]: ...

    def read_qa_card(self, arguments: dict[str, Any]) -> dict[str, Any]: ...


class AuthServiceDependency(Protocol):
    def request_login_code(self, email: str) -> Any: ...

    def verify_login_code(self, email: str, code: str) -> Any: ...

    def authenticate_session_token(self, session_token: str) -> Any: ...

    def revoke_session_token(self, session_token: str) -> bool: ...


class EmailSenderDependency(Protocol):
    def send_login_code(self, to_email: str, code: str, expires_minutes: int) -> None: ...


class SessionRepositoryDependency(Protocol):
    def create_session(self, user_id: str, *, session_id: str, title: str | None = None) -> Any: ...

    def list_sessions(self, user_id: str) -> list[Any]: ...

    def rename_session(self, user_id: str, session_id: str, title: str) -> Any | None: ...

    def load_messages(self, user_id: str, session_id: str) -> list[dict[str, Any]]: ...


class AuthenticatedSessionDependency(Protocol):
    user_id: str
    email: str
    llm_provider_user_id: str
    session_id: str
    expires_at: datetime


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class AuthEmailRequest(BaseModel):
    email: str


class AuthVerifyCodeRequest(BaseModel):
    email: str
    code: str


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
    def __init__(
        self,
        *,
        session_id: str,
        agent: ChatAgent | None,
        events: list[dict[str, Any]],
        event_logger: AgentEventJsonlLogger | None = None,
        close_callback: Callable[[], None] | None = None,
    ):
        self.session_id = session_id
        self.agent = agent
        self.events = events
        self.event_logger = event_logger
        self.close_callback = close_callback
        self.lock = threading.Lock()
        self.active_event_queue: queue.Queue[dict[str, Any] | object] | None = None
        self.active_event_queue_lock = threading.Lock()

    def collect_event(self, event: AgentEvent) -> None:
        event_dict = event.to_log_dict()
        self.publish_event(event_dict, log_event=event)

    def publish_event(self, event: dict[str, Any], log_event: AgentEvent | None = None) -> bool:
        """Publish a Web runtime event to audit storage and the active SSE stream."""

        if event.get("event_type") != "answer_delta":
            self.events.append(event)
            if self.event_logger is not None:
                self.event_logger.write(log_event or _agent_event_from_dict(event))
        return self.put_event(event)

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
    auth_service: AuthServiceDependency | None = None,
    email_sender: EmailSenderDependency | None = None,
    user_tool_factory: CloudUserToolFactory | None = None,
    cloud_session_repository: SessionRepositoryDependency | None = None,
    event_logger: AgentEventJsonlLogger | None = None,
) -> FastAPI:
    events: list[dict[str, Any]] = []
    needs_config = agent is None or (tools is None and user_tool_factory is None)
    resolved_config = config or (load_config() if needs_config else None)
    runners: dict[tuple[str | None, str], WebSessionRunner] = {}
    runners_lock = threading.Lock()
    approval_manager = WebApprovalManager(timeout_seconds=APPROVAL_TIMEOUT_SECONDS)
    workspace_root = Path.cwd()

    def request_web_approval(runner: WebSessionRunner, request: ApprovalRequest) -> bool:
        return approval_manager.request_approval(
            session_id=runner.session_id,
            request=request,
            emit_event=runner.publish_event,
        )

    def make_approval_callback(runner: WebSessionRunner) -> Callable[[ApprovalRequest], bool]:
        return lambda request: request_web_approval(runner, request)

    def authenticate_business_session(
        pka_session: str | None,
    ) -> AuthenticatedSessionDependency | dict[str, Any] | None:
        if auth_service is None:
            return None
        if not pka_session:
            return _business_authentication_error()
        try:
            result = auth_service.authenticate_session_token(pka_session)
        except Exception:
            return _business_authentication_error()
        if not getattr(result, "ok", False):
            return _business_authentication_error()
        return result

    def get_runner(
        session_id: str,
        auth_session: AuthenticatedSessionDependency | None = None,
    ) -> WebSessionRunner:
        safe_session_id = validate_session_id(session_id)
        runner_key = (_authenticated_user_id(auth_session), safe_session_id)
        with runners_lock:
            if runner_key in runners:
                return runners[runner_key]
            if agent is not None:
                runner = WebSessionRunner(
                    session_id=safe_session_id,
                    agent=agent,
                    events=events,
                    event_logger=event_logger,
                )
            else:
                placeholder = WebSessionRunner(
                    session_id=safe_session_id,
                    agent=None,
                    events=events,
                    event_logger=event_logger,
                )
                cloud_tools = None
                persistent_connection = None
                if user_tool_factory is not None and auth_session is not None:
                    cloud_tools, persistent_connection = user_tool_factory.create_persistent_tools(auth_session.user_id)
                component_kwargs: dict[str, Any] = {
                    "event_sink": placeholder.collect_event,
                    "approval_callback": make_approval_callback(placeholder),
                    "session_id": safe_session_id,
                }
                if cloud_tools is not None and auth_session is not None:
                    session_repository = PostgresConversationSessionRepository(
                        persistent_connection,
                        auth_session.user_id,
                    )
                    component_kwargs.update(
                        {
                            "qa_store": cloud_tools.tools.store,
                            "todo_store": cloud_tools.todo_tools.store,
                            "llm_provider_user_id": auth_session.llm_provider_user_id,
                            "enable_semantic_index": False,
                            "transcript": PostgresConversationTranscriptAdapter(
                                session_repository,
                                safe_session_id,
                            ),
                            "metadata_store": PostgresSessionMetadataAdapter(
                                session_repository,
                                safe_session_id,
                                model=resolved_config.deepseek_model,
                            ),
                            "context_compactor": InMemoryToolResultCompactor(),
                            "memory_index_store": cloud_tools.memory_index_store,
                            "memory_store": cloud_tools.memory_store,
                            "runtime_context_compactor_factory": (
                                lambda summarizer, repository=session_repository: PostgresRuntimeContextCompactor(
                                    repository,
                                    safe_session_id,
                                    summarizer=summarizer,
                                )
                            ),
                        }
                    )
                components = create_agent_components(resolved_config, **component_kwargs)
                placeholder.agent = components.agent
                if persistent_connection is not None:
                    placeholder.close_callback = (
                        lambda connection=persistent_connection: user_tool_factory.close_persistent_tools(connection)
                    )
                runner = placeholder
            runners[runner_key] = runner
            return runner

    def get_card_tools(auth_session: AuthenticatedSessionDependency | None) -> CardTools:
        if user_tool_factory is not None and auth_session is not None:
            raise RuntimeError("cloud card tools must be opened with call_card_tools")
        if tools is None:
            raise RuntimeError("card tools are not configured")
        return tools

    def call_card_tools(
        auth_session: AuthenticatedSessionDependency | None,
        callback: Callable[[CardTools], dict[str, Any]],
    ) -> dict[str, Any]:
        if user_tool_factory is not None and auth_session is not None:
            with user_tool_factory.open_tools(auth_session.user_id) as scoped_tools:
                return callback(scoped_tools.tools)
        return callback(get_card_tools(auth_session))

    def use_cloud_session_repository(auth_session: AuthenticatedSessionDependency | None) -> bool:
        return cloud_session_repository is not None and auth_session is not None

    if tools is None and user_tool_factory is None:
        tools = create_agent_components(
            resolved_config,
            approval_callback=default_approval_callback,
            session_id="default",
        ).tools

    app = FastAPI(title="Personal Knowledge Agent")
    app.state.agent_events = events
    app.state.approval_manager = approval_manager
    app.state.event_logger = event_logger

    @app.on_event("shutdown")
    def close_runners() -> None:
        with runners_lock:
            callbacks = [runner.close_callback for runner in runners.values() if runner.close_callback is not None]
            runners.clear()
        for callback in callbacks:
            callback()

    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True}

    @app.post("/api/auth/request-code")
    def request_login_code(request: AuthEmailRequest) -> dict[str, Any]:
        if auth_service is None or email_sender is None:
            return _error("auth_not_configured", "authentication is not configured")
        try:
            result = auth_service.request_login_code(request.email)
            if not getattr(result, "ok", False):
                return _auth_failure_payload(result)
            expires_minutes = _expires_minutes(result.expires_at)
            email_sender.send_login_code(result.email, result.plaintext_code, expires_minutes)
            return {"ok": True, "email": result.email}
        except Exception:
            return _error("auth_request_error", "login code request failed")

    @app.post("/api/auth/verify-code")
    def verify_login_code(request: AuthVerifyCodeRequest, response: Response) -> dict[str, Any]:
        if auth_service is None:
            return _error("auth_not_configured", "authentication is not configured")
        try:
            result = auth_service.verify_login_code(request.email, request.code)
            if not getattr(result, "ok", False):
                return _auth_failure_payload(result)
            response.set_cookie(
                AUTH_COOKIE_NAME,
                result.session_token,
                max_age=_cookie_max_age(result.expires_at),
                httponly=True,
                samesite="lax",
                path="/",
            )
            return {"ok": True, "user": _verified_user_payload(result)}
        except Exception:
            return _error("auth_verify_error", "login code verification failed")

    @app.get("/api/auth/me")
    def read_current_user(pka_session: str | None = Cookie(default=None)) -> dict[str, Any]:
        if auth_service is None:
            return _error("auth_not_configured", "authentication is not configured")
        if not pka_session:
            return _error("not_authenticated", "authentication session is missing")
        try:
            result = auth_service.authenticate_session_token(pka_session)
            if not getattr(result, "ok", False):
                return _auth_failure_payload(result)
            return {"ok": True, "user": _authenticated_user_payload(result)}
        except Exception:
            return _error("auth_me_error", "authentication lookup failed")

    @app.post("/api/auth/logout")
    def logout(response: Response, pka_session: str | None = Cookie(default=None)) -> dict[str, Any]:
        if auth_service is None:
            return _error("auth_not_configured", "authentication is not configured")
        try:
            if pka_session:
                auth_service.revoke_session_token(pka_session)
            response.delete_cookie(AUTH_COOKIE_NAME, path="/", samesite="lax")
            return {"ok": True}
        except Exception:
            response.delete_cookie(AUTH_COOKIE_NAME, path="/", samesite="lax")
            return _error("auth_logout_error", "logout failed")

    @app.post("/api/approvals/{approval_id}")
    def resolve_approval(
        approval_id: str,
        request: ApprovalDecisionRequest,
        pka_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        auth_session = authenticate_business_session(pka_session)
        if _is_auth_error(auth_session):
            return auth_session
        return approval_manager.resolve(approval_id, request.decision)

    @app.post("/api/sessions")
    def create_session(pka_session: str | None = Cookie(default=None)) -> dict[str, Any]:
        auth_session = authenticate_business_session(pka_session)
        if _is_auth_error(auth_session):
            return auth_session
        session_id = f"session_{uuid.uuid4().hex[:SESSION_ID_SUFFIX_CHARS]}"
        if use_cloud_session_repository(auth_session):
            record = cloud_session_repository.create_session(auth_session.user_id, session_id=session_id)
            return {"ok": True, "session": _cloud_session_payload(record)}
        metadata = ConversationSessionMetadataRepository(
            workspace_root,
            session_id=session_id,
        ).load_or_create()
        return {"ok": True, "session": _metadata_payload(metadata)}

    @app.get("/api/sessions")
    def list_sessions(pka_session: str | None = Cookie(default=None)) -> dict[str, Any]:
        auth_session = authenticate_business_session(pka_session)
        if _is_auth_error(auth_session):
            return auth_session
        if use_cloud_session_repository(auth_session):
            sessions = cloud_session_repository.list_sessions(auth_session.user_id)
            return {"ok": True, "sessions": [_cloud_session_payload(session) for session in sessions]}
        sessions = ConversationSessionMetadataRepository(workspace_root).list_sessions()
        return {"ok": True, "sessions": [_metadata_payload(metadata) for metadata in sessions]}

    @app.patch("/api/sessions/{session_id}")
    def rename_session(
        session_id: str,
        request: RenameSessionRequest,
        pka_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        auth_session = authenticate_business_session(pka_session)
        if _is_auth_error(auth_session):
            return auth_session
        try:
            if use_cloud_session_repository(auth_session):
                record = cloud_session_repository.rename_session(auth_session.user_id, session_id, request.title)
                if record is None:
                    return _error("session_not_found", "session not found")
                return {"ok": True, "session": _cloud_session_payload(record)}
            metadata = ConversationSessionMetadataRepository(
                workspace_root,
                session_id=session_id,
            ).rename_session(request.title)
            return {"ok": True, "session": _metadata_payload(metadata)}
        except Exception as exc:
            return _error("session_rename_error", str(exc))

    @app.get("/api/sessions/{session_id}/messages")
    def read_session_messages(
        session_id: str,
        pka_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        auth_session = authenticate_business_session(pka_session)
        if _is_auth_error(auth_session):
            return auth_session
        try:
            if use_cloud_session_repository(auth_session):
                messages = cloud_session_repository.load_messages(auth_session.user_id, session_id)
                return {"ok": True, "messages": _cloud_display_messages(messages)}
            transcript = ConversationTranscriptRepository(workspace_root, session_id=session_id)
            return {"ok": True, "messages": transcript.load_display_messages()}
        except Exception as exc:
            return _error("session_read_error", str(exc))

    @app.post("/api/chat/stream")
    def chat_stream(
        request: ChatRequest,
        pka_session: str | None = Cookie(default=None),
    ) -> StreamingResponse:
        message = request.message.strip()
        session_id = request.session_id or "default"
        event_queue: queue.Queue[dict[str, Any] | object] = queue.Queue()
        done = object()

        def run_agent() -> None:
            auth_session = authenticate_business_session(pka_session)
            if _is_auth_error(auth_session):
                event_queue.put(_event_error(auth_session["error_code"], auth_session["message"]))
                event_queue.put(done)
                return
            if not message:
                event_queue.put(_event_error("invalid_input", "message must be a non-empty string"))
                event_queue.put(done)
                return
            try:
                runner = get_runner(
                    session_id,
                    auth_session if auth_session is not None else None,
                )
                if not runner.lock.acquire(blocking=False):
                    event_queue.put(_event_error("session_busy", "current session is already running"))
                    return
                try:
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
                finally:
                    runner.lock.release()
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
        pka_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        auth_session = authenticate_business_session(pka_session)
        if _is_auth_error(auth_session):
            return auth_session
        try:
            return call_card_tools(
                auth_session if auth_session is not None else None,
                lambda card_tools: card_tools.list_recent_cards({"limit": limit}),
            )
        except Exception as exc:
            return _error("card_read_error", str(exc))

    @app.get("/api/cards/search")
    def search_cards(
        q: str = Query(default="", alias="q"),
        limit: int = Query(default=DEFAULT_CARD_LIMIT, ge=MIN_CARD_LIMIT, le=MAX_CARD_LIMIT),
        pka_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        auth_session = authenticate_business_session(pka_session)
        if _is_auth_error(auth_session):
            return auth_session
        query = q.strip()
        if not query:
            return _error("invalid_input", "q must be a non-empty string")
        try:
            return call_card_tools(
                auth_session if auth_session is not None else None,
                lambda card_tools: card_tools.search_qa_cards({"query": query, "limit": limit}),
            )
        except Exception as exc:
            return _error("card_search_error", str(exc))

    @app.get("/api/cards/{card_id}")
    def read_card(
        card_id: str,
        pka_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        auth_session = authenticate_business_session(pka_session)
        if _is_auth_error(auth_session):
            return auth_session
        try:
            return call_card_tools(
                auth_session if auth_session is not None else None,
                lambda card_tools: card_tools.read_qa_card({"card_id": card_id}),
            )
        except Exception as exc:
            return _error("card_read_error", str(exc))

    return app


def _error(error_code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error_code": error_code, "message": message}


def _business_authentication_error() -> dict[str, Any]:
    return _error("not_authenticated", "authentication is required")


def _is_auth_error(value: Any) -> bool:
    return isinstance(value, dict) and value.get("ok") is False


def _authenticated_user_id(auth_session: AuthenticatedSessionDependency | None) -> str | None:
    if auth_session is None:
        return None
    return auth_session.user_id


def _auth_failure_payload(result: Any) -> dict[str, Any]:
    return _error(str(result.error_code), str(result.message))


def _verified_user_payload(result: Any) -> dict[str, Any]:
    return {
        "user_id": result.user_id,
        "email": result.email,
        "expires_at": result.expires_at.isoformat(),
    }


def _authenticated_user_payload(result: Any) -> dict[str, Any]:
    return {
        "user_id": result.user_id,
        "email": result.email,
        "session_id": result.session_id,
        "expires_at": result.expires_at.isoformat(),
    }


def _expires_minutes(expires_at: datetime) -> int:
    return max(1, math.ceil((_ensure_aware_utc(expires_at) - datetime.now(UTC)).total_seconds() / 60))


def _cookie_max_age(expires_at: datetime) -> int:
    return max(0, int((_ensure_aware_utc(expires_at) - datetime.now(UTC)).total_seconds()))


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _metadata_payload(metadata: SessionMetadata) -> dict[str, Any]:
    return asdict(metadata)


def _cloud_session_payload(record: Any) -> dict[str, Any]:
    session_id = str(_record_value(record, "session_id", ""))
    created_at = str(_record_value(record, "created_at", ""))
    updated_at = str(_record_value(record, "updated_at", ""))
    title = _record_value(record, "title", None)
    return _metadata_payload(
        SessionMetadata(
            session_id=session_id,
            created_at=created_at,
            updated_at=updated_at,
            cwd="",
            model="",
            transcript_path="",
            summary_path="",
            artifacts_dir="",
            title=title if isinstance(title, str) and title else "新会话",
            title_source="user" if isinstance(title, str) and title else "auto",
        )
    )


def _cloud_display_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    display_messages: list[dict[str, Any]] = []
    for index, message in enumerate(messages, start=1):
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        if role == "assistant" and (message.get("tool_calls") or message.get("tool_call_id")):
            continue
        display_messages.append(
            {
                "role": role,
                "content": content,
                "created_at": str(message.get("created_at", "")),
                "event_id": index,
            }
        )
    return display_messages


def _record_value(record: Any, key: str, default: Any) -> Any:
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def _event_error(error_code: str, message: str) -> dict[str, Any]:
    return {
        "run_id": new_run_id(),
        "event_type": "error",
        "error_code": error_code,
        "message": message,
    }


def _agent_event_from_dict(event: dict[str, Any]) -> AgentEvent:
    """Convert a Web-only event dict into the shared AgentEvent log shape."""

    payload = {
        key: value
        for key, value in event.items()
        if key not in {"run_id", "event_type", "timestamp"}
    }
    return AgentEvent(
        run_id=str(event.get("run_id") or new_run_id()),
        event_type=str(event.get("event_type") or "unknown"),
        payload=payload,
        timestamp=str(event["timestamp"]) if event.get("timestamp") else datetime.now(UTC).isoformat(),
    )


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
    if request.tool_name == MERGE_TOOL_NAME:
        card_ids = [str(card_id) for card_id in arguments.get("card_ids", [])]
        question = str(arguments.get("question") or "")
        category = str(arguments.get("category") or "")
        keywords = arguments.get("keywords") or []
        preview = _merge_preview(question=question, category=category, keywords=keywords)
        return {
            "title": "合并知识卡片",
            "tool_name": request.tool_name,
            "tool_label": "合并知识卡片",
            "target_label": "原卡片",
            "target": _truncate_summary_text(", ".join(card_ids)),
            "changes": ["创建 1 张新卡片", f"删除 {len(card_ids)} 张原卡片"],
            "preview": _truncate_summary_text(preview),
            "risk": "将创建新卡片并物理删除原卡片。",
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


def _merge_preview(*, question: str, category: str, keywords: Any) -> str:
    """Build a safe merge approval preview without including the full answer."""

    keyword_text = ", ".join(str(item) for item in keywords) if isinstance(keywords, list) else str(keywords)
    parts = []
    if question:
        parts.append(f"合并后问题：{question}")
    if category:
        parts.append(f"分类：{category}")
    if keyword_text:
        parts.append(f"关键词：{keyword_text}")
    return "；".join(parts)


def _truncate_summary_text(value: str, limit: int = APPROVAL_SUMMARY_TEXT_LIMIT) -> str:
    """Truncate approval summary text, including the ellipsis in the limit."""

    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - len(APPROVAL_SUMMARY_ELLIPSIS)]}{APPROVAL_SUMMARY_ELLIPSIS}"
