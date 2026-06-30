from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from ..security.secrets import read_secret
from .constants import AgentBootstrapConstants as bootstrap_constants


@dataclass(frozen=True)
class AgentConfig:
    deepseek_api_key: str
    deepseek_model: str
    context_window_tokens: int = bootstrap_constants.DEFAULT_CONTEXT_WINDOW_TOKENS_BY_MODEL[
        bootstrap_constants.DEFAULT_DEEPSEEK_MODEL
    ]
    database_url: str | None = None
    allowed_login_emails: tuple[str, ...] = bootstrap_constants.DEFAULT_ALLOWED_LOGIN_EMAILS
    smtp_host: str | None = None
    smtp_port: int = bootstrap_constants.DEFAULT_SMTP_PORT
    smtp_ssl: bool = True
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str | None = None
    session_secret: str | None = None
    dashscope_api_key: str | None = None
    cloud_only: bool = False
    qwen_embedding_base_url: str = bootstrap_constants.DEFAULT_QWEN_EMBEDDING_BASE_URL
    qwen_embedding_model: str = bootstrap_constants.DEFAULT_QWEN_EMBEDDING_MODEL
    qwen_embedding_dimensions: int = bootstrap_constants.DEFAULT_QWEN_EMBEDDING_DIMENSIONS


def load_config(env_path: str | Path = ".env") -> AgentConfig:
    load_dotenv(env_path)

    api_key = read_secret(bootstrap_constants.DEEPSEEK_API_KEY_ENV, required=True)

    model = os.environ.get(bootstrap_constants.DEEPSEEK_MODEL_ENV, bootstrap_constants.DEFAULT_DEEPSEEK_MODEL)
    context_window_tokens = int(
        os.environ.get(
            bootstrap_constants.DEEPSEEK_CONTEXT_WINDOW_TOKENS_ENV,
            str(_context_window_tokens_for_model(model)),
        )
    )
    embedding_dimensions = int(
        os.environ.get(
            bootstrap_constants.QWEN_EMBEDDING_DIMENSIONS_ENV,
            str(bootstrap_constants.DEFAULT_QWEN_EMBEDDING_DIMENSIONS),
        )
    )
    return AgentConfig(
        deepseek_api_key=api_key,
        deepseek_model=model,
        context_window_tokens=context_window_tokens,
        database_url=read_secret(bootstrap_constants.DATABASE_URL_ENV),
        allowed_login_emails=_parse_allowed_login_emails(
            os.environ.get(bootstrap_constants.ALLOWED_LOGIN_EMAILS_ENV)
        ),
        smtp_host=os.environ.get(bootstrap_constants.SMTP_HOST_ENV),
        smtp_port=int(os.environ.get(bootstrap_constants.SMTP_PORT_ENV, str(bootstrap_constants.DEFAULT_SMTP_PORT))),
        smtp_ssl=_parse_bool(
            os.environ.get(bootstrap_constants.SMTP_SSL_ENV),
            default=True,
            name=bootstrap_constants.SMTP_SSL_ENV,
        ),
        smtp_user=os.environ.get(bootstrap_constants.SMTP_USER_ENV),
        smtp_password=read_secret(bootstrap_constants.SMTP_PASSWORD_ENV),
        mail_from=os.environ.get(bootstrap_constants.MAIL_FROM_ENV),
        session_secret=read_secret(bootstrap_constants.SESSION_SECRET_ENV),
        dashscope_api_key=read_secret(bootstrap_constants.DASHSCOPE_API_KEY_ENV, allow_empty=True),
        cloud_only=_parse_bool(
            os.environ.get(bootstrap_constants.PKA_CLOUD_ONLY_ENV),
            default=False,
            name=bootstrap_constants.PKA_CLOUD_ONLY_ENV,
        ),
        qwen_embedding_base_url=os.environ.get(
            bootstrap_constants.QWEN_EMBEDDING_BASE_URL_ENV,
            bootstrap_constants.DEFAULT_QWEN_EMBEDDING_BASE_URL,
        ),
        qwen_embedding_model=os.environ.get(
            bootstrap_constants.QWEN_EMBEDDING_MODEL_ENV,
            bootstrap_constants.DEFAULT_QWEN_EMBEDDING_MODEL,
        ),
        qwen_embedding_dimensions=embedding_dimensions,
    )


def _context_window_tokens_for_model(model: str) -> int:
    return bootstrap_constants.DEFAULT_CONTEXT_WINDOW_TOKENS_BY_MODEL.get(
        model,
        bootstrap_constants.DEFAULT_CONTEXT_WINDOW_TOKENS_BY_MODEL[bootstrap_constants.DEFAULT_DEEPSEEK_MODEL],
    )


def _parse_allowed_login_emails(value: str | None) -> tuple[str, ...]:
    if value is None:
        return bootstrap_constants.DEFAULT_ALLOWED_LOGIN_EMAILS
    emails = tuple(email.strip() for email in value.split(",") if email.strip())
    if not emails:
        raise ValueError(f"{bootstrap_constants.ALLOWED_LOGIN_EMAILS_ENV} must include at least one email")
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
