from personal_knowledge_agent.agent_memory import MemoryIndexStore, MemoryStore
from personal_knowledge_agent.qa_store import SQLiteStore
from personal_knowledge_agent.schemas import ToolCall
from personal_knowledge_agent.tools import KnowledgeTools, ToolDispatcher


class FakeSemanticIndex:
    def __init__(self, *, enabled=True, hits=None, fail_upsert_ids=None, fail_search=False):
        self.enabled = enabled
        self.hits = hits or []
        self.fail_upsert_ids = set(fail_upsert_ids or [])
        self.fail_search = fail_search
        self.upserted = []
        self.deleted = []

    def is_enabled(self):
        return self.enabled

    def search(self, query, limit):
        if self.fail_search:
            raise RuntimeError("qdrant unavailable")
        return self.hits[:limit]

    def upsert_card(self, card):
        if card.id in self.fail_upsert_ids:
            raise RuntimeError("embedding failed")
        self.upserted.append(card.id)

    def delete_card(self, card_id):
        self.deleted.append(card_id)


class FakeHit:
    def __init__(self, card_id, score):
        self.card_id = card_id
        self.score = score


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


def test_update_and_delete_qa_card_tools(tmp_path):
    tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    saved = tools.save_qa_card(
        {
            "question": "旧问题？",
            "answer": "旧答案。",
            "summary": "旧摘要。",
            "keywords": ["旧"],
        }
    )

    updated = tools.update_qa_card(
        {
            "card_id": saved["card_id"],
            "question": "新问题？",
            "answer": "新答案。",
            "summary": "新摘要。",
            "keywords": ["新"],
        }
    )

    assert updated["ok"] is True
    assert updated["card"]["card_id"] == saved["card_id"]
    assert updated["card"]["question"] == "新问题？"
    assert updated["card"]["keywords"] == ["新"]

    deleted = tools.delete_qa_card({"card_id": saved["card_id"]})

    assert deleted == {"ok": True, "deleted_card_id": saved["card_id"]}
    assert tools.read_qa_card({"card_id": saved["card_id"]})["error_code"] == "not_found"


def test_update_and_delete_qa_card_tools_return_not_found(tmp_path):
    tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))

    updated = tools.update_qa_card({"card_id": "qa_missing", "summary": "新摘要。"})
    deleted = tools.delete_qa_card({"card_id": "qa_missing"})

    assert updated["ok"] is False
    assert updated["error_code"] == "not_found"
    assert deleted["ok"] is False
    assert deleted["error_code"] == "not_found"


def test_hybrid_search_degrades_to_sqlite_like_when_semantic_index_disabled(tmp_path):
    store = SQLiteStore(tmp_path / "knowledge.db")
    tools = KnowledgeTools(store, semantic_index=FakeSemanticIndex(enabled=False))
    saved = tools.save_qa_card(
        {
            "question": "程序级来源校验是什么？",
            "answer": "程序根据工具结果生成来源区块。",
            "summary": "来源区块必须来自工具证据。",
            "keywords": ["来源", "校验"],
        }
    )

    result = tools.hybrid_search_qa_cards({"query": "来源校验", "limit": 5})

    assert result["ok"] is True
    assert result["cards"][0]["card_id"] == saved["card_id"]
    assert "warning" in result


def test_hybrid_search_merges_semantic_hits_and_reads_sqlite_cards(tmp_path):
    store = SQLiteStore(tmp_path / "knowledge.db")
    first = store.save_card(
        question="关键词问题？",
        answer="关键词答案。",
        summary="关键词摘要。",
        keywords=["关键词"],
    )
    second = store.save_card(
        question="语义问题？",
        answer="语义答案。",
        summary="语义摘要。",
        keywords=["语义"],
    )
    tools = KnowledgeTools(
        store,
        semantic_index=FakeSemanticIndex(hits=[FakeHit(second.id, 0.87)]),
    )

    result = tools.hybrid_search_qa_cards({"query": "关键词", "limit": 5})

    assert result["ok"] is True
    assert [card["card_id"] for card in result["cards"]] == [first.id, second.id]
    assert result["cards"][1]["question"] == "语义问题？"


def test_rebuild_qa_semantic_index_only_indexes_unvectorized_cards(tmp_path):
    store = SQLiteStore(tmp_path / "knowledge.db")
    first = store.save_card(
        question="已向量化问题？",
        answer="已向量化答案。",
        summary="已向量化摘要。",
        keywords=["已向量化"],
    )
    second = store.save_card(
        question="未向量化问题？",
        answer="未向量化答案。",
        summary="未向量化摘要。",
        keywords=["未向量化"],
    )
    store.mark_card_vectorized(first.id)
    semantic_index = FakeSemanticIndex()
    tools = KnowledgeTools(store, semantic_index=semantic_index)

    result = tools.rebuild_qa_semantic_index({})

    assert result["ok"] is True
    assert result["total"] == 1
    assert result["indexed"] == 1
    assert semantic_index.upserted == [second.id]
    assert store.read_card(first.id).is_vectorized == 1
    assert store.read_card(second.id).is_vectorized == 1


