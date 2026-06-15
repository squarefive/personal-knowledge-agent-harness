from pathlib import Path

import pytest

from personal_knowledge_agent.agent_bootstrap import load_config


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
    assert config.dashscope_api_key is None
    assert config.qwen_embedding_base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert config.qwen_embedding_model == "text-embedding-v4"
    assert config.qwen_embedding_dimensions == 1024
    assert config.qdrant_path == Path(".knowledge/qdrant")
    assert config.qdrant_collection == "qa_cards"


def test_load_config_reads_v04_embedding_settings(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=test-key\n"
        "DASHSCOPE_API_KEY=dashscope-key\n"
        "QWEN_EMBEDDING_BASE_URL=https://example.test/v1\n"
        "QWEN_EMBEDDING_MODEL=text-embedding-v4\n"
        "QWEN_EMBEDDING_DIMENSIONS=1024\n"
        "QDRANT_PATH=.knowledge/test-qdrant\n"
        "QDRANT_COLLECTION=test_cards\n",
        encoding="utf-8",
    )

    for name in (
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
        "QWEN_EMBEDDING_BASE_URL",
        "QWEN_EMBEDDING_MODEL",
        "QWEN_EMBEDDING_DIMENSIONS",
        "QDRANT_PATH",
        "QDRANT_COLLECTION",
    ):
        monkeypatch.delenv(name, raising=False)

    config = load_config(env_file)

    assert config.dashscope_api_key == "dashscope-key"
    assert config.qwen_embedding_base_url == "https://example.test/v1"
    assert config.qwen_embedding_model == "text-embedding-v4"
    assert config.qwen_embedding_dimensions == 1024
    assert config.qdrant_path == Path(".knowledge/test-qdrant")
    assert config.qdrant_collection == "test_cards"


def test_load_config_requires_api_key(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        load_config(env_file)
