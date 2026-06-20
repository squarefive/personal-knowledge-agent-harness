import pytest

from personal_knowledge_agent.agent_context.agent_profile_memory import (
    AgentMemoryDocumentRepository,
    AgentMemoryIndexRepository,
)
from personal_knowledge_agent.qa_data_access import QACardRepository
from personal_knowledge_agent.tool_runtime import ToolCall
from personal_knowledge_agent.agent_tools import AgentMemoryToolHandlers, QAKnowledgeToolHandlers
from personal_knowledge_agent.tool_runtime import ToolDispatcher


class FakeSemanticIndex:
    def __init__(
        self,
        *,
        enabled=True,
        hits=None,
        fail_upsert_ids=None,
        fail_delete_ids=None,
        fail_search=False,
    ):
        self.enabled = enabled
        self.hits = hits or []
        self.fail_upsert_ids = set(fail_upsert_ids or [])
        self.fail_delete_ids = set(fail_delete_ids or [])
        self.fail_search = fail_search
        self.upserted = []
        self.deleted = []
        self.search_limits = []

    def is_enabled(self):
        return self.enabled

    def search(self, query, limit):
        if self.fail_search:
            raise RuntimeError("qdrant unavailable")
        self.search_limits.append(limit)
        return self.hits[:limit]

    def upsert_card(self, card):
        if card.id in self.fail_upsert_ids:
            raise RuntimeError("embedding failed")
        self.upserted.append(card.id)

    def delete_card(self, card_id):
        if card_id in self.fail_delete_ids:
            raise RuntimeError("delete failed")
        self.deleted.append(card_id)


class FakeHit:
    def __init__(self, card_id, score):
        self.card_id = card_id
        self.score = score


def create_memory_tools(tmp_path):
    return AgentMemoryToolHandlers(
        memory_index_repository=AgentMemoryIndexRepository(tmp_path),
        memory_document_repository=AgentMemoryDocumentRepository(tmp_path),
    )


def create_dispatcher(tmp_path, qa_tools):
    return ToolDispatcher(qa_tools, create_memory_tools(tmp_path))


def test_tool_handlers_keep_qa_and_memory_dependencies_separate(tmp_path):
    qa_tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))
    memory_tools = create_memory_tools(tmp_path)

    assert not hasattr(qa_tools, "memory_index_repository")
    assert not hasattr(qa_tools, "memory_document_repository")
    assert not hasattr(memory_tools, "store")
    assert not hasattr(memory_tools, "semantic_index")


def test_tool_dispatcher_aggregates_qa_and_memory_definitions(tmp_path):
    qa_tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(qa_tools, create_memory_tools(tmp_path))

    tool_names = {
        definition["function"]["name"]
        for definition in dispatcher.definitions()
    }

    assert tool_names == {
        "save_qa_card",
        "search_qa_cards",
        "hybrid_search_qa_cards",
        "read_qa_card",
        "update_qa_card",
        "delete_qa_card",
        "list_recent_cards",
        "detect_duplicate_cards",
        "merge_qa_cards",
        "rebuild_qa_semantic_index",
        "list_memory_index",
        "read_memory",
    }


def test_detect_duplicate_cards_definition_includes_all_scope(tmp_path):
    tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))
    definition = next(
        item for item in tools.definitions()
        if item["function"]["name"] == "detect_duplicate_cards"
    )

    properties = definition["function"]["parameters"]["properties"]

    assert properties["scope"]["enum"] == ["target", "all"]
    assert "scope=all" in definition["function"]["description"]


def test_save_qa_card_validates_required_fields(tmp_path):
    tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))

    result = tools.save_qa_card({"question": "缺少答案"})

    assert result["ok"] is False
    assert result["error_code"] == "invalid_input"


def test_save_qa_card_requires_category(tmp_path):
    tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))

    result = tools.save_qa_card(
        {
            "question": "问题？",
            "answer": "答案。",
            "summary": "摘要。",
            "keywords": ["关键词"],
        }
    )

    assert result["ok"] is False
    assert result["error_code"] == "invalid_input"
    assert "category" in result["message"]