def test_rebuild_qa_semantic_index_keeps_failed_cards_unvectorized(tmp_path):
    store = SQLiteStore(tmp_path / "knowledge.db")
    card = store.save_card(
        question="失败问题？",
        answer="失败答案。",
        summary="失败摘要。",
        keywords=["失败"],
    )
    tools = KnowledgeTools(
        store,
        semantic_index=FakeSemanticIndex(fail_upsert_ids={card.id}),
    )

    result = tools.rebuild_qa_semantic_index({})

    assert result["status"] == "partial_failed"
    assert result["failed_card_ids"] == [card.id]
    assert store.read_card(card.id).is_vectorized == 0


def test_save_update_delete_sync_semantic_index_best_effort(tmp_path):
    store = SQLiteStore(tmp_path / "knowledge.db")
    semantic_index = FakeSemanticIndex()
    tools = KnowledgeTools(store, semantic_index=semantic_index)

    saved = tools.save_qa_card(
        {
            "question": "同步问题？",
            "answer": "同步答案。",
            "summary": "同步摘要。",
            "keywords": ["同步"],
        }
    )
    updated = tools.update_qa_card({"card_id": saved["card_id"], "summary": "更新摘要。"})
    deleted = tools.delete_qa_card({"card_id": saved["card_id"]})

    assert store.read_card(saved["card_id"]) is None
    assert updated["ok"] is True
    assert deleted["ok"] is True
    assert semantic_index.upserted == [saved["card_id"], saved["card_id"]]
    assert semantic_index.deleted == [saved["card_id"]]


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


def test_tool_dispatcher_handles_update_and_delete_tools(tmp_path):
    tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(tools)
    saved = tools.save_qa_card(
        {
            "question": "旧问题？",
            "answer": "旧答案。",
            "summary": "旧摘要。",
            "keywords": ["旧"],
        }
    )

    updated = dispatcher.execute(
        ToolCall(
            id="call_1",
            name="update_qa_card",
            arguments={"card_id": saved["card_id"], "summary": "新摘要。"},
        )
    )
    deleted = dispatcher.execute(
        ToolCall(
            id="call_2",
            name="delete_qa_card",
            arguments={"card_id": saved["card_id"]},
        )
    )

    assert updated["ok"] is True
    assert updated["card"]["summary"] == "新摘要。"
    assert deleted == {"ok": True, "deleted_card_id": saved["card_id"]}


def test_tool_dispatcher_display_output_keeps_unknown_tool_error(tmp_path):
    tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(tools)

    display = dispatcher.display_output(
        "unknown_tool",
        {"ok": False, "error_code": "unknown_tool", "message": "missing", "debug": "hidden"},
    )

    assert display == {"ok": False, "error_code": "unknown_tool", "message": "missing"}


def test_memory_tools_list_and_read_memory(tmp_path):
    memory_dir = tmp_path / ".memory"
    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text(
        "\n".join(
            [
                "# Memory Index",
                "",
                "| name | type | description | path |",
                "|---|---|---|---|",
                "| project-boundary | project | Project boundary | .memory/project-boundary.md |",
            ]
        ),
        encoding="utf-8",
    )
    (memory_dir / "project-boundary.md").write_text(
        "\n".join(
            [
                "---",
                'name: "project-boundary"',
                'type: "project"',
                'description: "Project boundary"',
                'updated_at: "2026-05-31"',
                'source_type: "user_decision"',
                "---",
                "",
                "Q&A 和 Agent memory 分开。",
            ]
        ),
        encoding="utf-8",
    )
    tools = KnowledgeTools(
        SQLiteStore(tmp_path / "knowledge.db"),
        memory_index_store=MemoryIndexStore(tmp_path),
        memory_store=MemoryStore(tmp_path),
    )

    index = tools.list_memory_index({"limit": 10})
    memory = tools.read_memory({"name": "project-boundary"})

    assert index["ok"] is True
    assert index["entries"][0]["name"] == "project-boundary"
    assert memory["ok"] is True
    assert memory["memory"]["content"] == "Q&A 和 Agent memory 分开。"

def test_tool_dispatcher_handles_memory_tools(tmp_path):
    tools = KnowledgeTools(
        SQLiteStore(tmp_path / "knowledge.db"),
        memory_index_store=MemoryIndexStore(tmp_path),
    )
    dispatcher = ToolDispatcher(tools)

    result = dispatcher.execute(ToolCall(id="call_1", name="list_memory_index", arguments={"limit": 5}))

    assert result == {"ok": True, "entries": []}
