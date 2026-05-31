from personal_knowledge_agent.session_memory import SessionMetadataStore


def test_session_metadata_load_or_create_writes_default_metadata(tmp_path):
    store = SessionMetadataStore(tmp_path, model="deepseek-test")

    metadata = store.load_or_create()

    assert metadata.session_id == "default"
    assert metadata.model == "deepseek-test"
    assert metadata.transcript_path == ".sessions/default/transcript.jsonl"
    assert metadata.summary_path == ".sessions/default/summary.md"
    assert metadata.artifacts_dir == ".sessions/default/artifacts"
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