def test_tools_save_read_search_and_recent(tmp_path):
    tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))

    saved = tools.save_qa_card(
        {
            "question": "DeepSeek 在本项目里负责什么？",
            "answer": "DeepSeek 只通过薄 LLM Client 提供模型调用能力。",
            "summary": "DeepSeek 是第一版 LLM 服务。",
            "keywords": ["DeepSeek", "LLM Client"],
            "category": "Agent 开发",
        }
    )

    assert saved["ok"] is True
    assert saved["category"] == "Agent 开发"

    read = tools.read_qa_card({"card_id": saved["card_id"]})
    assert read["ok"] is True
    assert read["card"]["source_type"] == "manual_qa"
    assert read["card"]["category"] == "Agent 开发"

    searched = tools.search_qa_cards({"query": "DeepSeek", "limit": 5})
    assert searched["ok"] is True
    assert searched["cards"][0]["card_id"] == saved["card_id"]
    assert searched["cards"][0]["category"] == "Agent 开发"

    recent = tools.list_recent_cards({"limit": 5})
    assert recent["ok"] is True
    assert recent["cards"][0]["card_id"] == saved["card_id"]
    assert recent["cards"][0]["category"] == "Agent 开发"


def test_read_qa_card_not_found_returns_structured_error(tmp_path):
    tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))

    result = tools.read_qa_card({"card_id": "missing"})

    assert result["ok"] is False
    assert result["error_code"] == "not_found"


def test_update_and_delete_qa_card_tools(tmp_path):
    tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))
    saved = tools.save_qa_card(
        {
            "question": "旧问题？",
            "answer": "旧答案。",
            "summary": "旧摘要。",
            "keywords": ["旧"],
            "category": "Agent 开发",
        }
    )

    updated = tools.update_qa_card(
        {
            "card_id": saved["card_id"],
            "question": "新问题？",
            "answer": "新答案。",
            "summary": "新摘要。",
            "keywords": ["新"],
            "category": "Agent 开发",
        }
    )

    assert updated["ok"] is True
    assert updated["card"]["card_id"] == saved["card_id"]
    assert updated["card"]["question"] == "新问题？"
    assert updated["card"]["keywords"] == ["新"]
    assert updated["card"]["category"] == "Agent 开发"

    deleted = tools.delete_qa_card({"card_id": saved["card_id"]})

    assert deleted == {"ok": True, "deleted_card_id": saved["card_id"]}
    assert tools.read_qa_card({"card_id": saved["card_id"]})["error_code"] == "not_found"


def test_update_and_delete_qa_card_tools_return_not_found(tmp_path):
    tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))

    updated = tools.update_qa_card({"card_id": "qa_missing", "summary": "新摘要。"})
    deleted = tools.delete_qa_card({"card_id": "qa_missing"})

    assert updated["ok"] is False
    assert updated["error_code"] == "not_found"
    assert deleted["ok"] is False
    assert deleted["error_code"] == "not_found"


