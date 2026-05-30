from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AgentConfig:
    deepseek_api_key: str
    deepseek_model: str
    knowledge_db_path: Path


def load_config(env_path: str | Path = ".env") -> AgentConfig:
    load_dotenv(env_path)

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY is required")

    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    db_path = Path(os.environ.get("KNOWLEDGE_DB_PATH", ".knowledge/knowledge.db"))
    return AgentConfig(
        deepseek_api_key=api_key,
        deepseek_model=model,
        knowledge_db_path=db_path,
    )
