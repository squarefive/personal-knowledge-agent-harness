from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from ..security.secrets import read_secret

DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_CONTEXT_WINDOW_TOKENS_BY_MODEL = {
    DEFAULT_DEEPSEEK_MODEL: 1_000_000,
}
DEFAULT_ALLOWED_LOGIN_EMAILS = ("1033795760@qq.com",)
DEFAULT_QWEN_EMBEDDING_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_QWEN_EMBEDDING_MODEL = "text-embedding-v4"
DEFAULT_QWEN_EMBEDDING_DIMENSIONS = 1024


@dataclass(frozen=True)
class AgentConfig:
    deepseek_api_key: str
    deepseek_model: str
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS_BY_MODEL[DEFAULT_DEEPSEEK_MODEL]
    database_url: str | None = None
    allowed_login_emails: tuple[str, ...] = DEFAULT_ALLOWED_LOGIN_EMAILS
    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_ssl: bool = True
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str | None = None
    session_secret: str | None = None
    dashscope_api_key: str | None = None
    cloud_only: bool = False
    qwen_embedding_base_url: str = DEFAULT_QWEN_EMBEDDING_BASE_URL
    qwen_embedding_model: str = DEFAULT_QWEN_EMBEDDING_MODEL
    qwen_embedding_dimensions: int = DEFAULT_QWEN_EMBEDDING_DIMENSIONS


def load_config(env_path: str | Path = ".env") -> AgentConfig:
    load_dotenv(env_path)

    api_key = read_secret("DEEPSEEK_API_KEY", required=True)

    model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
    context_window_tokens = int(
        os.environ.get(
            "DEEPSEEK_CONTEXT_WINDOW_TOKENS",
            str(_context_window_tokens_for_model(model)),
        )
    )
    embedding_dimensions = int(os.environ.get("QWEN_EMBEDDING_DIMENSIONS", str(DEFAULT_QWEN_EMBEDDING_DIMENSIONS)))
    return AgentConfig(
        deepseek_api_key=api_key,
        deepseek_model=model,
        context_window_tokens=context_window_tokens,
        database_url=read_secret("DATABASE_URL"),
        allowed_login_emails=_parse_allowed_login_emails(os.environ.get("ALLOWED_LOGIN_EMAILS")),
        smtp_host=os.environ.get("SMTP_HOST"),
        smtp_port=int(os.environ.get("SMTP_PORT", "465")),
        smtp_ssl=_parse_bool(os.environ.get("SMTP_SSL"), default=True, name="SMTP_SSL"),
        smtp_user=os.environ.get("SMTP_USER"),
        smtp_password=read_secret("SMTP_PASSWORD"),
        mail_from=os.environ.get("MAIL_FROM"),
        session_secret=read_secret("SESSION_SECRET"),
        dashscope_api_key=read_secret("DASHSCOPE_API_KEY", allow_empty=True),
        cloud_only=_parse_bool(os.environ.get("PKA_CLOUD_ONLY"), default=False, name="PKA_CLOUD_ONLY"),
        qwen_embedding_base_url=os.environ.get(
            "QWEN_EMBEDDING_BASE_URL",
            DEFAULT_QWEN_EMBEDDING_BASE_URL,
        ),
        qwen_embedding_model=os.environ.get("QWEN_EMBEDDING_MODEL", DEFAULT_QWEN_EMBEDDING_MODEL),
        qwen_embedding_dimensions=embedding_dimensions,
    )


def _context_window_tokens_for_model(model: str) -> int:
    return DEFAULT_CONTEXT_WINDOW_TOKENS_BY_MODEL.get(model, DEFAULT_CONTEXT_WINDOW_TOKENS_BY_MODEL[DEFAULT_DEEPSEEK_MODEL])


def _parse_allowed_login_emails(value: str | None) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_ALLOWED_LOGIN_EMAILS
    emails = tuple(email.strip() for email in value.split(",") if email.strip())
    if not emails:
        raise ValueError("ALLOWED_LOGIN_EMAILS must include at least one email")
    return emails


def _parse_bool(value: str | None, *, default: bool, name: str = "boolean") -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value for {name}: {value!r}")
