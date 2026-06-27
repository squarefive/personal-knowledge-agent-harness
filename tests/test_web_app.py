import json
import queue
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from personal_knowledge_agent.agent_bootstrap import AgentConfig
from personal_knowledge_agent.agent_runtime import AgentEvent
from personal_knowledge_agent.llm_clients import LLMResponse
from personal_knowledge_agent.tool_runtime import ApprovalRequest
from personal_knowledge_agent.apps.web import create_web_app
from personal_knowledge_agent.apps.web.cloud_dependencies import CloudUserToolFactory, CloudUserTools
from personal_knowledge_agent.apps.web.web_app import WebApprovalManager


LONG_MERGE_ANSWER = "完整答案" * 120
MERGE_ARGUMENTS = {
    "card_ids": ["qa_1", "qa_2"],
    "question": "合并后的问题",
    "answer": LONG_MERGE_ANSWER,
    "summary": "合并后的摘要",
    "keywords": ["合并", "权限"],
    "category": "知识整理",
}


class FakeAgent:
    def __init__(self, fail=False, answer_prefix="reply"):
        self.fail = fail
        self.answer_prefix = answer_prefix
        self.inputs = []

    def run(self, user_input):
        self.inputs.append(user_input)
        if self.fail:
            raise RuntimeError("temporary failure")
        return f"{self.answer_prefix}: {user_input}"


class BlockingAgent:
    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def run(self, user_input):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.05)
        with self.lock:
            self.active -= 1
        return f"reply: {user_input}"


class ControlledBlockingAgent(BlockingAgent):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def run(self, user_input):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        self.started.set()
        self.release.wait(timeout=3)
        with self.lock:
            self.active -= 1
        return f"reply: {user_input}"


class FakeTools:
    def __init__(self, user_id=None):
        self.user_id = user_id
        self.store = SimpleNamespace(user_id=user_id)

    def list_recent_cards(self, arguments):
        return {
            "ok": True,
            "cards": [
                {
                    "card_id": "qa_1",
                    "user_id": self.user_id,
                    "question": "问题一",
                    "summary": "摘要一",
                    "keywords": ["本地"],
                    "category": "Agent 开发",
                    "source_type": "manual_qa",
                    "created_at": "2026-06-02T00:00:00Z",
                }
            ],
        }

    def search_qa_cards(self, arguments):
        return {
            "ok": True,
            "cards": [
                {
                    "card_id": "qa_1",
                    "user_id": self.user_id,
                    "question": arguments["query"],
                    "summary": "摘要一",
                    "answer_snippet": "答案片段",
                    "score": 4,
                    "category": "Agent 开发",
                    "source_type": "manual_qa",
                    "created_at": "2026-06-02T00:00:00Z",
                }
            ],
        }

    def read_qa_card(self, arguments):
        if arguments["card_id"] == "missing":
            return {"ok": False, "error_code": "not_found", "message": "card not found"}
        return {
            "ok": True,
            "card": {
                "card_id": arguments["card_id"],
                "user_id": self.user_id,
                "question": "问题一",
                "answer": "答案一",
                "summary": "摘要一",
                "keywords": ["本地"],
                "category": "Agent 开发",
                "source_type": "manual_qa",
                "created_at": "2026-06-02T00:00:00Z",
                "updated_at": "2026-06-02T00:00:00Z",
            },
        }


class FakeEventLogger:
    def __init__(self):
        self.events = []

    def write(self, event):
        self.events.append(event.to_log_dict())

    def close(self):
        return None


class FakeEmailSender:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent_codes = []

    def send_login_code(self, to_email, code, expires_minutes):
        if self.fail:
            raise RuntimeError("smtp unavailable")
        self.sent_codes.append(
            {
                "to_email": to_email,
                "code": code,
                "expires_minutes": expires_minutes,
            }
        )


class FakeAuthService:
    allowed_email = "1033795760@qq.com"

    def __init__(self, *, fail_request=False, user_id="usr_test_1", llm_provider_user_id="llm_test_1"):
        self.fail_request = fail_request
        self.user_id = user_id
        self.llm_provider_user_id = llm_provider_user_id
        self.requested_emails = []
        self.verified_codes = []
        self.authenticated_tokens = []
        self.revoked_tokens = []
        self.last_seen_updates = []
        self.expires_at = datetime.now(UTC) + timedelta(days=30)

    def request_login_code(self, email):
        normalized_email = email.strip().lower()
        self.requested_emails.append(normalized_email)
        if self.fail_request or normalized_email != self.allowed_email:
            return SimpleNamespace(
                ok=False,
                error_code="email_not_allowed",
                message="email is not allowed to log in",
                email=normalized_email,
            )
        return SimpleNamespace(
            ok=True,
            email=normalized_email,
            plaintext_code="123456",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )

    def verify_login_code(self, email, code):
        normalized_email = email.strip().lower()
        stripped_code = code.strip()
        self.verified_codes.append((normalized_email, stripped_code))
        if normalized_email != self.allowed_email or stripped_code != "123456":
            return SimpleNamespace(
                ok=False,
                error_code="invalid_login_code",
                message="login code is invalid",
                email=normalized_email,
            )
        return SimpleNamespace(
            ok=True,
            email=normalized_email,
            user_id=self.user_id,
            llm_provider_user_id=self.llm_provider_user_id,
            session_token="plain-session-token",
            expires_at=self.expires_at,
        )

    def authenticate_session_token(self, session_token):
        self.authenticated_tokens.append(session_token)
        if session_token != "plain-session-token":
            return SimpleNamespace(ok=False, error_code="auth_session_not_found", message="auth session not found")
        self.last_seen_updates.append(("sess_test_1", datetime.now(UTC)))
        return SimpleNamespace(
            ok=True,
            user_id=self.user_id,
            email=self.allowed_email,
            llm_provider_user_id=self.llm_provider_user_id,
            session_id="sess_test_1",
            expires_at=self.expires_at,
        )

    def revoke_session_token(self, session_token):
        self.revoked_tokens.append(session_token)
        return session_token == "plain-session-token"


