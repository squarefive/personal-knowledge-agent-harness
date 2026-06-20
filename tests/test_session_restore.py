from personal_knowledge_agent.agent_context.conversation_sessions import ConversationSessionMetadataRepository, ConversationSessionRestorer, ConversationTranscriptRepository


class FakeSummarizer:
    max_retries = 3

    def __init__(self, *, summary=None, error=None):
        if summary is None:
            summary = "\n".join(
                [
                    "# Session Summary",
                    "",
                    "## Current Goal",
                    "继续实现 session restore。",
                    "",
                    "## User Constraints",
                    "- 保持上下文边界清晰。",
                    "",
                    "## Known Context",
                    "- transcript 已超过预算。",
                    "",
                    "## Completed Work",
                    "- 已生成 summary。",
                    "",
                    "## Next Step",
                    "- 恢复最近消息。",
                    "",
                    "## Boundaries",
                    "- summary 不是用户新请求。",
                    "- summary 不是长期 memory。",
                    "- summary 不是 Q&A 知识来源。",
                ]
            )
        self.summary = summary
        self.error = error
        self.calls = []

    def summarize(self, messages):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.summary, 2


def test_session_restore_returns_full_messages_below_budget(tmp_path):
    transcript = ConversationTranscriptRepository(tmp_path)
    transcript.append_message({"role": "user", "content": "短消息"})
    metadata_store = ConversationSessionMetadataRepository(tmp_path)

    result = ConversationSessionRestorer(
        transcript=transcript,
        metadata_store=metadata_store,
        message_budget_chars=10_000,
    ).restore()

    assert result.mode == "full"
    assert result.messages == [{"role": "user", "content": "短消息"}]
    assert metadata_store.load_or_create().last_restore_mode == "full"


def test_session_restore_uses_summary_and_recent_messages_above_budget(tmp_path):
    transcript = ConversationTranscriptRepository(tmp_path)
    for index in range(5):
        transcript.append_message({"role": "user", "content": f"消息 {index} " + "x" * 20})
    metadata_store = ConversationSessionMetadataRepository(tmp_path)
    summarizer = FakeSummarizer()

    result = ConversationSessionRestorer(
        transcript=transcript,
        metadata_store=metadata_store,
        summarizer=summarizer,
        message_budget_chars=10,
        recent_messages_count=2,
    ).restore()

    assert result.mode == "summary_plus_recent"
    assert result.messages == transcript.load_messages()[-2:]
    assert result.summary == summarizer.summary
    assert not any("[Previous session summary]" in message.get("content", "") for message in result.messages)
    assert (tmp_path / ".sessions/default/summary.md").read_text(encoding="utf-8") == summarizer.summary
    metadata = metadata_store.load_or_create()
    assert metadata.summary_status == "valid"
    assert metadata.summary_attempts == 2


def test_session_restore_falls_back_to_recent_with_warning_when_summary_fails(tmp_path):
    transcript = ConversationTranscriptRepository(tmp_path)
    for index in range(8):
        transcript.append_message({"role": "user", "content": f"消息 {index} " + "x" * 20})
    metadata_store = ConversationSessionMetadataRepository(tmp_path)

    result = ConversationSessionRestorer(
        transcript=transcript,
        metadata_store=metadata_store,
        summarizer=FakeSummarizer(error=RuntimeError("boom")),
        message_budget_chars=10,
        first_messages_count=2,
        recent_messages_count=3,
    ).restore()

    assert result.mode == "first_and_recent"
    assert "自动总结失败" in result.warning
    assert result.summary == result.warning
    assert result.messages == transcript.load_messages()[-3:]
    assert not any("[Session recovery notice]" in message.get("content", "") for message in result.messages)
    metadata = metadata_store.load_or_create()
    assert metadata.summary_status == "failed"
    assert metadata.last_restore_mode == "first_and_recent"
    assert metadata.summary_error == "boom"
