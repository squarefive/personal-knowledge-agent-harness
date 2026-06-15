from personal_knowledge_agent.agent_context.conversation_sessions import ConversationSessionMetadataRepository as SessionMetadataStore, ConversationSessionRestorer as SessionRestore, ConversationTranscriptRepository as SessionTranscript


class FakeSummarizer:
    max_retries = 3

    def __init__(self, *, summary="压缩摘要", error=None):
        self.summary = summary
        self.error = error
        self.calls = []

    def summarize(self, messages):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.summary, 2


def test_session_restore_returns_full_messages_below_budget(tmp_path):
    transcript = SessionTranscript(tmp_path)
    transcript.append_message({"role": "user", "content": "短消息"})
    metadata_store = SessionMetadataStore(tmp_path)

    result = SessionRestore(
        transcript=transcript,
        metadata_store=metadata_store,
        message_budget_chars=10_000,
    ).restore()

    assert result.mode == "full"
    assert result.messages == [{"role": "user", "content": "短消息"}]
    assert metadata_store.load_or_create().last_restore_mode == "full"


def test_session_restore_uses_summary_and_recent_messages_above_budget(tmp_path):
    transcript = SessionTranscript(tmp_path)
    for index in range(5):
        transcript.append_message({"role": "user", "content": f"消息 {index} " + "x" * 20})
    metadata_store = SessionMetadataStore(tmp_path)
    summarizer = FakeSummarizer(summary="当前目标：继续实现 session restore。")

    result = SessionRestore(
        transcript=transcript,
        metadata_store=metadata_store,
        summarizer=summarizer,
        message_budget_chars=10,
        recent_messages_count=2,
    ).restore()

    assert result.mode == "summary_plus_recent"
    assert result.messages[0]["content"].startswith("[Previous session summary]")
    assert result.messages[-2:] == transcript.load_messages()[-2:]
    assert (tmp_path / ".sessions/default/summary.md").read_text(encoding="utf-8") == "当前目标：继续实现 session restore。"
    metadata = metadata_store.load_or_create()
    assert metadata.summary_status == "valid"
    assert metadata.summary_attempts == 2


def test_session_restore_falls_back_to_first_and_recent_when_summary_fails(tmp_path):
    transcript = SessionTranscript(tmp_path)
    for index in range(8):
        transcript.append_message({"role": "user", "content": f"消息 {index} " + "x" * 20})
    metadata_store = SessionMetadataStore(tmp_path)

    result = SessionRestore(
        transcript=transcript,
        metadata_store=metadata_store,
        summarizer=FakeSummarizer(error=RuntimeError("boom")),
        message_budget_chars=10,
        first_messages_count=2,
        recent_messages_count=3,
    ).restore()

    assert result.mode == "first_and_recent"
    assert "自动总结失败" in result.warning
    assert result.messages[:2] == transcript.load_messages()[:2]
    assert result.messages[-3:] == transcript.load_messages()[-3:]
    metadata = metadata_store.load_or_create()
    assert metadata.summary_status == "failed"
    assert metadata.last_restore_mode == "first_and_recent"
    assert metadata.summary_error == "boom"
