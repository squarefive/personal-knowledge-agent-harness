from personal_knowledge_agent.qa_store import SQLiteStore


def test_save_read_search_and_recent_cards(tmp_path):
    store = SQLiteStore(tmp_path / "knowledge.db")

    card = store.save_card(
        question="Agent 的第一版边界是什么？",
        answer="第一版只做 Q&A 保存、检索、回答和来源引用。",
        summary="第一版只验证本地 Q&A 知识闭环。",
        keywords=["Agent", "Q&A", "边界"],
    )

    assert card.id.startswith("qa_")
    assert card.source_type == "manual_qa"

    read_back = store.read_card(card.id)
    assert read_back == card

    results = store.search_cards("Q&A 边界", limit=5)
    assert len(results) == 1
    assert results[0].card_id == card.id
    assert results[0].score > 0

    recent = store.list_recent_cards(limit=10)
    assert [item.id for item in recent] == [card.id]


def test_search_returns_empty_for_no_match(tmp_path):
    store = SQLiteStore(tmp_path / "knowledge.db")
    store.save_card(
        question="SQLite 负责什么？",
        answer="SQLite 是第一版唯一长期记忆来源。",
        summary="SQLite 保存 Q&A 卡片。",
        keywords=["SQLite", "长期记忆"],
    )

    assert store.search_cards("完全不存在的检索词") == []
