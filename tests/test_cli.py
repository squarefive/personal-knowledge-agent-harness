import tomllib
from pathlib import Path

from personal_knowledge_agent import __main__ as cli


def test_run_cli_processes_input_and_exit(monkeypatch, capsys):
    class FakeAgent:
        def run(self, text):
            return f"reply: {text}"

    inputs = iter(["帮我记一条知识", "/exit"])
    monkeypatch.setattr(cli, "load_config", lambda: object())
    monkeypatch.setattr(cli, "create_agent", lambda config, event_sink=None: FakeAgent())
    monkeypatch.setattr(cli, "create_prompt_session", lambda: object())
    monkeypatch.setattr(cli, "prompt_user", lambda session: next(inputs))
    monkeypatch.setattr(cli, "AsyncJsonlLogger", lambda: type("FakeLogger", (), {"write": lambda self, event: None, "close": lambda self: None})())

    exit_code = cli.run_cli()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "本地 Q&A 知识库 Agent 已启动" in output
    assert "Agent> reply: 帮我记一条知识" in output
    assert "已退出" in output


def test_run_cli_reports_startup_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", lambda: (_ for _ in ()).throw(ValueError("missing key")))

    exit_code = cli.run_cli()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "启动失败：missing key" in captured.err


def test_pyproject_declares_pka_script():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert data["project"]["scripts"]["pka"] == "personal_knowledge_agent.__main__:main"
