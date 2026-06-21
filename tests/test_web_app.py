import json
import queue
import threading
import time

from fastapi.testclient import TestClient

from personal_knowledge_agent.agent_bootstrap import AgentConfig
from personal_knowledge_agent.agent_runtime import AgentEvent
from personal_knowledge_agent.tool_runtime import ApprovalRequest
from personal_knowledge_agent.apps.web import create_web_app
from personal_knowledge_agent.apps.web.web_app import WebApprovalManager


class FakeAgent:
    def __init__(self, fail=False):
        self.fail = fail
        self.inputs = []

    def run(self, user_input):
        self.inputs.append(user_input)
        if self.fail:
            raise RuntimeError("temporary failure")
        return f"reply: {user_input}"


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


class FakeTools:
    def list_recent_cards(self, arguments):
        return {
            "ok": True,
            "cards": [
                {
                    "card_id": "qa_1",
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


def make_client(agent=None, tools=None):
    app = create_web_app(agent=agent or FakeAgent(), tools=tools or FakeTools())
    return TestClient(app)


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


def test_chat_stream_returns_agent_answer():
    agent = FakeAgent()
    client = make_client(agent=agent)

    response = client.post("/api/chat/stream", json={"message": "  你好  "})

    assert response.status_code == 200
    events = read_sse_events(response)
    assert events[-1]["event_type"] == "final_answer_generated"
    assert events[-1]["answer"] == "reply: 你好"
    assert agent.inputs == ["你好"]


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
    assert "完整 system prompt" not in index_response.text
    assert "完整 runtime messages" not in index_response.text
    assert "完整 session summary" not in index_response.text


def test_chat_serializes_agent_access():
    agent = BlockingAgent()
    client = make_client(agent=agent)

    def send_message(text):
        response = client.post("/api/chat/stream", json={"message": text})
        assert response.status_code == 200
        assert read_sse_events(response)[-1]["event_type"] == "final_answer_generated"

    threads = [
        threading.Thread(target=send_message, args=("one",)),
        threading.Thread(target=send_message, args=("two",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert agent.max_active == 1


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
