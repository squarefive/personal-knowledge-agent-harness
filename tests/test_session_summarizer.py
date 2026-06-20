from personal_knowledge_agent.llm_clients import LLMResponse
from personal_knowledge_agent.agent_context.conversation_sessions import ConversationSessionSummarizer

VALID_SUMMARY = "\n".join(
    [
        "# Session Summary",
        "",
        "## Current Goal",
        "继续实现。",
        "",
        "## User Constraints",
        "- 保持边界。",
        "",
        "## Known Context",
        "- 有历史消息。",
        "",
        "## Completed Work",
        "- 已整理上下文。",
        "",
        "## Next Step",
        "- 继续。",
        "",
        "## Boundaries",
        "- summary 不是用户新请求。",
        "- summary 不是长期 memory。",
        "- summary 不是 Q&A 知识来源。",
    ]
)


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, *, messages, tools, system_prompt):
        self.calls.append({"messages": messages, "tools": tools, "system_prompt": system_prompt})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_session_summarizer_returns_summary_with_attempt_count():
    llm = FakeLLM([RuntimeError("temporary"), LLMResponse(text=VALID_SUMMARY)])

    summary, attempts = ConversationSessionSummarizer(llm, max_retries=3).summarize(
        [{"role": "user", "content": "继续"}]
    )

    assert summary == VALID_SUMMARY
    assert attempts == 2
    assert llm.calls[0]["tools"] == []
    assert "session summary" in llm.calls[0]["system_prompt"]


def test_session_summarizer_raises_after_max_retries():
    llm = FakeLLM([RuntimeError("first"), LLMResponse(text="")])

    try:
        ConversationSessionSummarizer(llm, max_retries=2).summarize([{"role": "user", "content": "继续"}])
    except RuntimeError as exc:
        assert "session summary failed after 2 attempts" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_session_summarizer_retries_when_summary_misses_required_heading():
    llm = FakeLLM([LLMResponse(text="当前目标：继续实现。"), LLMResponse(text=VALID_SUMMARY)])

    summary, attempts = ConversationSessionSummarizer(llm, max_retries=2).summarize(
        [{"role": "user", "content": "继续"}]
    )

    assert summary == VALID_SUMMARY
    assert attempts == 2


def test_session_summarizer_rejects_missing_boundary_statement():
    invalid_summary = VALID_SUMMARY.replace("- summary 不是长期 memory。\n", "")
    llm = FakeLLM([LLMResponse(text=invalid_summary)])

    try:
        ConversationSessionSummarizer(llm, max_retries=1).summarize([{"role": "user", "content": "继续"}])
    except RuntimeError as exc:
        assert "session summary failed after 1 attempts" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
