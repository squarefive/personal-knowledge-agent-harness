from personal_knowledge_agent.sqlite_store import SQLiteStore
from personal_knowledge_agent.tool_dispatcher import ToolDispatcher
from personal_knowledge_agent.tools import KnowledgeTools


def test_save_qa_card_validates_required_fields(tmp_path):
    tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))

    result = tools.save_qa_card({"question": "缺少答案"})

    assert result["ok"] is False
    assert result["error_code"] == "invalid_input"


def test_tools_save_read_search_and_recent(tmp_path):
    tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))

    saved = tools.save_qa_card(
        {
            "question": "DeepSeek 在本项目里负责什么？",
            "answer": "DeepSeek 只通过薄 LLM Client 提供模型调用能力。",
            "summary": "DeepSeek 是第一版 LLM 服务。",
            "keywords": ["DeepSeek", "LLM Client"],
        }
    )

    assert saved["ok"] is True

    read = tools.read_qa_card({"card_id": saved["card_id"]})
    assert read["ok"] is True
    assert read["card"]["source_type"] == "manual_qa"

    searched = tools.search_qa_cards({"query": "DeepSeek", "limit": 5})
    assert searched["ok"] is True
    assert searched["cards"][0]["card_id"] == saved["card_id"]

    recent = tools.list_recent_cards({"limit": 5})
    assert recent["ok"] is True
    assert recent["cards"][0]["card_id"] == saved["card_id"]


def test_read_qa_card_not_found_returns_structured_error(tmp_path):
    tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))

    result = tools.read_qa_card({"card_id": "missing"})

    assert result["ok"] is False
    assert result["error_code"] == "not_found"


def test_tool_dispatcher_display_output_uses_declared_fields(tmp_path):
    tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(tools)
    result = {
        "ok": True,
        "cards": [
            {
                "card_id": "qa_1",
                "question": "问题",
                "summary": "摘要",
                "answer_snippet": "片段",
                "score": 3,
                "source_type": "manual_qa",
                "created_at": "2026-05-30T00:00:00+00:00",
                "internal": "hidden",
            }
        ],
        "debug": {"sql": "hidden"},
    }

    display = dispatcher.display_output("search_qa_cards", result)

    assert display == {
        "ok": True,
        "cards": [
            {
                "card_id": "qa_1",
                "question": "问题",
                "summary": "摘要",
                "answer_snippet": "片段",
                "score": 3,
                "source_type": "manual_qa",
                "created_at": "2026-05-30T00:00:00+00:00",
            }
        ],
    }


def test_tool_dispatcher_display_output_keeps_unknown_tool_error(tmp_path):
    tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(tools)

    display = dispatcher.display_output(
        "unknown_tool",
        {"ok": False, "error_code": "unknown_tool", "message": "missing", "debug": "hidden"},
    )

    assert display == {"ok": False, "error_code": "unknown_tool", "message": "missing"}