class FakeTodoTools:
    def __init__(self, user_id):
        self.store = SimpleNamespace(user_id=user_id)


class FakeCloudUserToolFactory:
    def __init__(self):
        self.opened_user_ids = []
        self.persistent_user_ids = []
        self.closed_connections = []

    def open_tools(self, user_id):
        factory = self

        class ToolContext:
            def __enter__(self):
                factory.opened_user_ids.append(user_id)
                return CloudUserTools(tools=FakeTools(user_id=user_id), todo_tools=FakeTodoTools(user_id))

            def __exit__(self, exc_type, exc, traceback):
                return False

        return ToolContext()

    def create_persistent_tools(self, user_id):
        self.persistent_user_ids.append(user_id)
        connection = SimpleNamespace(user_id=user_id)
        return CloudUserTools(tools=FakeTools(user_id=user_id), todo_tools=FakeTodoTools(user_id)), connection

    def close_persistent_tools(self, connection):
        self.closed_connections.append(connection)


class FakeCloudSessionRepository:
    def __init__(self):
        self.created_user_ids = []
        self.listed_user_ids = []
        self.renamed_calls = []
        self.loaded_calls = []
        self.sessions = {}
        self.messages = {}

    def create_session(self, user_id, *, session_id, title=None):
        self.created_user_ids.append(user_id)
        record = SimpleNamespace(
            session_id=session_id,
            title=title,
            summary=None,
            status="idle",
            current_run_id=None,
            created_at="2026-06-27T01:00:00+00:00",
            updated_at="2026-06-27T01:00:00+00:00",
        )
        self.sessions[(user_id, session_id)] = record
        return record

    def list_sessions(self, user_id):
        self.listed_user_ids.append(user_id)
        return [record for (record_user_id, _), record in self.sessions.items() if record_user_id == user_id]

    def rename_session(self, user_id, session_id, title):
        self.renamed_calls.append((user_id, session_id, title))
        record = self.sessions.get((user_id, session_id))
        if record is None:
            return None
        updated = SimpleNamespace(
            session_id=record.session_id,
            title=title,
            summary=record.summary,
            status=record.status,
            current_run_id=record.current_run_id,
            created_at=record.created_at,
            updated_at="2026-06-27T01:01:00+00:00",
        )
        self.sessions[(user_id, session_id)] = updated
        return updated

    def load_messages(self, user_id, session_id):
        self.loaded_calls.append((user_id, session_id))
        return self.messages.get(
            (user_id, session_id),
            [
                {"role": "user", "content": "hello", "created_at": "2026-06-27T01:02:00+00:00"},
                {"role": "assistant", "content": "world", "created_at": "2026-06-27T01:03:00+00:00"},
                {"role": "tool", "content": "hidden"},
            ],
        )


class MultiUserAuthService(FakeAuthService):
    def authenticate_session_token(self, session_token):
        self.authenticated_tokens.append(session_token)
        if session_token == "token-a":
            return SimpleNamespace(
                ok=True,
                user_id="usr_a",
                email=self.allowed_email,
                llm_provider_user_id="llm_a",
                session_id="sess_a",
                expires_at=self.expires_at,
            )
        if session_token == "token-b":
            return SimpleNamespace(
                ok=True,
                user_id="usr_b",
                email=self.allowed_email,
                llm_provider_user_id="llm_b",
                session_id="sess_b",
                expires_at=self.expires_at,
            )
        return SimpleNamespace(ok=False, error_code="auth_session_not_found", message="auth session not found")


def make_client(agent=None, tools=None):
    app = create_web_app(agent=agent or FakeAgent(), tools=tools or FakeTools())
    return TestClient(app)


def make_auth_client(agent=None, tools=None):
    auth_service = FakeAuthService()
    app = create_web_app(
        agent=agent or FakeAgent(),
        tools=tools or FakeTools(),
        auth_service=auth_service,
        email_sender=FakeEmailSender(),
    )
    client = TestClient(app)
    return client, auth_service


def read_sse_events(response):
    events = []
    for block in response.text.strip().split("\n\n"):
        if not block:
            continue
        line = next(line for line in block.splitlines() if line.startswith("data:"))
        import json

        events.append(json.loads(line.removeprefix("data:").strip()))
    return events


def start_pending_approval(manager, request):
    events = queue.Queue()
    result = {}

    def emit_event(event):
        events.put(event)
        return True

    def wait_for_approval():
        result["approved"] = manager.request_approval(
            session_id="session_1",
            request=request,
            emit_event=emit_event,
        )

    thread = threading.Thread(target=wait_for_approval)
    thread.start()
    return thread, events, result


def next_approval_event(events, event_type=None, timeout=3):
    try:
        event = events.get(timeout=timeout)
    except queue.Empty as exc:
        raise AssertionError("Timed out waiting for SSE event") from exc
    if event_type is not None:
        assert event["event_type"] == event_type
    return event


def assert_approval_finished(thread):
    thread.join(timeout=3)
    assert not thread.is_alive()


def approval_request(tool_name="delete_qa_card", arguments=None):
    return ApprovalRequest(
        tool_name=tool_name,
        arguments=arguments or {"card_id": "qa_1"},
        reason="danger",
    )


