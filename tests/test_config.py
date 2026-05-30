from pathlib import Path

import pytest

from personal_knowledge_agent.config import load_config


def test_load_config_reads_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=test-key\n"
        "DEEPSEEK_MODEL=deepseek-v4-flash\n"
        "KNOWLEDGE_DB_PATH=.knowledge/test.db\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("KNOWLEDGE_DB_PATH", raising=False)

    config = load_config(env_file)

    assert config.deepseek_api_key == "test-key"
    assert config.deepseek_model == "deepseek-v4-flash"
    assert config.knowledge_db_path == Path(".knowledge/test.db")


def test_load_config_requires_api_key(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        load_config(env_file)
