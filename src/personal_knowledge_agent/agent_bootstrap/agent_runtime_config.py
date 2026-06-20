from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_CONTEXT_WINDOW_TOKENS_BY_MODEL = {
    DEFAULT_DEEPSEEK_MODEL: 1_000_000,
}


@dataclass(frozen=True)
class AgentConfig:
    deepseek_api_key: str
    deepseek_model: str
    knowledge_db_path: Path
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS_BY_MODEL[DEFAULT_DEEPSEEK_MODEL]
    dashscope_api_key: str | None = None
    qwen_embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_embedding_model: str = "text-embedding-v4"
    qwen_embedding_dimensions: int = 1024
    qdrant_path: Path = Path(".knowledge/qdrant")
    qdrant_collection: str = "qa_cards"


def load_config(env_path: str | Path = ".env") -> AgentConfig:
    load_dotenv(env_path)

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY is required")

    model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
    context_window_tokens = int(
        os.environ.get(
            "DEEPSEEK_CONTEXT_WINDOW_TOKENS",
            str(_context_window_tokens_for_model(model)),
        )
    )
    db_path = Path(os.environ.get("KNOWLEDGE_DB_PATH", ".knowledge/knowledge.db"))
    embedding_dimensions = int(os.environ.get("QWEN_EMBEDDING_DIMENSIONS", "1024"))
    return AgentConfig(
        deepseek_api_key=api_key,
        deepseek_model=model,
        context_window_tokens=context_window_tokens,
        knowledge_db_path=db_path,
        dashscope_api_key=os.environ.get("DASHSCOPE_API_KEY"),
        qwen_embedding_base_url=os.environ.get(
            "QWEN_EMBEDDING_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        qwen_embedding_model=os.environ.get("QWEN_EMBEDDING_MODEL", "text-embedding-v4"),
        qwen_embedding_dimensions=embedding_dimensions,
        qdrant_path=Path(os.environ.get("QDRANT_PATH", ".knowledge/qdrant")),
        qdrant_collection=os.environ.get("QDRANT_COLLECTION", "qa_cards"),
    )


def _context_window_tokens_for_model(model: str) -> int:
    return DEFAULT_CONTEXT_WINDOW_TOKENS_BY_MODEL.get(model, DEFAULT_CONTEXT_WINDOW_TOKENS_BY_MODEL[DEFAULT_DEEPSEEK_MODEL])
