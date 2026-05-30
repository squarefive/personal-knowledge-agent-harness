import json

import pytest

from personal_knowledge_agent.llm_client import DeepSeekClient


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
