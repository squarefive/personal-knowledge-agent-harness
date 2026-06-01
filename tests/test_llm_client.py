import json
from io import BytesIO
from urllib import error

import pytest

from personal_knowledge_agent import llm_client
from personal_knowledge_agent.llm_client import DeepSeekClient


class FakeResponse:
    def __init__(self, body: dict):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


def http_error(status: int, body: str = "error") -> error.HTTPError:
    return error.HTTPError(
        url="https://api.deepseek.com/chat/completions",
        code=status,
        msg=body,
        hdrs={},
        fp=BytesIO(body.encode("utf-8")),
    )


def test_deepseek_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        DeepSeekClient()


def test_deepseek_client_parses_tool_calls():
    data = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "search_qa_cards",
                                "arguments": json.dumps({"query": "SQLite"}),
                            },
                        }
                    ],
                }
            }
        ]
    }

    response = DeepSeekClient._parse_response(data)

    assert response.text is None
    assert response.tool_calls[0].id == "call_1"
    assert response.tool_calls[0].name == "search_qa_cards"
    assert response.tool_calls[0].arguments == {"query": "SQLite"}


def test_deepseek_client_retries_network_errors(monkeypatch):
    calls = []
    sleeps = []

    def fake_urlopen(req, timeout):
        calls.append((req, timeout))
        if len(calls) == 1:
            raise error.URLError("temporary EOF")
        return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(llm_client.time, "sleep", lambda seconds: sleeps.append(seconds))

    client = DeepSeekClient(api_key="key", retry_backoff_seconds=(0.5, 1.0))
    response = client.chat(messages=[], tools=[], system_prompt="system")

    assert response.text == "ok"
    assert len(calls) == 2
    assert sleeps == [0.5]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_deepseek_client_retries_retryable_http_statuses(monkeypatch, status):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req, timeout))
        if len(calls) == 1:
            raise http_error(status, "temporary")
        return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(llm_client.time, "sleep", lambda seconds: None)

    client = DeepSeekClient(api_key="key")
    response = client.chat(messages=[], tools=[], system_prompt="system")

    assert response.text == "ok"
    assert len(calls) == 2


@pytest.mark.parametrize("status", [400, 401, 402, 422])
def test_deepseek_client_does_not_retry_non_retryable_http_statuses(monkeypatch, status):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req, timeout))
        raise http_error(status, "not retryable")

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)

    client = DeepSeekClient(api_key="key")
    with pytest.raises(RuntimeError, match=f"status {status} after 1 attempts"):
        client.chat(messages=[], tools=[], system_prompt="system")

    assert len(calls) == 1


def test_deepseek_client_reports_retry_exhaustion(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req, timeout))
        raise error.URLError("temporary EOF")

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(llm_client.time, "sleep", lambda seconds: None)

    client = DeepSeekClient(api_key="key", max_retries=2)
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        client.chat(messages=[], tools=[], system_prompt="system")

    assert len(calls) == 3
