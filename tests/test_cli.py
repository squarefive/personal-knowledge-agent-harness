import tomllib
from pathlib import Path

from personal_knowledge_agent.apps.cli import cli_main as cli
from personal_knowledge_agent.agent_runtime import AgentEvent
from personal_knowledge_agent.tool_runtime import ApprovalRequest


def test_run_cli_processes_input_and_exit(monkeypatch, capsys):
    class FakeAgent:
        def run(self, text):
            return f"reply: {text}"

    inputs = iter(["帮我记一条知识", "/exit"])
    monkeypatch.setattr(cli, "load_config", lambda: object())
    monkeypatch.setattr(cli, "create_agent", lambda config, event_sink=None, approval_callback=None: FakeAgent())
    monkeypatch.setattr(cli, "create_prompt_session", lambda: object())
    monkeypatch.setattr(cli, "prompt_user", lambda session: next(inputs))
    monkeypatch.setattr(cli, "AgentEventJsonlLogger", lambda: type("FakeLogger", (), {"write": lambda self, event: None, "close": lambda self: None})())

    exit_code = cli.run_cli()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "本地 Q&A 知识库 Agent 已启动" in output
    assert "Agent> reply: 帮我记一条知识" in output
    assert "已退出" in output


def test_run_cli_does_not_log_answer_delta(monkeypatch):
    class FakeAgent:
        def __init__(self, event_sink):
            self.event_sink = event_sink

        def run(self, text):
            self.event_sink(AgentEvent(run_id="run_1", event_type="answer_delta", payload={"text": "你"}))
            self.event_sink(
                AgentEvent(run_id="run_1", event_type="final_answer_generated", payload={"answer": "你好"})
            )
            return "你好"

    written = []
    inputs = iter(["你好", "/exit"])
    monkeypatch.setattr(cli, "load_config", lambda: object())
    monkeypatch.setattr(
        cli,
        "create_agent",
        lambda config, event_sink=None, approval_callback=None: FakeAgent(event_sink),
    )
    monkeypatch.setattr(cli, "create_prompt_session", lambda: object())
    monkeypatch.setattr(cli, "prompt_user", lambda session: next(inputs))
    monkeypatch.setattr(
        cli,
        "AgentEventJsonlLogger",
        lambda: type("FakeLogger", (), {"write": lambda self, event: written.append(event), "close": lambda self: None})(),
    )

    assert cli.run_cli() == 0

    assert [event.event_type for event in written] == ["final_answer_generated"]


def test_run_cli_reports_startup_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", lambda: (_ for _ in ()).throw(ValueError("missing key")))

    exit_code = cli.run_cli()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "启动失败：missing key" in captured.err


def test_run_cli_continues_after_agent_run_error(monkeypatch, capsys):
    class FakeAgent:
        def run(self, text):
            raise RuntimeError("temporary llm failure")

    inputs = iter(["你好", "/exit"])
    monkeypatch.setattr(cli, "load_config", lambda: object())
    monkeypatch.setattr(cli, "create_agent", lambda config, event_sink=None, approval_callback=None: FakeAgent())
    monkeypatch.setattr(cli, "create_prompt_session", lambda: object())
    monkeypatch.setattr(cli, "prompt_user", lambda session: next(inputs))
    monkeypatch.setattr(cli, "AgentEventJsonlLogger", lambda: type("FakeLogger", (), {"write": lambda self, event: None, "close": lambda self: None})())

    exit_code = cli.run_cli()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "模型服务暂时不可用，本轮没有完成" in output
    assert "已退出" in output


def test_pyproject_declares_pka_script():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert data["project"]["scripts"]["pka"] == "personal_knowledge_agent.__main__:main"


def test_approve_tool_call_allows_only_yes(capsys):
    class FakeSession:
        def __init__(self, answer):
            self.answer = answer

        def prompt(self, text):
            self.prompt_text = text
            return self.answer

    request = ApprovalRequest(
        tool_name="delete_qa_card",
        arguments={"card_id": "qa_1"},
        reason="danger",
    )

    assert cli.approve_tool_call(FakeSession("yes"), request) is True
    assert cli.approve_tool_call(FakeSession("no"), request) is False
    output = capsys.readouterr().out
    assert "高风险工具请求需要确认" in output
    assert "delete_qa_card" in output


def test_main_dispatches_web_subcommand(monkeypatch):
    called = {}

    def fake_web_main(argv):
        called["argv"] = argv
        return 0

    import personal_knowledge_agent.apps.web.web_main as web_main_module

    monkeypatch.setattr(web_main_module, "main", fake_web_main)

    assert cli.main(["web", "--no-open"]) == 0
    assert called["argv"] == ["--no-open"]


def test_main_defaults_to_cli(monkeypatch):
    monkeypatch.setattr(cli, "run_cli", lambda: 0)

    assert cli.main([]) == 0