def test_auth_request_code_sends_email_without_returning_plaintext_code():
    auth_service = FakeAuthService()
    email_sender = FakeEmailSender()
    app = create_web_app(agent=FakeAgent(), tools=FakeTools(), auth_service=auth_service, email_sender=email_sender)
    client = TestClient(app)

    response = client.post("/api/auth/request-code", json={"email": "  1033795760@QQ.COM  "})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "email": "1033795760@qq.com"}
    assert email_sender.sent_codes == [
        {
            "to_email": "1033795760@qq.com",
            "code": "123456",
            "expires_minutes": 10,
        }
    ]
    assert "123456" not in response.text


def test_auth_request_code_does_not_send_email_when_auth_rejects():
    auth_service = FakeAuthService()
    email_sender = FakeEmailSender()
    app = create_web_app(agent=FakeAgent(), tools=FakeTools(), auth_service=auth_service, email_sender=email_sender)
    client = TestClient(app)

    response = client.post("/api/auth/request-code", json={"email": "other@example.com"})

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error_code"] == "email_not_allowed"
    assert email_sender.sent_codes == []


def test_auth_verify_code_sets_http_only_cookie_without_returning_token():
    auth_service = FakeAuthService()
    app = create_web_app(
        agent=FakeAgent(),
        tools=FakeTools(),
        auth_service=auth_service,
        email_sender=FakeEmailSender(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/auth/verify-code",
        json={"email": "1033795760@qq.com", "code": "123456"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["user"]["email"] == "1033795760@qq.com"
    assert "session_token" not in body
    assert "llm_provider_user_id" not in body["user"]
    assert "plain-session-token" not in response.text
    cookie_header = response.headers["set-cookie"]
    assert "pka_session=plain-session-token" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header
    assert "Path=/" in cookie_header
    assert "Max-Age=" in cookie_header


def test_auth_me_uses_cookie_and_returns_user_with_last_seen_update():
    auth_service = FakeAuthService()
    app = create_web_app(
        agent=FakeAgent(),
        tools=FakeTools(),
        auth_service=auth_service,
        email_sender=FakeEmailSender(),
    )
    client = TestClient(app)
    client.cookies.set("pka_session", "plain-session-token")

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["user"]["email"] == "1033795760@qq.com"
    assert "llm_provider_user_id" not in response.json()["user"]
    assert auth_service.authenticated_tokens == ["plain-session-token"]
    assert auth_service.last_seen_updates[0][0] == "sess_test_1"


def test_auth_logout_revokes_cookie_token_and_clears_cookie():
    auth_service = FakeAuthService()
    app = create_web_app(
        agent=FakeAgent(),
        tools=FakeTools(),
        auth_service=auth_service,
        email_sender=FakeEmailSender(),
    )
    client = TestClient(app)
    client.cookies.set("pka_session", "plain-session-token")

    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert auth_service.revoked_tokens == ["plain-session-token"]
    cookie_header = response.headers["set-cookie"]
    assert "pka_session=" in cookie_header
    assert "Max-Age=0" in cookie_header
    assert "Path=/" in cookie_header


def test_auth_endpoints_return_configuration_error_without_auth_service():
    client = make_client()

    request_response = client.post("/api/auth/request-code", json={"email": "1033795760@qq.com"})
    verify_response = client.post("/api/auth/verify-code", json={"email": "1033795760@qq.com", "code": "123456"})
    me_response = client.get("/api/auth/me")
    logout_response = client.post("/api/auth/logout")
    cards_response = client.get("/api/cards/recent")

    assert request_response.json()["error_code"] == "auth_not_configured"
    assert verify_response.json()["error_code"] == "auth_not_configured"
    assert me_response.json()["error_code"] == "auth_not_configured"
    assert logout_response.json()["error_code"] == "auth_not_configured"
    assert cards_response.json()["ok"] is True


def test_chat_stream_returns_agent_answer():
    agent = FakeAgent()
    client = make_client(agent=agent)

    response = client.post("/api/chat/stream", json={"message": "  你好  "})

    assert response.status_code == 200
    events = read_sse_events(response)
    assert events[-1]["event_type"] == "final_answer_generated"
    assert events[-1]["answer"] == "reply: 你好"
    assert agent.inputs == ["你好"]


def test_business_chat_stream_requires_authenticated_cookie_when_auth_service_is_configured():
    agent = FakeAgent()
    client, auth_service = make_auth_client(agent=agent)

    response = client.post("/api/chat/stream", json={"message": "你好"})

    assert response.status_code == 200
    events = read_sse_events(response)
    assert events[-1]["event_type"] == "error"
    assert events[-1]["error_code"] == "not_authenticated"
    assert agent.inputs == []
    assert auth_service.authenticated_tokens == []


def test_business_json_apis_require_authenticated_cookie_when_auth_service_is_configured():
    client, auth_service = make_auth_client()
    cases = [
        ("get", "/api/cards/recent", None),
        ("get", "/api/cards/search?q=本地", None),
        ("get", "/api/cards/qa_1", None),
        ("post", "/api/sessions", None),
        ("get", "/api/sessions", None),
        ("patch", "/api/sessions/session_1", {"title": "新标题"}),
        ("get", "/api/sessions/session_1/messages", None),
        ("post", "/api/approvals/approval_1", {"decision": "approve"}),
    ]

    for method, path, json_body in cases:
        response = getattr(client, method)(path, json=json_body) if json_body is not None else getattr(client, method)(path)
        assert response.status_code == 200
        assert response.json()["ok"] is False
        assert response.json()["error_code"] == "not_authenticated"
    assert auth_service.authenticated_tokens == []


def test_authenticated_business_apis_keep_existing_chat_cards_and_sessions_behavior(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agent = FakeAgent()
    client, auth_service = make_auth_client(agent=agent)
    client.cookies.set("pka_session", "plain-session-token")

    chat_response = client.post("/api/chat/stream", json={"message": "你好"})
    recent_response = client.get("/api/cards/recent")
    search_response = client.get("/api/cards/search?q=本地")
    card_response = client.get("/api/cards/qa_1")
    created_response = client.post("/api/sessions")
    listed_response = client.get("/api/sessions")
    session_id = created_response.json()["session"]["session_id"]
    renamed_response = client.patch(f"/api/sessions/{session_id}", json={"title": "新标题"})
    messages_response = client.get(f"/api/sessions/{session_id}/messages")

    assert read_sse_events(chat_response)[-1]["answer"] == "reply: 你好"
    assert recent_response.json()["cards"][0]["card_id"] == "qa_1"
    assert search_response.json()["cards"][0]["question"] == "本地"
    assert card_response.json()["card"]["card_id"] == "qa_1"
    assert created_response.json()["ok"] is True
    assert listed_response.json()["sessions"][0]["session_id"] == session_id
    assert renamed_response.json()["session"]["title"] == "新标题"
    assert messages_response.json()["messages"] == []
    assert agent.inputs == ["你好"]
    assert auth_service.authenticated_tokens == ["plain-session-token"] * 8


def test_authenticated_card_apis_use_current_user_bound_tools():
    auth_service = FakeAuthService(user_id="usr_cards", llm_provider_user_id="llm_cards")
    tool_factory = FakeCloudUserToolFactory()
    app = create_web_app(
        agent=FakeAgent(),
        auth_service=auth_service,
        email_sender=FakeEmailSender(),
        user_tool_factory=tool_factory,
    )
    client = TestClient(app)
    client.cookies.set("pka_session", "plain-session-token")

    recent_response = client.get("/api/cards/recent")
    search_response = client.get("/api/cards/search?q=本地")
    card_response = client.get("/api/cards/qa_1")

    assert recent_response.json()["cards"][0]["user_id"] == "usr_cards"
    assert search_response.json()["cards"][0]["user_id"] == "usr_cards"
    assert card_response.json()["card"]["user_id"] == "usr_cards"
    assert tool_factory.opened_user_ids == ["usr_cards", "usr_cards", "usr_cards"]


def test_authenticated_session_apis_use_cloud_repository_and_do_not_touch_local_sessions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    auth_service = FakeAuthService(user_id="usr_sessions", llm_provider_user_id="llm_sessions")
    session_repository = FakeCloudSessionRepository()
    app = create_web_app(
        agent=FakeAgent(),
        tools=FakeTools(),
        auth_service=auth_service,
        email_sender=FakeEmailSender(),
        cloud_session_repository=session_repository,
    )
    client = TestClient(app)
    client.cookies.set("pka_session", "plain-session-token")

    created_response = client.post("/api/sessions")
    session_id = created_response.json()["session"]["session_id"]
    listed_response = client.get("/api/sessions")
    renamed_response = client.patch(f"/api/sessions/{session_id}", json={"title": "云端标题"})
    messages_response = client.get(f"/api/sessions/{session_id}/messages")

    assert created_response.json()["ok"] is True
    assert listed_response.json()["sessions"][0]["session_id"] == session_id
    assert renamed_response.json()["session"]["title"] == "云端标题"
    assert messages_response.json()["messages"] == [
        {
            "role": "user",
            "content": "hello",
            "created_at": "2026-06-27T01:02:00+00:00",
            "event_id": 1,
        },
        {
            "role": "assistant",
            "content": "world",
            "created_at": "2026-06-27T01:03:00+00:00",
            "event_id": 2,
        },
    ]
    assert session_repository.created_user_ids == ["usr_sessions"]
    assert session_repository.listed_user_ids == ["usr_sessions"]
    assert session_repository.renamed_calls == [("usr_sessions", session_id, "云端标题")]
    assert session_repository.loaded_calls == [("usr_sessions", session_id)]
    assert not (tmp_path / ".sessions").exists()


def test_cloud_chat_runner_cache_is_scoped_by_user_and_passes_user_context(tmp_path, monkeypatch):
    import personal_knowledge_agent.apps.web.web_app as app_module

    monkeypatch.chdir(tmp_path)
    created_components = []

    def fake_create_agent_components(
        config,
        event_sink=None,
        approval_callback=None,
        session_id="default",
        qa_store=None,
        todo_store=None,
        llm_provider_user_id=None,
        semantic_index=None,
        enable_semantic_index=True,
        transcript=None,
        metadata_store=None,
        context_compactor=None,
        runtime_context_compactor=None,
        runtime_context_compactor_factory=None,
    ):
        created_components.append(
            {
                "session_id": session_id,
                "qa_user_id": qa_store.user_id,
                "todo_user_id": todo_store.user_id,
                "llm_provider_user_id": llm_provider_user_id,
                "enable_semantic_index": enable_semantic_index,
                "transcript": type(transcript).__name__,
                "metadata_store": type(metadata_store).__name__,
                "context_compactor": type(context_compactor).__name__,
                "has_runtime_context_compactor_factory": runtime_context_compactor_factory is not None,
            }
        )
        agent = FakeAgent(answer_prefix=f"reply-{qa_store.user_id}")
        return type("Components", (), {"agent": agent, "tools": FakeTools(user_id=qa_store.user_id)})()

    monkeypatch.setattr(app_module, "create_agent_components", fake_create_agent_components)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )
    tool_factory = FakeCloudUserToolFactory()
    app = create_web_app(
        config=config,
        auth_service=MultiUserAuthService(),
        email_sender=FakeEmailSender(),
        user_tool_factory=tool_factory,
    )
    client = TestClient(app)

    client.cookies.set("pka_session", "token-a")
    first_response = client.post("/api/chat/stream", json={"session_id": "shared", "message": "hello"})
    client.cookies.set("pka_session", "token-b")
    second_response = client.post("/api/chat/stream", json={"session_id": "shared", "message": "hello"})
    client.cookies.set("pka_session", "token-a")
    third_response = client.post("/api/chat/stream", json={"session_id": "shared", "message": "again"})

    assert read_sse_events(first_response)[-1]["answer"] == "reply-usr_a: hello"
    assert read_sse_events(second_response)[-1]["answer"] == "reply-usr_b: hello"
    assert read_sse_events(third_response)[-1]["answer"] == "reply-usr_a: again"
    assert created_components == [
        {
            "session_id": "shared",
            "qa_user_id": "usr_a",
            "todo_user_id": "usr_a",
            "llm_provider_user_id": "llm_a",
            "enable_semantic_index": False,
            "transcript": "PostgresConversationTranscriptAdapter",
            "metadata_store": "PostgresSessionMetadataAdapter",
            "context_compactor": "InMemoryToolResultCompactor",
            "has_runtime_context_compactor_factory": True,
        },
        {
            "session_id": "shared",
            "qa_user_id": "usr_b",
            "todo_user_id": "usr_b",
            "llm_provider_user_id": "llm_b",
            "enable_semantic_index": False,
            "transcript": "PostgresConversationTranscriptAdapter",
            "metadata_store": "PostgresSessionMetadataAdapter",
            "context_compactor": "InMemoryToolResultCompactor",
            "has_runtime_context_compactor_factory": True,
        },
    ]
    assert tool_factory.persistent_user_ids == ["usr_a", "usr_b"]


def test_authenticated_cloud_chat_stream_uses_postgres_session_runtime_without_local_sessions(tmp_path, monkeypatch):
    import personal_knowledge_agent.agent_bootstrap.agent_component_factory as factory_module

    class FakeLLM:
        def __init__(self, **kwargs):
            self.llm_provider_user_id = kwargs.get("llm_provider_user_id")

        def chat(self, *, messages, tools, system_prompt, on_text_delta=None):
            return LLMResponse(text="云端回复")

    class FakeCursor:
        def __init__(self, row=None, rows=None, rowcount=1):
            self._row = row
            self._rows = rows or []
            self.rowcount = rowcount

        def fetchone(self):
            return self._row

        def fetchall(self):
            return self._rows

    class FakeConnection:
        def __init__(self):
            self.executed = []
            self.messages = []
            self.sessions = {}
            self.commits = 0

        def execute(self, query, params=()):
            sql = " ".join(query.split())
            self.executed.append((sql, params))
            if "SELECT session_id, title, summary, status, current_run_id, created_at, updated_at" in sql:
                record = self.sessions.get((params[0], params[1]))
                return FakeCursor(row=record)
            if "INSERT INTO conversation_sessions" in sql:
                row = (
                    params[0],
                    params[2],
                    None,
                    "idle",
                    None,
                    datetime(2026, 6, 27, 1, 0, tzinfo=UTC),
                    datetime(2026, 6, 27, 1, 0, tzinfo=UTC),
                )
                self.sessions[(params[1], params[0])] = row
                return FakeCursor(row=row)
            if "SELECT message FROM conversation_messages" in sql:
                user_id, session_id = params[:2]
                rows = [
                    (message,)
                    for row_user, row_session, message in self.messages
                    if (row_user, row_session) == (user_id, session_id)
                ]
                return FakeCursor(rows=rows)
            if "SELECT COUNT(*) FROM conversation_messages" in sql:
                user_id, session_id = params
                count = sum(
                    1
                    for row_user, row_session, _message in self.messages
                    if (row_user, row_session) == (user_id, session_id)
                )
                return FakeCursor(row=(count,))
            if "SELECT COALESCE(MAX(sequence_no), 0) + 1 FROM conversation_messages" in sql:
                user_id, session_id = params
                count = sum(
                    1
                    for row_user, row_session, _message in self.messages
                    if (row_user, row_session) == (user_id, session_id)
                )
                return FakeCursor(row=(count + 1,))
            if "INSERT INTO conversation_messages" in sql:
                self.messages.append((params[0], params[1], params[4].obj))
                return FakeCursor()
            if "UPDATE conversation_sessions SET title" in sql:
                return FakeCursor(
                    row=(
                        params[2],
                        params[0],
                        None,
                        "idle",
                        None,
                        datetime(2026, 6, 27, 1, 0, tzinfo=UTC),
                        datetime(2026, 6, 27, 1, 1, tzinfo=UTC),
                    )
                )
            return FakeCursor(rowcount=1)

        def commit(self):
            self.commits += 1

    class FakePool:
        def __init__(self):
            self.connection = FakeConnection()
            self.put_connections = []

        def getconn(self):
            return self.connection

        def putconn(self, connection):
            self.put_connections.append(connection)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(factory_module, "DeepSeekChatClient", FakeLLM)
    pool = FakePool()
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )
    app = create_web_app(
        config=config,
        auth_service=FakeAuthService(user_id="usr_cloud_runtime", llm_provider_user_id="llm_cloud_runtime"),
        email_sender=FakeEmailSender(),
        user_tool_factory=CloudUserToolFactory(pool),
    )
    client = TestClient(app)
    client.cookies.set("pka_session", "plain-session-token")

    response = client.post("/api/chat/stream", json={"session_id": "cloud_chat", "message": "你好"})

    assert response.status_code == 200
    assert read_sse_events(response)[-1]["answer"] == "云端回复"
    assert [message for _user_id, _session_id, message in pool.connection.messages] == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "云端回复"},
    ]
    assert [(user_id, session_id) for user_id, session_id, _message in pool.connection.messages] == [
        ("usr_cloud_runtime", "cloud_chat"),
        ("usr_cloud_runtime", "cloud_chat"),
    ]
    assert not (tmp_path / ".sessions").exists()


