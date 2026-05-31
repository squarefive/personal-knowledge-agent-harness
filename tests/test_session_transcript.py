from personal_knowledge_agent.session_transcript import SessionTranscript


def test_session_transcript_appends_and_loads_messages(tmp_path):
    transcript = SessionTranscript(tmp_path)

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
