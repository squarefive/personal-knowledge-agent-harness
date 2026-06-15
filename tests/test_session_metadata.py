from personal_knowledge_agent.agent_context.conversation_sessions import ConversationSessionMetadataRepository as SessionMetadataStore


def test_session_metadata_load_or_create_writes_default_metadata(tmp_path):
    store = SessionMetadataStore(tmp_path, model="deepseek-test")

    metadata = store.load_or_create()

    assert metadata.session_id == "default"
    assert metadata.model == "deepseek-test"
    assert metadata.transcript_path == ".sessions/default/transcript.jsonl"
    assert metadata.summary_path == ".sessions/default/summary.md"
    assert metadata.artifacts_dir == ".sessions/default/artifacts"
    assert metadata.title == "新会话"
    assert metadata.title_source == "auto"
    assert metadata.last_user_message is None
    assert store.path.exists()


def test_session_metadata_updates_counts_and_restore_mode(tmp_path):
    store = SessionMetadataStore(tmp_path)

    updated = store.update_counts(
        event_count=3,
        message_count=2,
        summary_status="valid",
        summary_attempts=2,
        last_restore_mode="summary_plus_recent",
    )

    assert updated.event_count == 3
    assert updated.message_count == 2
    assert updated.summary_status == "valid"
    assert updated.summary_attempts == 2
    assert updated.last_restore_mode == "summary_plus_recent"
    assert store.load_or_create() == updated


def test_session_metadata_lists_sessions_by_updated_at(tmp_path):
    older = SessionMetadataStore(tmp_path, session_id="older")
    newer = SessionMetadataStore(tmp_path, session_id="newer")

    older.rename_session("旧会话")
    newer.rename_session("新会话")

    sessions = SessionMetadataStore(tmp_path).list_sessions()

    assert [session.session_id for session in sessions] == ["newer", "older"]


def test_session_metadata_renames_session_and_preserves_user_title(tmp_path):
    store = SessionMetadataStore(tmp_path, session_id="named")

    renamed = store.rename_session("  手动标题  ")
    updated = store.update_after_user_message("第一条用户消息", event_count=1, message_count=1)

    assert renamed.title == "手动标题"
    assert updated.title == "手动标题"
    assert updated.title_source == "user"
    assert updated.last_user_message == "第一条用户消息"


def test_session_metadata_generates_auto_title_from_user_message(tmp_path):
    store = SessionMetadataStore(tmp_path, session_id="auto")

    updated = store.update_after_user_message("SQLite LIKE 检索怎么做？", event_count=1, message_count=1)

    assert updated.title == "SQLite LIKE 检索怎么做？"
    assert updated.title_source == "auto"
    assert updated.last_user_message == "SQLite LIKE 检索怎么做？"


def test_session_metadata_auto_title_uses_first_user_message(tmp_path):
    store = SessionMetadataStore(tmp_path, session_id="auto_once")

    first = store.update_after_user_message("第一条消息", event_count=1, message_count=1)
    second = store.update_after_user_message("第二条消息", event_count=2, message_count=2)

    assert first.title == "第一条消息"
    assert second.title == "第一条消息"
    assert second.title_source == "auto"
    assert second.last_user_message == "第二条消息"
