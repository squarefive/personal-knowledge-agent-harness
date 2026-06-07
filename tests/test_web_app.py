import threading
import time

from fastapi.testclient import TestClient

from personal_knowledge_agent.config import AgentConfig
from personal_knowledge_agent.permissions import ApprovalRequest
from personal_knowledge_agent.web.app import create_web_app


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
                "source_type": "manual_qa",
                "created_at": "2026-06-02T00:00:00Z",
                "updated_at": "2026-06-02T00:00:00Z",
            },
        }


def make_client(agent=None, tools=None):
    app = create_web_app(agent=agent or FakeAgent(), tools=tools or FakeTools())
    return TestClient(app)


def test_chat_returns_agent_answer():
    agent = FakeAgent()
    client = make_client(agent=agent)

    response = client.post("/api/chat", json={"message": "  你好  "})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["answer"] == "reply: 你好"
    assert agent.inputs == ["你好"]


def test_web_runtime_uses_default_denial_approval_callback(tmp_path, monkeypatch):
    captured = {}

    def fake_create_agent_components(config, event_sink=None, approval_callback=None):
        captured["approval_callback"] = approval_callback
        return type("Components", (), {"agent": FakeAgent(), "tools": FakeTools()})()

    import personal_knowledge_agent.web.app as app_module

    monkeypatch.setattr(app_module, "create_agent_components", fake_create_agent_components)
    config = AgentConfig(
        deepseek_api_key="test-key",
        deepseek_model="test-model",
        knowledge_db_path=tmp_path / "knowledge.db",
    )

    create_web_app(config=config)

    assert captured["approval_callback"](
        ApprovalRequest(tool_name="delete_qa_card", arguments={"card_id": "qa_1"}, reason="danger")
    ) is False


def test_chat_rejects_empty_message():
    client = make_client()

    response = client.post("/api/chat", json={"message": " "})

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error_code"] == "invalid_input"


def test_chat_returns_structured_error_on_agent_failure():
    client = make_client(agent=FakeAgent(fail=True))

    response = client.post("/api/chat", json={"message": "你好"})

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error_code"] == "agent_error"


def test_chat_serializes_agent_access():
    agent = BlockingAgent()
    client = make_client(agent=agent)

    def send_message(text):
        response = client.post("/api/chat", json={"message": text})
        assert response.status_code == 200
        assert response.json()["ok"] is True

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


def test_search_cards_returns_tool_result():
    client = make_client()

    response = client.get("/api/cards/search?q=本地")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["cards"][0]["question"] == "本地"


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


def test_read_card_preserves_tool_error():
    client = make_client()

    response = client.get("/api/cards/missing")

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error_code"] == "not_found"
