from personal_knowledge_agent.agent_context.conversation_sessions import RuntimeContextCompactor


class FakeSummarizer:
    max_retries = 3

    def __init__(self, *, summary="summary", error=None):
        self.summary = summary
        self.error = error
        self.calls = []

    def summarize(self, messages):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.summary, 1


def test_runtime_context_compactor_writes_summary_and_keeps_recent_messages(tmp_path):
    messages = [{"role": "user", "content": f"消息 {index}"} for index in range(5)]
    summarizer = FakeSummarizer(summary="固定 summary")

    result = RuntimeContextCompactor(
        root=tmp_path,
        summarizer=summarizer,
        recent_messages_count=2,
    ).compact(messages)

    assert result.mode == "summary_plus_recent"
    assert result.messages == messages[-2:]
    assert result.session_summary == "固定 summary"
    assert (tmp_path / ".sessions/default/summary.md").read_text(encoding="utf-8") == "固定 summary"
    assert summarizer.calls[0] == messages


def test_runtime_context_compactor_includes_existing_summary_in_summary_input(tmp_path):
    messages = [{"role": "user", "content": "继续"}]
    summarizer = FakeSummarizer(summary="新 summary")

    RuntimeContextCompactor(root=tmp_path, summarizer=summarizer).compact(
        messages,
        existing_summary="旧 summary",
    )

    assert summarizer.calls[0][0]["content"].startswith("[Existing session summary]")


def test_runtime_context_compactor_returns_recovery_notice_when_summary_fails(tmp_path):
    messages = [{"role": "user", "content": f"消息 {index}"} for index in range(4)]

    result = RuntimeContextCompactor(
        root=tmp_path,
        summarizer=FakeSummarizer(error=RuntimeError("boom")),
        recent_messages_count=2,
    ).compact(messages)

    assert result.mode == "recent_with_recovery_notice"
    assert result.messages == messages[-2:]
    assert "自动总结失败" in result.session_summary
    assert "summary_error: boom" in result.session_summary
    assert not (tmp_path / ".sessions/default/summary.md").exists()
