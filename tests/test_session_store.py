from personal_knowledge_agent.schemas import SessionSummary
from personal_knowledge_agent.session_store import SessionStore


def test_load_current_returns_empty_when_missing(tmp_path):
    summary = SessionStore(tmp_path).load_current()

    assert summary == SessionSummary()


def test_write_and_load_current_session(tmp_path):
    store = SessionStore(tmp_path)
    original = SessionSummary(
        current_goal="设计 Agent memory 管理。",
        confirmed_decisions=["Q&A 和 Agent memory 分开。"],
        open_questions=["CLI 如何展示待确认候选？"],
        next_steps=["实现 memory index 读取。"],
    )

    path = store.write_current(original)
    loaded = store.load_current()

    assert path == tmp_path / ".session" / "current.md"
    assert loaded == original


def test_write_current_overwrites_existing_session(tmp_path):
    store = SessionStore(tmp_path)
    store.write_current(SessionSummary(current_goal="旧目标"))

    store.write_current(SessionSummary(current_goal="新目标"))

    assert store.load_current().current_goal == "新目标"


def test_write_artifact_creates_safe_file(tmp_path):
    store = SessionStore(tmp_path)

    path = store.write_artifact(
        run_id="run 123",
        artifact_name="tool/result.txt",
        content="large output",
    )

    assert path == tmp_path / ".session" / "artifacts" / "run-123-tool-result.txt"
    assert path.read_text(encoding="utf-8") == "large output"