def test_chat_route_is_removed():
    client = make_client()

    response = client.post("/api/chat", json={"message": "你好"})

    assert response.status_code == 404


def test_web_runtime_approves_pending_tool_permission(tmp_path, monkeypatch):
    app = create_web_app(agent=FakeAgent(), tools=FakeTools())
    client = TestClient(app)
    manager = app.state.approval_manager
    thread, events, result_holder = start_pending_approval(manager, approval_request())
    requested = next_approval_event(events, "permission_requested")

    assert requested["timeout_seconds"] == 300
    assert requested["summary"]["tool_name"] == "delete_qa_card"
    assert requested["summary"]["target"] == "qa_1"
    assert "arguments" not in requested

    result = client.post(
        f"/api/approvals/{requested['approval_id']}",
        json={"decision": "approve"},
    ).json()
    assert result["ok"] is True
    assert result["status"] == "approved"

    resolved = next_approval_event(events, "permission_resolved")
    assert_approval_finished(thread)

    assert resolved["status"] == "approved"
    assert result_holder["approved"] is True


def test_web_runtime_denies_pending_tool_permission(tmp_path, monkeypatch):
    app = create_web_app(agent=FakeAgent(), tools=FakeTools())
    client = TestClient(app)
    manager = app.state.approval_manager
    thread, events, result_holder = start_pending_approval(manager, approval_request())
    requested = next_approval_event(events, "permission_requested")

    result = client.post(
        f"/api/approvals/{requested['approval_id']}",
        json={"decision": "deny"},
    ).json()
    assert result["ok"] is True
    assert result["status"] == "denied"

    resolved = next_approval_event(events, "permission_resolved")
    assert_approval_finished(thread)

    assert resolved["status"] == "denied"
    assert result_holder["approved"] is False


