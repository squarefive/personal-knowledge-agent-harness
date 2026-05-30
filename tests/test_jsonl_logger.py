import json

from personal_knowledge_agent.events import AgentEvent
from personal_knowledge_agent.jsonl_logger import AsyncJsonlLogger


def test_async_jsonl_logger_writes_full_user_input(tmp_path):
    log_path = tmp_path / "agent.log"
    logger = AsyncJsonlLogger(path=log_path)
    user_input = "原始输入" * 200

    logger.write(
        AgentEvent(
            run_id="run_1",
            event_type="user_input_received",
            payload={"user_input": user_input},
        )
    )
    logger.close()

    line = log_path.read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert payload["run_id"] == "run_1"
    assert payload["event_type"] == "user_input_received"
    assert payload["user_input"] == user_input


def test_async_jsonl_logger_drops_when_queue_is_full(tmp_path, capsys):
    log_path = tmp_path / "agent.log"
    logger = AsyncJsonlLogger(path=log_path, max_queue_size=1)
    logger._started = True  # noqa: SLF001
    logger._queue.put_nowait(  # noqa: SLF001
        AgentEvent(run_id="run_1", event_type="user_input_received", payload={})
    )

    logger.write(AgentEvent(run_id="run_2", event_type="user_input_received", payload={}))

    captured = capsys.readouterr()
    assert "agent log queue full" in captured.err
