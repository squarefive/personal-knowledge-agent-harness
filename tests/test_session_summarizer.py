from personal_knowledge_agent.schemas import LLMResponse
from personal_knowledge_agent.agent_context.conversation_sessions import ConversationSessionSummarizer as SessionSummarizer


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
    llm = FakeLLM([RuntimeError("temporary"), LLMResponse(text="当前目标：继续实现。")])

    summary, attempts = SessionSummarizer(llm, max_retries=3).summarize(
        [{"role": "user", "content": "继续"}]
    )

    assert summary == "当前目标：继续实现。"
    assert attempts == 2
    assert llm.calls[0]["tools"] == []
    assert "session summary" in llm.calls[0]["system_prompt"]


def test_session_summarizer_raises_after_max_retries():
    llm = FakeLLM([RuntimeError("first"), LLMResponse(text="")])

    try:
        SessionSummarizer(llm, max_retries=2).summarize([{"role": "user", "content": "继续"}])
    except RuntimeError as exc:
        assert "session summary failed after 2 attempts" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