def test_web_runtime_expires_pending_tool_permission():
    manager = WebApprovalManager(timeout_seconds=0.01)
    thread, events, result_holder = start_pending_approval(manager, approval_request())

    requested = next_approval_event(events, "permission_requested")
    resolved = next_approval_event(events, "permission_resolved")
    assert_approval_finished(thread)

    assert requested["timeout_seconds"] == 0.01
    assert resolved["status"] == "expired"
    assert result_holder["approved"] is False


def test_web_permission_summary_for_update_omits_full_arguments(tmp_path, monkeypatch):
    manager = WebApprovalManager(timeout_seconds=3)
    request = approval_request(
        tool_name="update_qa_card",
        arguments={
            "card_id": "qa_1",
            "question": "很长的问题" * 80,
            "summary": "新的摘要",
            "category": "权限机制",
        },
    )
    thread, events, _result_holder = start_pending_approval(manager, request)

    requested = next_approval_event(events, "permission_requested")
    manager.resolve(requested["approval_id"], "deny")
    next_approval_event(events, "permission_resolved")
    assert_approval_finished(thread)

    summary = requested["summary"]
    assert requested["event_type"] == "permission_requested"
    assert "arguments" not in requested
    assert summary["tool_name"] == "update_qa_card"
    assert summary["target"] == "qa_1"
    assert summary["changes"] == ["原始问题", "摘要", "分类"]
    assert len(summary["preview"]) <= 180
    assert summary["risk"] == "将覆盖当前卡片内容。"


