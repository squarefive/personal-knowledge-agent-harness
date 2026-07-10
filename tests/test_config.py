import pytest

from personal_knowledge_agent.agent_bootstrap import load_config
from personal_knowledge_agent.apps.cli import cli_main


def test_load_config_reads_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=test-key\n"
        "DEEPSEEK_MODEL=deepseek-v4-flash\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY_FILE", raising=False)

    config = load_config(env_file)

    assert config.deepseek_api_key == "test-key"
    assert config.deepseek_model == "deepseek-v4-flash"
    assert config.context_window_tokens == 1_000_000
    assert config.database_url is None
    assert config.allowed_login_emails == ("1033795760@qq.com",)
    assert config.smtp_host is None
    assert config.smtp_port == 465
    assert config.smtp_ssl is True
    assert config.smtp_user is None
    assert config.smtp_password is None
    assert config.mail_from is None
    assert config.session_secret is None
    assert config.dashscope_api_key is None
    assert config.cloud_only is False
    assert config.qwen_embedding_base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert config.qwen_embedding_model == "text-embedding-v4"
    assert config.qwen_embedding_dimensions == 1024


def test_disabled_cli_points_to_cloud_web_entrypoint(capsys):
    exit_code = cli_main.main([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "本地 CLI Agent runtime 已移除" in captured.out
    assert "pka web" in captured.out
    assert "./run-web" in captured.out


def test_load_config_reads_v04_embedding_settings(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=test-key\n"
        "DASHSCOPE_API_KEY=dashscope-key\n"
        "QWEN_EMBEDDING_BASE_URL=https://example.test/v1\n"
        "QWEN_EMBEDDING_MODEL=text-embedding-v4\n"
        "QWEN_EMBEDDING_DIMENSIONS=1024\n",
        encoding="utf-8",
    )

    for name in (
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
        "QWEN_EMBEDDING_BASE_URL",
        "QWEN_EMBEDDING_MODEL",
        "QWEN_EMBEDDING_DIMENSIONS",
        "DEEPSEEK_CONTEXT_WINDOW_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)

    config = load_config(env_file)

    assert config.dashscope_api_key == "dashscope-key"
    assert config.qwen_embedding_base_url == "https://example.test/v1"
    assert config.qwen_embedding_model == "text-embedding-v4"
    assert config.qwen_embedding_dimensions == 1024


def test_load_config_reads_context_window_override(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=test-key\n"
        "DEEPSEEK_CONTEXT_WINDOW_TOKENS=123456\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_CONTEXT_WINDOW_TOKENS", raising=False)

    config = load_config(env_file)

    assert config.context_window_tokens == 123456


def test_load_config_reads_cloud_runtime_settings(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=test-key\n"
        "DATABASE_URL=postgresql://example\n"
        "ALLOWED_LOGIN_EMAILS=one@example.test, two@example.test\n"
        "SMTP_HOST=smtp.example.test\n"
        "SMTP_PORT=587\n"
        "SMTP_SSL=false\n"
        "SMTP_USER=smtp-user\n"
        "SMTP_PASSWORD=smtp-password\n"
        "MAIL_FROM=agent@example.test\n"
        "SESSION_SECRET=session-secret\n"
        "PKA_CLOUD_ONLY=true\n",
        encoding="utf-8",
    )

    for name in (
        "DEEPSEEK_API_KEY",
        "DATABASE_URL",
        "DATABASE_URL_FILE",
        "ALLOWED_LOGIN_EMAILS",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_SSL",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_PASSWORD_FILE",
        "MAIL_FROM",
        "SESSION_SECRET",
        "SESSION_SECRET_FILE",
        "PKA_CLOUD_ONLY",
    ):
        monkeypatch.delenv(name, raising=False)

    config = load_config(env_file)

    assert config.database_url == "postgresql://example"
    assert config.allowed_login_emails == ("one@example.test", "two@example.test")
    assert config.smtp_host == "smtp.example.test"
    assert config.smtp_port == 587
    assert config.smtp_ssl is False
    assert config.smtp_user == "smtp-user"
    assert config.smtp_password == "smtp-password"
    assert config.mail_from == "agent@example.test"
    assert config.session_secret == "session-secret"
    assert config.cloud_only is True


def test_load_config_prefers_secret_files(tmp_path, monkeypatch):
    deepseek_file = tmp_path / "deepseek.txt"
    database_file = tmp_path / "database.txt"
    smtp_file = tmp_path / "smtp.txt"
    session_file = tmp_path / "session.txt"
    dashscope_file = tmp_path / "dashscope.txt"
    deepseek_file.write_text("deepseek-file\n", encoding="utf-8")
    database_file.write_text("postgresql://from-file\n", encoding="utf-8")
    smtp_file.write_text("smtp-file\n", encoding="utf-8")
    session_file.write_text("session-file\n", encoding="utf-8")
    dashscope_file.write_text("dashscope-file\n", encoding="utf-8")

    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=deepseek-env\n"
        f"DEEPSEEK_API_KEY_FILE={deepseek_file}\n"
        "DATABASE_URL=postgresql://from-env\n"
        f"DATABASE_URL_FILE={database_file}\n"
        "SMTP_PASSWORD=smtp-env\n"
        f"SMTP_PASSWORD_FILE={smtp_file}\n"
        "SESSION_SECRET=session-env\n"
        f"SESSION_SECRET_FILE={session_file}\n"
        "DASHSCOPE_API_KEY=dashscope-env\n"
        f"DASHSCOPE_API_KEY_FILE={dashscope_file}\n",
        encoding="utf-8",
    )

    for name in (
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_API_KEY_FILE",
        "DATABASE_URL",
        "DATABASE_URL_FILE",
        "SMTP_PASSWORD",
        "SMTP_PASSWORD_FILE",
        "SESSION_SECRET",
        "SESSION_SECRET_FILE",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_API_KEY_FILE",
    ):
        monkeypatch.delenv(name, raising=False)

    config = load_config(env_file)

    assert config.deepseek_api_key == "deepseek-file"
    assert config.database_url == "postgresql://from-file"
    assert config.smtp_password == "smtp-file"
    assert config.session_secret == "session-file"
    assert config.dashscope_api_key == "dashscope-file"


def test_load_config_requires_api_key(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY_FILE", raising=False)

    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        load_config(env_file)
