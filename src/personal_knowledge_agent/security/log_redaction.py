from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"
SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "cookie",
    "database_url",
    "password",
    "secret",
    "session",
    "smtp_password",
    "token",
)


def redact_sensitive_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: REDACTED if _is_sensitive_key(key) and value is not None else value
        for key, value in values.items()
    }


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in {"code", "verification_code"} or any(part in normalized for part in SENSITIVE_KEY_PARTS)