def test_web_permission_summary_for_merge_omits_full_answer():
    manager = WebApprovalManager(timeout_seconds=3)
    request = approval_request(tool_name="merge_qa_cards", arguments=MERGE_ARGUMENTS)
    thread, events, _result_holder = start_pending_approval(manager, request)

    requested = next_approval_event(events, "permission_requested")
    manager.resolve(requested["approval_id"], "deny")
    next_approval_event(events, "permission_resolved")
    assert_approval_finished(thread)

    summary = requested["summary"]
    serialized_event = json.dumps(requested, ensure_ascii=False)
    assert "arguments" not in requested
    assert LONG_MERGE_ANSWER not in serialized_event
    assert summary["tool_name"] == "merge_qa_cards"
    assert summary["tool_label"] == "合并知识卡片"
    assert summary["target"] == "qa_1, qa_2"
    assert summary["changes"] == ["创建 1 张新卡片", "删除 2 张原卡片"]
    assert summary["risk"] == "将创建新卡片并物理删除原卡片。"


def test_chat_stream_publishes_and_logs_web_approval_events(tmp_path, monkeypatch):
    class ApprovalAgent:
        def __init__(self, approval_callback):
            self.approval_callback = approval_callback
            self.approved = None

        def run(self, user_input):
            self.approved = self.approval_callback(
                ApprovalRequest(
                    tool_name="merge_qa_cards",
                    arguments=MERGE_ARGUMENTS,
                    reason="合并卡片需要确认",
                )
            )
            return "已合并" if self.approved else "未合并"

    captured = {}

    def fake_create_agent_components(config, event_sink=None, approval_callback=None, session_id="default"):
        agent = ApprovalAgent(approval_callback)
        captured["agent"] = agent
        return type("Components", (), {"agent": agent, "tools": FakeTools()})()

    import personal_knowledge_agent.apps.web.web_app as app_module

    monkeypatch.setattr(app_module, "create_agent_components", fake_create_agent_components)
    event_logger = FakeEventLogger()
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )
    app = create_web_app(config=config, event_logger=event_logger)
    client = TestClient(app)
    result = {}

    def send_message():
        result["response"] = client.post("/api/chat/stream", json={"session_id": "chat_1", "message": "合并"})

    thread = threading.Thread(target=send_message)
    thread.start()

    requested = None
    deadline = time.time() + 3
    while time.time() < deadline:
        requested = next(
            (event for event in app.state.agent_events if event["event_type"] == "permission_requested"),
            None,
        )
        if requested is not None:
            break
        time.sleep(0.01)
    assert requested is not None
    assert requested["summary"]["tool_name"] == "merge_qa_cards"

    approval_response = client.post(
        f"/api/approvals/{requested['approval_id']}",
        json={"decision": "approve"},
    )
    assert approval_response.status_code == 200
    assert approval_response.json()["status"] == "approved"

    thread.join(timeout=3)
    assert not thread.is_alive()
    assert result["response"].status_code == 200

    events = read_sse_events(result["response"])
    event_types = [event["event_type"] for event in events]
    logged_types = [event["event_type"] for event in event_logger.events]
    serialized_log = json.dumps(event_logger.events, ensure_ascii=False)

    assert "permission_requested" in event_types
    assert "permission_resolved" in event_types
    assert "permission_requested" in logged_types
    assert "permission_resolved" in logged_types
    assert "arguments" not in next(event for event in event_logger.events if event["event_type"] == "permission_requested")
    assert LONG_MERGE_ANSWER not in serialized_log
    assert captured["agent"].approved is True


