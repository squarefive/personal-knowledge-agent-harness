from personal_knowledge_agent.agent_context.conversation_sessions import ToolResultCompactor


def test_compact_tool_result_returns_none_below_threshold(tmp_path):
    compactor = ToolResultCompactor(tmp_path, threshold_chars=20)

    record = compactor.compact_tool_result(
        run_id="run-1",
        tool_call_id="call-1",
        tool_name="search_qa_cards",
        result_text="short",
    )

    assert record is None


def test_compact_tool_result_writes_artifact_and_returns_record(tmp_path):
    compactor = ToolResultCompactor(tmp_path, threshold_chars=10)

    record = compactor.compact_tool_result(
        run_id="run-1",
        tool_call_id="call-1",
        tool_name="read_memory",
        result_text="first line\n" + "x" * 20,
    )

    assert record is not None
    assert record.artifact_path == ".sessions/default/artifacts/run-1-call-1.txt"
    assert "read_memory 返回了" in record.summary
    assert "first line" in record.summary
    assert "read_memory" in record.relevance
    assert record.must_keep == []
    assert (tmp_path / record.artifact_path).read_text(encoding="utf-8") == "first line\n" + "x" * 20
