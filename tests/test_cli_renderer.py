from io import StringIO

from personal_knowledge_agent.cli_renderer import CliRenderer
from personal_knowledge_agent.events import AgentEvent


def test_cli_renderer_truncates_long_text():
    stream = StringIO()
    renderer = CliRenderer(stream=stream, max_text_length=12)

    renderer.render(
        AgentEvent(
            run_id="run_1",
            event_type="user_input_received",
            payload={"user_input": "abcdefghijklmnopqrstuvwxyz"},
        )
    )

    output = stream.getvalue()
    assert "abcdefghi..." in output
    assert "abcdefghijklmnopqrstuvwxyz" not in output


def test_cli_renderer_renders_tool_result():
    stream = StringIO()
    renderer = CliRenderer(stream=stream)

    renderer.render(
        AgentEvent(
            run_id="run_1",
            event_type="tool_call_finished",
            payload={
                "tool_name": "search_qa_cards",
                "duration_ms": 12,
                "output": {"ok": True, "cards": [{"card_id": "qa_1"}]},
            },
        )
    )

    output = stream.getvalue()
    assert "Tool Result: search_qa_cards in 12ms" in output
    assert '"card_id": "qa_1"' in output