def test_chat_rejects_empty_message():
    client = make_client()

    response = client.post("/api/chat/stream", json={"message": " "})

    assert response.status_code == 200
    events = read_sse_events(response)
    assert events[-1]["event_type"] == "error"
    assert events[-1]["error_code"] == "invalid_input"


def test_chat_returns_structured_error_on_agent_failure():
    client = make_client(agent=FakeAgent(fail=True))

    response = client.post("/api/chat/stream", json={"message": "你好"})

    assert response.status_code == 200
    events = read_sse_events(response)
    assert events[-1]["event_type"] == "error"
    assert events[-1]["error_code"] == "agent_error"


def test_chat_stream_does_not_cache_answer_delta(tmp_path, monkeypatch):
    class EventAgent:
        def __init__(self, sink):
            self.sink = sink

        def run(self, user_input):
            self.sink(AgentEvent(run_id="run_1", event_type="answer_delta", payload={"text": "你"}))
            self.sink(
                AgentEvent(run_id="run_1", event_type="final_answer_generated", payload={"answer": "你好"})
            )
            return "你好"

    def fake_create_agent_components(config, event_sink=None, approval_callback=None, session_id="default"):
        return type("Components", (), {"agent": EventAgent(event_sink), "tools": FakeTools()})()

    import personal_knowledge_agent.apps.web.web_app as app_module

    monkeypatch.setattr(app_module, "create_agent_components", fake_create_agent_components)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )
    app = create_web_app(config=config)
    client = TestClient(app)

    response = client.post("/api/chat/stream", json={"message": "你好"})

    assert response.status_code == 200
    events = read_sse_events(response)
    assert [event["event_type"] for event in events] == ["answer_delta", "final_answer_generated"]
    assert [event["event_type"] for event in app.state.agent_events] == ["final_answer_generated"]


def test_chat_stream_forwards_context_compaction_events(tmp_path, monkeypatch):
    class EventAgent:
        def __init__(self, sink):
            self.sink = sink

        def run(self, user_input):
            self.sink(
                AgentEvent(
                    run_id="run_1",
                    event_type="prompt_usage_updated",
                    payload={"prompt_usage_ratio": 0.78},
                )
            )
            self.sink(
                AgentEvent(
                    run_id="run_1",
                    event_type="runtime_context_compaction_started",
                    payload={
                        "reason": "usage_threshold",
                        "prompt_usage_ratio": 0.78,
                        "threshold": 0.75,
                    },
                )
            )
            self.sink(
                AgentEvent(
                    run_id="run_1",
                    event_type="runtime_context_compaction_finished",
                    payload={
                        "reason": "usage_threshold",
                        "prompt_usage_ratio": 0.78,
                        "threshold": 0.75,
                        "mode": "summary_plus_recent",
                    },
                )
            )
            self.sink(AgentEvent(run_id="run_1", event_type="final_answer_generated", payload={"answer": "完成"}))
            return "完成"

    def fake_create_agent_components(config, event_sink=None, approval_callback=None, session_id="default"):
        return type("Components", (), {"agent": EventAgent(event_sink), "tools": FakeTools()})()

    import personal_knowledge_agent.apps.web.web_app as app_module

    monkeypatch.setattr(app_module, "create_agent_components", fake_create_agent_components)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )
    app = create_web_app(config=config)
    client = TestClient(app)

    response = client.post("/api/chat/stream", json={"message": "你好"})

    assert response.status_code == 200
    events = read_sse_events(response)
    assert [event["event_type"] for event in events] == [
        "prompt_usage_updated",
        "runtime_context_compaction_started",
        "runtime_context_compaction_finished",
        "final_answer_generated",
    ]
    assert events[0]["prompt_usage_ratio"] == 0.78
    assert events[1]["reason"] == "usage_threshold"
    assert events[2]["mode"] == "summary_plus_recent"
    assert "summary" not in events[2]
    assert "messages" not in events[2]
    assert "system_prompt" not in events[2]