def test_hybrid_search_degrades_to_sqlite_like_when_semantic_index_disabled(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    tools = QAKnowledgeToolHandlers(store, semantic_index=FakeSemanticIndex(enabled=False))
    saved = tools.save_qa_card(
        {
            "question": "程序级来源校验是什么？",
            "answer": "程序根据工具结果生成来源区块。",
            "summary": "来源区块必须来自工具证据。",
            "keywords": ["来源", "校验"],
            "category": "Agent 开发",
        }
    )

    result = tools.hybrid_search_qa_cards({"query": "来源校验", "limit": 5})

    assert result["ok"] is True
    assert result["cards"][0]["card_id"] == saved["card_id"]
    assert result["cards"][0]["match_level"] == "strong"
    assert result["cards"][0]["matched_by"] == ["keyword"]
    assert "warning" in result


def test_hybrid_search_normalizes_scores_and_ranks_by_final_score(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    keyword_card = store.save_card(
        question="关键词问题？",
        answer="关键词答案。",
        summary="关键词摘要。",
        keywords=["关键词"],
        category="Agent 开发",
    )
    semantic_card = store.save_card(
        question="语义问题？",
        answer="语义答案。",
        summary="语义摘要。",
        keywords=["语义"],
        category="Agent 开发",
    )
    tools = QAKnowledgeToolHandlers(
        store,
        semantic_index=FakeSemanticIndex(hits=[FakeHit(semantic_card.id, 0.87)]),
    )

    result = tools.hybrid_search_qa_cards({"query": "关键词", "limit": 5})

    assert result["ok"] is True
    assert [card["card_id"] for card in result["cards"]] == [semantic_card.id]
    card = result["cards"][0]
    assert card["rank"] == 1
    assert card["score"] == card["final_score"]
    assert card["final_score"] == pytest.approx(0.522)
    assert card["keyword_score"] == 0.0
    assert card["keyword_score_norm"] == 0.0
    assert card["semantic_score"] == 0.87
    assert card["match_level"] == "medium"
    assert card["matched_by"] == ["semantic"]


def test_hybrid_search_combines_keyword_and_semantic_scores(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    card = store.save_card(
        question="氛围编程 vibe coding 是什么？",
        answer="vibe coding 是 AI 辅助编程范式。",
        summary="vibe coding 强调人机协作。",
        keywords=["vibe coding"],
        category="Agent 开发",
    )
    tools = QAKnowledgeToolHandlers(
        store,
        semantic_index=FakeSemanticIndex(hits=[FakeHit(card.id, 0.69)]),
    )

    result = tools.hybrid_search_qa_cards({"query": "vibe coding", "limit": 5})

    assert result["ok"] is True
    card_result = result["cards"][0]
    assert card_result["card_id"] == card.id
    assert card_result["keyword_score"] > 0
    assert card_result["keyword_score_norm"] == 1.0
    assert card_result["semantic_score"] == 0.69
    assert card_result["final_score"] == pytest.approx(0.814)
    assert card_result["match_level"] == "strong"
    assert card_result["matched_by"] == ["keyword", "semantic"]


def test_hybrid_search_returns_top_weak_candidate_with_warning(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    weak_card = store.save_card(
        question="弱相关问题？",
        answer="弱相关答案。",
        summary="弱相关摘要。",
        keywords=["弱相关"],
        category="Agent 开发",
    )
    weaker_card = store.save_card(
        question="更弱相关问题？",
        answer="更弱相关答案。",
        summary="更弱相关摘要。",
        keywords=["更弱相关"],
        category="Agent 开发",
    )
    tools = QAKnowledgeToolHandlers(
        store,
        semantic_index=FakeSemanticIndex(
            hits=[FakeHit(weak_card.id, 0.70), FakeHit(weaker_card.id, 0.60)]
        ),
    )

    result = tools.hybrid_search_qa_cards({"query": "没有关键词命中", "limit": 5})

    assert result["ok"] is True
    assert [card["card_id"] for card in result["cards"]] == [weak_card.id]
    assert result["cards"][0]["match_level"] == "weak"
    assert "弱相关候选" in result["warning"]


def test_hybrid_search_returns_empty_when_candidates_are_below_weak_threshold(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    card = store.save_card(
        question="低相关问题？",
        answer="低相关答案。",
        summary="低相关摘要。",
        keywords=["低相关"],
        category="Agent 开发",
    )
    tools = QAKnowledgeToolHandlers(
        store,
        semantic_index=FakeSemanticIndex(hits=[FakeHit(card.id, 0.20)]),
    )

    result = tools.hybrid_search_qa_cards({"query": "没有关键词命中", "limit": 5})

    assert result["ok"] is True
    assert result["cards"] == []
    assert result["message"] == "没有找到足够相关的本地知识卡片。"


def test_search_and_recent_cards_filter_by_category(tmp_path):
    tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))
    tools.save_qa_card(
        {
            "question": "Agent 问题？",
            "answer": "Agent 答案。",
            "summary": "Agent 摘要。",
            "keywords": ["共同词"],
            "category": "Agent 开发",
        }
    )
    search_saved = tools.save_qa_card(
        {
            "question": "检索问题？",
            "answer": "检索答案。",
            "summary": "检索摘要。",
            "keywords": ["共同词"],
            "category": "检索与知识库",
        }
    )

    searched = tools.search_qa_cards({"query": "共同词", "category": "检索与知识库"})
    recent = tools.list_recent_cards({"limit": 10, "category": "检索与知识库"})

    assert [card["card_id"] for card in searched["cards"]] == [search_saved["card_id"]]
    assert [card["card_id"] for card in recent["cards"]] == [search_saved["card_id"]]


def test_hybrid_search_filters_semantic_candidates_by_category(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    agent_card = store.save_card(
        question="Agent 语义问题？",
        answer="Agent 语义答案。",
        summary="Agent 语义摘要。",
        keywords=["语义"],
        category="Agent 开发",
    )
    search_card = store.save_card(
        question="检索语义问题？",
        answer="检索语义答案。",
        summary="检索语义摘要。",
        keywords=["语义"],
        category="检索与知识库",
    )
    tools = QAKnowledgeToolHandlers(
        store,
        semantic_index=FakeSemanticIndex(hits=[FakeHit(agent_card.id, 0.91), FakeHit(search_card.id, 0.86)]),
    )

    result = tools.hybrid_search_qa_cards(
        {"query": "没有关键词命中", "category": "检索与知识库", "limit": 5}
    )

    assert result["ok"] is True
    assert [card["card_id"] for card in result["cards"]] == [search_card.id]
    assert result["cards"][0]["category"] == "检索与知识库"


def test_hybrid_search_over_fetches_semantic_hits_when_category_filters(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    first_agent_card = store.save_card(
        question="第一个 Agent 语义问题？",
        answer="第一个 Agent 语义答案。",
        summary="第一个 Agent 语义摘要。",
        keywords=["不命中"],
        category="Agent 开发",
    )
    second_agent_card = store.save_card(
        question="第二个 Agent 语义问题？",
        answer="第二个 Agent 语义答案。",
        summary="第二个 Agent 语义摘要。",
        keywords=["不命中"],
        category="Agent 开发",
    )
    search_card = store.save_card(
        question="检索语义问题？",
        answer="检索语义答案。",
        summary="检索语义摘要。",
        keywords=["不命中"],
        category="检索与知识库",
    )
    semantic_index = FakeSemanticIndex(
        hits=[
            FakeHit(first_agent_card.id, 0.96),
            FakeHit(second_agent_card.id, 0.95),
            FakeHit(search_card.id, 0.90),
        ]
    )
    tools = QAKnowledgeToolHandlers(store, semantic_index=semantic_index)

    result = tools.hybrid_search_qa_cards(
        {"query": "没有关键词命中", "category": "检索与知识库", "limit": 2}
    )

    assert result["ok"] is True
    assert [card["card_id"] for card in result["cards"]] == [search_card.id]
    assert semantic_index.search_limits == [20]


def test_hybrid_search_does_not_fallback_across_category(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    agent_card = store.save_card(
        question="Agent 语义问题？",
        answer="Agent 语义答案。",
        summary="Agent 语义摘要。",
        keywords=["语义"],
        category="Agent 开发",
    )
    tools = QAKnowledgeToolHandlers(
        store,
        semantic_index=FakeSemanticIndex(hits=[FakeHit(agent_card.id, 0.91)]),
    )

    result = tools.hybrid_search_qa_cards(
        {"query": "没有关键词命中", "category": "检索与知识库", "limit": 5}
    )

    assert result["ok"] is True
    assert result["cards"] == []
    assert result["message"] == "指定 category 下没有找到相关本地知识卡片。"


def test_detect_duplicate_cards_filters_self_and_auto_returns_only_duplicates(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    target = store.save_card(
        question="alpha source check",
        answer="answer",
        summary="source summary",
        keywords=["source"],
        category="Agent 开发",
    )
    duplicate = store.save_card(
        question="alpha source check copy",
        answer="duplicate answer",
        summary="duplicate summary",
        keywords=["source"],
        category="Agent 开发",
    )
    possible = store.save_card(
        question="totally different",
        answer="possible answer",
        summary="possible summary",
        keywords=["source"],
        category="Agent 开发",
    )
    store.save_card(
        question="discard card",
        answer="discard answer",
        summary="discard summary",
        keywords=["discard"],
        category="Agent 开发",
    )
    tools = QAKnowledgeToolHandlers(
        store,
        semantic_index=FakeSemanticIndex(
            hits=[
                FakeHit(target.id, 0.99),
                FakeHit(duplicate.id, 0.89),
                FakeHit(possible.id, 0.80),
            ]
        ),
    )

    manual = tools.detect_duplicate_cards({"card_id": target.id, "mode": "manual", "limit": 5})
    auto = tools.detect_duplicate_cards({"card_id": target.id, "mode": "auto", "limit": 5})

    assert manual["ok"] is True
    assert [card["card_id"] for card in manual["candidates"]] == [duplicate.id, possible.id]
    assert [card["duplicate_level"] for card in manual["candidates"]] == ["duplicate", "possible_duplicate"]
    assert target.id not in [card["card_id"] for card in manual["candidates"]]
    assert [card["card_id"] for card in auto["candidates"]] == [duplicate.id]


def test_detect_duplicate_cards_all_scope_returns_duplicate_groups(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    first = store.save_card(
        question="DeepSeek API key 应该如何配置？",
        answer="把 DeepSeek API key 放到环境变量中。",
        summary="DeepSeek API key 配置方式。",
        keywords=["DeepSeek", "API key", "配置"],
        category="Agent 开发",
    )
    second = store.save_card(
        question="DeepSeek 的 API key 怎么配置？",
        answer="DeepSeek API key 应配置到环境变量。",
        summary="配置 DeepSeek API key。",
        keywords=["DeepSeek", "API key", "配置"],
        category="Agent 开发",
    )
    third = store.save_card(
        question="FastAPI 路由怎么测试？",
        answer="使用 TestClient 测试路由。",
        summary="FastAPI 路由测试。",
        keywords=["FastAPI", "测试"],
        category="工程架构",
    )
    tools = QAKnowledgeToolHandlers(store)

    result = tools.detect_duplicate_cards({"scope": "all", "mode": "manual", "limit": 20})

    assert result["ok"] is True
    assert result["scope"] == "all"
    assert result["checked_count"] == 3
    assert len(result["duplicate_groups"]) == 1
    assert result["duplicate_groups"][0]["card_ids"] == [first.id, second.id]
    assert result["duplicate_groups"][0]["duplicate_level"] == "duplicate"
    assert [card["card_id"] for card in result["duplicate_groups"][0]["cards"]] == [first.id, second.id]
    assert third.id not in result["duplicate_groups"][0]["card_ids"]


def test_detect_duplicate_cards_all_scope_merges_connected_pairs(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    first = store.save_card(
        question="上下文压缩什么时候触发？",
        answer="达到真实 token 阈值后触发。",
        summary="上下文压缩由 token usage 触发。",
        keywords=["上下文压缩", "token", "触发"],
        category="上下文管理",
    )
    second = store.save_card(
        question="context compact 何时触发？",
        answer="根据 token usage 判断是否触发。",
        summary="context compact 根据 token usage 触发。",
        keywords=["上下文压缩", "token", "compact"],
        category="上下文管理",
    )
    third = store.save_card(
        question="runtime compact 什么时候执行？",
        answer="上一轮 prompt token 占比超过阈值时执行。",
        summary="runtime compact 使用 token usage 判断。",
        keywords=["runtime compact", "token", "触发"],
        category="上下文管理",
    )
    tools = QAKnowledgeToolHandlers(store)

    result = tools.detect_duplicate_cards({"scope": "all", "mode": "manual", "limit": 20})

    assert len(result["duplicate_groups"]) == 1
    assert result["duplicate_groups"][0]["card_ids"] == [first.id, second.id, third.id]


def test_detect_duplicate_cards_all_scope_auto_returns_only_duplicates(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    store.save_card(
        question="DeepSeek API key 应该如何配置？",
        answer="把 key 放到环境变量。",
        summary="DeepSeek API key 配置。",
        keywords=["DeepSeek", "API key", "配置"],
        category="Agent 开发",
    )
    store.save_card(
        question="DeepSeek token 放在哪里？",
        answer="放到环境变量。",
        summary="DeepSeek token 配置。",
        keywords=["DeepSeek", "token", "配置"],
        category="Agent 开发",
    )
    tools = QAKnowledgeToolHandlers(store)

    manual = tools.detect_duplicate_cards({"scope": "all", "mode": "manual", "limit": 20})
    auto = tools.detect_duplicate_cards({"scope": "all", "mode": "auto", "limit": 20})

    assert len(manual["duplicate_groups"]) == 1
    assert manual["duplicate_groups"][0]["duplicate_level"] == "possible_duplicate"
    assert auto["duplicate_groups"] == []


def test_detect_duplicate_cards_applies_category_filter_and_degrades_to_keyword(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    target = store.save_card(
        question="来源校验",
        answer="答案",
        summary="摘要",
        keywords=["来源"],
        category="检索与知识库",
    )
    same_category = store.save_card(
        question="来源校验副本",
        answer="答案",
        summary="摘要",
        keywords=["来源"],
        category="检索与知识库",
    )
    other_category = store.save_card(
        question="来源校验其他分类",
        answer="答案",
        summary="摘要",
        keywords=["来源"],
        category="Agent 开发",
    )
    tools = QAKnowledgeToolHandlers(
        store,
        semantic_index=FakeSemanticIndex(
            fail_search=True,
            hits=[FakeHit(other_category.id, 0.99), FakeHit(same_category.id, 0.90)],
        ),
    )

    result = tools.detect_duplicate_cards(
        {"card_id": target.id, "category": "检索与知识库", "mode": "manual", "limit": 5}
    )

    assert result["ok"] is True
    assert [card["card_id"] for card in result["candidates"]] == [same_category.id]
    assert "warning" in result


def test_merge_qa_cards_creates_new_card_deletes_originals_and_syncs_semantic_index(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    first = store.save_card(
        question="问题一？",
        answer="答案一。",
        summary="摘要一。",
        keywords=["合并"],
        category="Agent 开发",
    )
    second = store.save_card(
        question="问题二？",
        answer="答案二。",
        summary="摘要二。",
        keywords=["合并"],
        category="Agent 开发",
    )
    semantic_index = FakeSemanticIndex()
    tools = QAKnowledgeToolHandlers(store, semantic_index=semantic_index)

    result = tools.merge_qa_cards(
        {
            "card_ids": [first.id, second.id],
            "question": "合并问题？",
            "answer": "合并答案。",
            "summary": "合并摘要。",
            "keywords": ["合并"],
            "category": "Agent 开发",
        }
    )

    assert result["ok"] is True
    assert result["deleted_card_ids"] == [first.id, second.id]
    assert store.read_card(first.id) is None
    assert store.read_card(second.id) is None
    assert store.read_card(result["new_card_id"]).question == "合并问题？"
    assert semantic_index.deleted == [first.id, second.id]
    assert semantic_index.upserted == [result["new_card_id"]]


def test_merge_qa_cards_missing_original_does_not_write(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    first = store.save_card(
        question="问题一？",
        answer="答案一。",
        summary="摘要一。",
        keywords=["合并"],
        category="Agent 开发",
    )
    tools = QAKnowledgeToolHandlers(store)

    result = tools.merge_qa_cards(
        {
            "card_ids": [first.id, "qa_missing"],
            "question": "合并问题？",
            "answer": "合并答案。",
            "summary": "合并摘要。",
            "keywords": ["合并"],
            "category": "Agent 开发",
        }
    )

    assert result["ok"] is False
    assert result["error_code"] == "not_found"
    assert store.read_card(first.id) is not None
    assert len(store.list_recent_cards(limit=10)) == 1


def test_merge_qa_cards_returns_warning_when_semantic_sync_fails(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    first = store.save_card(
        question="问题一？",
        answer="答案一。",
        summary="摘要一。",
        keywords=["合并"],
        category="Agent 开发",
    )
    second = store.save_card(
        question="问题二？",
        answer="答案二。",
        summary="摘要二。",
        keywords=["合并"],
        category="Agent 开发",
    )
    tools = QAKnowledgeToolHandlers(store, semantic_index=FakeSemanticIndex(fail_delete_ids={first.id}))

    result = tools.merge_qa_cards(
        {
            "card_ids": [first.id, second.id],
            "question": "合并问题？",
            "answer": "合并答案。",
            "summary": "合并摘要。",
            "keywords": ["合并"],
            "category": "Agent 开发",
        }
    )

    assert result["ok"] is True
    assert "warning" in result
    assert "语义索引删除失败" in result["warning"]


def test_rebuild_qa_semantic_index_only_indexes_unvectorized_cards(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    first = store.save_card(
        question="已向量化问题？",
        answer="已向量化答案。",
        summary="已向量化摘要。",
        keywords=["已向量化"],
        category="Agent 开发",
    )
    second = store.save_card(
        question="未向量化问题？",
        answer="未向量化答案。",
        summary="未向量化摘要。",
        keywords=["未向量化"],
        category="Agent 开发",
    )
    store.mark_card_vectorized(first.id)
    semantic_index = FakeSemanticIndex()
    tools = QAKnowledgeToolHandlers(store, semantic_index=semantic_index)

    result = tools.rebuild_qa_semantic_index({})

    assert result["ok"] is True
    assert result["total"] == 1
    assert result["indexed"] == 1
    assert semantic_index.upserted == [second.id]
    assert store.read_card(first.id).is_vectorized == 1
    assert store.read_card(second.id).is_vectorized == 1


def test_rebuild_qa_semantic_index_keeps_failed_cards_unvectorized(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    card = store.save_card(
        question="失败问题？",
        answer="失败答案。",
        summary="失败摘要。",
        keywords=["失败"],
        category="Agent 开发",
    )
    tools = QAKnowledgeToolHandlers(
        store,
        semantic_index=FakeSemanticIndex(fail_upsert_ids={card.id}),
    )

    result = tools.rebuild_qa_semantic_index({})

    assert result["status"] == "partial_failed"
    assert result["failed_card_ids"] == [card.id]
    assert store.read_card(card.id).is_vectorized == 0


def test_save_update_delete_sync_semantic_index_best_effort(tmp_path):
    store = QACardRepository(tmp_path / "knowledge.db")
    semantic_index = FakeSemanticIndex()
    tools = QAKnowledgeToolHandlers(store, semantic_index=semantic_index)

    saved = tools.save_qa_card(
        {
            "question": "同步问题？",
            "answer": "同步答案。",
            "summary": "同步摘要。",
            "keywords": ["同步"],
            "category": "Agent 开发",
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
    tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))
    dispatcher = create_dispatcher(tmp_path, tools)
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


def test_tool_dispatcher_display_output_includes_hybrid_ranking_fields(tmp_path):
    tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))
    dispatcher = create_dispatcher(tmp_path, tools)
    result = {
        "ok": True,
        "cards": [
            {
                "rank": 1,
                "card_id": "qa_1",
                "question": "问题",
                "summary": "摘要",
                "answer_snippet": "片段",
                "score": 0.8,
                "final_score": 0.8,
                "match_level": "strong",
                "matched_by": ["keyword", "semantic"],
                "keyword_score": 10,
                "keyword_score_norm": 1.0,
                "semantic_score": 0.67,
                "source_type": "manual_qa",
                "created_at": "2026-05-30T00:00:00+00:00",
                "category": "检索与知识库",
                "internal": "hidden",
            }
        ],
        "warning": "warn",
        "debug": "hidden",
    }

    display = dispatcher.display_output("hybrid_search_qa_cards", result)

    assert display == {
        "ok": True,
        "cards": [
            {
                "rank": 1,
                "card_id": "qa_1",
                "question": "问题",
                "summary": "摘要",
                "answer_snippet": "片段",
                "score": 0.8,
                "final_score": 0.8,
                "match_level": "strong",
                "matched_by": ["keyword", "semantic"],
                "keyword_score": 10,
                "keyword_score_norm": 1.0,
                "semantic_score": 0.67,
                "source_type": "manual_qa",
                "created_at": "2026-05-30T00:00:00+00:00",
                "category": "检索与知识库",
            }
        ],
        "warning": "warn",
    }


def test_tool_dispatcher_display_output_includes_duplicate_and_merge_fields(tmp_path):
    tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))
    dispatcher = create_dispatcher(tmp_path, tools)

    duplicate_display = dispatcher.display_output(
        "detect_duplicate_cards",
        {
            "ok": True,
            "scope": "all",
            "checked_card_id": "qa_1",
            "checked_count": 2,
            "candidates": [
                {
                    "card_id": "qa_2",
                    "question": "问题",
                    "summary": "摘要",
                    "category": "Agent 开发",
                    "duplicate_score": 0.91,
                    "duplicate_level": "duplicate",
                    "reason": "同分类",
                    "debug": "hidden",
                }
            ],
            "duplicate_groups": [
                {
                    "card_ids": ["qa_1", "qa_2"],
                    "duplicate_score": 0.91,
                    "duplicate_level": "duplicate",
                    "reason": "同分类",
                    "cards": [
                        {
                            "card_id": "qa_1",
                            "question": "问题一",
                            "summary": "摘要一",
                            "category": "Agent 开发",
                            "debug": "hidden",
                        }
                    ],
                    "debug": "hidden",
                }
            ],
            "debug": "hidden",
        },
    )
    merge_display = dispatcher.display_output(
        "merge_qa_cards",
        {
            "ok": True,
            "new_card_id": "qa_new",
            "deleted_card_ids": ["qa_1", "qa_2"],
            "source_type": "manual_qa",
            "created_at": "2026-06-19T00:00:00+00:00",
            "category": "Agent 开发",
            "debug": "hidden",
        },
    )

    assert duplicate_display == {
        "ok": True,
        "scope": "all",
        "checked_card_id": "qa_1",
        "checked_count": 2,
        "candidates": [
            {
                "card_id": "qa_2",
                "question": "问题",
                "summary": "摘要",
                "category": "Agent 开发",
                "duplicate_score": 0.91,
                "duplicate_level": "duplicate",
                "reason": "同分类",
            }
        ],
        "duplicate_groups": [
            {
                "card_ids": ["qa_1", "qa_2"],
                "duplicate_score": 0.91,
                "duplicate_level": "duplicate",
                "reason": "同分类",
                "cards": [
                    {
                        "card_id": "qa_1",
                        "question": "问题一",
                        "summary": "摘要一",
                        "category": "Agent 开发",
                    }
                ],
            }
        ],
    }
    assert merge_display == {
        "ok": True,
        "new_card_id": "qa_new",
        "deleted_card_ids": ["qa_1", "qa_2"],
        "source_type": "manual_qa",
        "created_at": "2026-06-19T00:00:00+00:00",
        "category": "Agent 开发",
    }


def test_tool_dispatcher_handles_update_and_delete_tools(tmp_path):
    tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))
    dispatcher = create_dispatcher(tmp_path, tools)
    saved = tools.save_qa_card(
        {
            "question": "旧问题？",
            "answer": "旧答案。",
            "summary": "旧摘要。",
            "keywords": ["旧"],
            "category": "Agent 开发",
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
    tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))
    dispatcher = create_dispatcher(tmp_path, tools)

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
    tools = create_memory_tools(tmp_path)

    index = tools.list_memory_index({"limit": 10})
    memory = tools.read_memory({"name": "project-boundary"})

    assert index["ok"] is True
    assert index["entries"][0]["name"] == "project-boundary"
    assert memory["ok"] is True
    assert memory["memory"]["content"] == "Q&A 和 Agent memory 分开。"

def test_tool_dispatcher_handles_memory_tools(tmp_path):
    qa_tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))
    memory_tools = create_memory_tools(tmp_path)
    dispatcher = ToolDispatcher(qa_tools, memory_tools)

    result = dispatcher.execute(ToolCall(id="call_1", name="list_memory_index", arguments={"limit": 5}))

    assert result == {"ok": True, "entries": []}
