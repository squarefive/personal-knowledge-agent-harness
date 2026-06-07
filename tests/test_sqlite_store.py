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
    assert card.is_vectorized == 0

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


def test_update_card_changes_current_card(tmp_path):
    store = SQLiteStore(tmp_path / "knowledge.db")
    card = store.save_card(
        question="旧问题？",
        answer="旧答案。",
        summary="旧摘要。",
        keywords=["旧"],
    )

    updated = store.update_card(
        card.id,
        question="新问题？",
        answer="新答案。",
        summary="新摘要。",
        keywords=["新"],
    )

    assert updated is not None
    assert updated.id == card.id
    assert updated.question == "新问题？"
    assert updated.answer == "新答案。"
    assert updated.summary == "新摘要。"
    assert updated.keywords == ["新"]
    assert updated.created_at == card.created_at
    assert updated.updated_at != card.updated_at
    assert updated.is_vectorized == 0


def test_update_card_requires_existing_card_and_non_empty_patch(tmp_path):
    store = SQLiteStore(tmp_path / "knowledge.db")

    assert store.update_card("qa_missing", question="新问题？") is None

    card = store.save_card(
        question="问题？",
        answer="答案。",
        summary="摘要。",
        keywords=["关键词"],
    )
    try:
        store.update_card(card.id)
    except ValueError as exc:
        assert "at least one field" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_delete_card_physically_removes_card(tmp_path):
    store = SQLiteStore(tmp_path / "knowledge.db")
    card = store.save_card(
        question="要删除的问题？",
        answer="要删除的答案。",
        summary="要删除的摘要。",
        keywords=["删除"],
    )

    assert store.delete_card(card.id) is True
    assert store.read_card(card.id) is None
    assert store.search_cards("要删除的问题") == []
    assert store.list_recent_cards() == []
    assert store.delete_card(card.id) is False


def test_vectorized_marker_tracks_cards_needing_semantic_index(tmp_path):
    store = SQLiteStore(tmp_path / "knowledge.db")
    first = store.save_card(
        question="第一个问题？",
        answer="第一个答案。",
        summary="第一个摘要。",
        keywords=["第一个"],
    )
    second = store.save_card(
        question="第二个问题？",
        answer="第二个答案。",
        summary="第二个摘要。",
        keywords=["第二个"],
    )

    assert [card.id for card in store.list_unvectorized_cards()] == [first.id, second.id]
    assert store.mark_card_vectorized(first.id) is True
    assert [card.id for card in store.list_unvectorized_cards()] == [second.id]

    updated = store.update_card(first.id, summary="更新后的摘要。")

    assert updated is not None
    assert updated.is_vectorized == 0
    assert [card.id for card in store.list_unvectorized_cards()] == [first.id, second.id]


def test_existing_database_gets_vectorized_marker(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = SQLiteStore(db_path)
    card = store.save_card(
        question="历史问题？",
        answer="历史答案。",
        summary="历史摘要。",
        keywords=["历史"],
    )
    with store._connect() as conn:
        conn.execute("ALTER TABLE qa_cards RENAME TO qa_cards_old")
        conn.execute(
            """
            CREATE TABLE qa_cards (
              id TEXT PRIMARY KEY,
              question TEXT NOT NULL,
              answer TEXT NOT NULL,
              summary TEXT NOT NULL,
              keywords TEXT NOT NULL,
              source_type TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO qa_cards (
              id, question, answer, summary, keywords, source_type, created_at, updated_at
            )
            SELECT id, question, answer, summary, keywords, source_type, created_at, updated_at
            FROM qa_cards_old
            """
        )
        conn.execute("DROP TABLE qa_cards_old")

    migrated = SQLiteStore(db_path)
    read_back = migrated.read_card(card.id)

    assert read_back is not None
    assert read_back.is_vectorized == 0
