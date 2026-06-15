import pytest

from personal_knowledge_agent.agent_context.conversation_sessions import ConversationTranscriptRepository


def test_session_transcript_appends_and_loads_messages(tmp_path):
    transcript = ConversationTranscriptRepository(tmp_path)

    first_id = transcript.append_message({"role": "user", "content": "你好"})
    second_id = transcript.append_message({"role": "assistant", "content": "你好。"})

    assert first_id == 1
    assert second_id == 2
    assert transcript.event_count() == 2
    assert transcript.load_messages() == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好。"},
    ]
    assert transcript.path == tmp_path / ".sessions" / "default" / "transcript.jsonl"


def test_session_transcript_rejects_invalid_session_id(tmp_path):
    with pytest.raises(ValueError):
        ConversationTranscriptRepository(tmp_path, session_id="../escape")


def test_session_transcript_loads_display_messages(tmp_path):
    transcript = ConversationTranscriptRepository(tmp_path, session_id="chat_1")

    transcript.append_message({"role": "user", "content": "你好"})
    transcript.append_message(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "function": {"name": "search_qa_cards"}}],
        }
    )
    transcript.append_message({"role": "tool", "tool_call_id": "call_1", "content": "{\"ok\": true}"})
    transcript.append_message({"role": "assistant", "content": "回答：你好。"})

    messages = transcript.load_display_messages()

    assert messages == [
        {"role": "user", "content": "你好", "created_at": messages[0]["created_at"], "event_id": 1},
        {"role": "assistant", "content": "回答：你好。", "created_at": messages[1]["created_at"], "event_id": 4},
    ]