def test_web_static_context_status_ui_is_lightweight():
    client = make_client()

    index_response = client.get("/")
    app_response = client.get("/static/app.js")

    assert index_response.status_code == 200
    assert app_response.status_code == 200
    assert 'id="contextStatus"' in index_response.text
    assert "Context 0%" in index_response.text
    assert "runtime_context_compaction_started" in app_response.text
    assert "上下文超限，正在压缩上下文" in app_response.text
    assert "<br\\s*\\/?>" in app_response.text
    assert 'document.createElement("br")' in app_response.text
    assert "完整 system prompt" not in index_response.text
    assert "完整 runtime messages" not in index_response.text
    assert "完整 session summary" not in index_response.text


def test_chat_rejects_second_request_for_same_session_without_blocking_first():
    agent = ControlledBlockingAgent()
    client = make_client(agent=agent)
    first_result = {}

    def send_first_message():
        first_result["response"] = client.post(
            "/api/chat/stream",
            json={"session_id": "chat_1", "message": "one"},
        )

    first_thread = threading.Thread(target=send_first_message)
    first_thread.start()
    assert agent.started.wait(timeout=3)

    second_response = client.post(
        "/api/chat/stream",
        json={"session_id": "chat_1", "message": "two"},
    )
    agent.release.set()
    first_thread.join(timeout=3)
    assert not first_thread.is_alive()

    assert second_response.status_code == 200
    second_events = read_sse_events(second_response)
    assert second_events[-1]["event_type"] == "error"
    assert second_events[-1]["error_code"] == "session_busy"
    assert second_events[-1]["message"] == "current session is already running"

    first_response = first_result["response"]
    assert first_response.status_code == 200
    first_events = read_sse_events(first_response)
    assert first_events[-1]["event_type"] == "final_answer_generated"
    assert first_events[-1]["answer"] == "reply: one"
    assert agent.max_active == 1


def test_chat_allows_different_sessions_to_run_concurrently():
    agent = BlockingAgent()
    client = make_client(agent=agent)
    results = []

    def send_message(session_id, text):
        response = client.post(
            "/api/chat/stream",
            json={"session_id": session_id, "message": text},
        )
        results.append(response)

    threads = [
        threading.Thread(target=send_message, args=("chat_1", "one")),
        threading.Thread(target=send_message, args=("chat_2", "two")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()

    assert len(results) == 2
    for response in results:
        assert response.status_code == 200
        assert read_sse_events(response)[-1]["event_type"] == "final_answer_generated"
    assert agent.max_active > 1


def test_recent_cards_returns_tool_result():
    client = make_client()

    response = client.get("/api/cards/recent")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["cards"][0]["card_id"] == "qa_1"
    assert response.json()["cards"][0]["category"] == "Agent 开发"


def test_search_cards_returns_tool_result():
    client = make_client()

    response = client.get("/api/cards/search?q=本地")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["cards"][0]["question"] == "本地"
    assert response.json()["cards"][0]["category"] == "Agent 开发"


def test_search_cards_rejects_empty_query():
    client = make_client()

    response = client.get("/api/cards/search?q=")

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error_code"] == "invalid_input"


def test_read_card_returns_tool_result():
    client = make_client()

    response = client.get("/api/cards/qa_1")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["card"]["card_id"] == "qa_1"
    assert response.json()["card"]["category"] == "Agent 开发"


def test_read_card_preserves_tool_error():
    client = make_client()

    response = client.get("/api/cards/missing")

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error_code"] == "not_found"


def test_create_and_list_sessions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = make_client()

    created = client.post("/api/sessions")
    listed = client.get("/api/sessions")

    assert created.status_code == 200
    assert created.json()["ok"] is True
    assert created.json()["session"]["title"] == "新会话"
    assert listed.json()["sessions"][0]["session_id"] == created.json()["session"]["session_id"]


def test_rename_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = make_client()
    session_id = client.post("/api/sessions").json()["session"]["session_id"]

    response = client.patch(f"/api/sessions/{session_id}", json={"title": "  新标题  "})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["session"]["title"] == "新标题"
    assert response.json()["session"]["title_source"] == "user"


def test_read_session_messages_returns_display_messages(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = make_client()
    session_id = client.post("/api/sessions").json()["session"]["session_id"]

    from personal_knowledge_agent.agent_context.conversation_sessions import ConversationTranscriptRepository

    transcript = ConversationTranscriptRepository(tmp_path, session_id=session_id)
    transcript.append_message({"role": "user", "content": "你好"})
    transcript.append_message({"role": "assistant", "content": "你好。"})

    response = client.get(f"/api/sessions/{session_id}/messages")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert [message["role"] for message in response.json()["messages"]] == ["user", "assistant"]


def test_chat_stream_accepts_session_id():
    agent = FakeAgent()
    client = make_client(agent=agent)

    response = client.post("/api/chat/stream", json={"session_id": "chat_1", "message": "你好"})

    assert response.status_code == 200
    assert read_sse_events(response)[-1]["answer"] == "reply: 你好"
    assert agent.inputs == ["你好"]


def test_chat_stream_defaults_to_default_session():
    agent = FakeAgent()
    client = make_client(agent=agent)

    response = client.post("/api/chat/stream", json={"message": "你好"})

    assert response.status_code == 200
    assert read_sse_events(response)[-1]["answer"] == "reply: 你好"
