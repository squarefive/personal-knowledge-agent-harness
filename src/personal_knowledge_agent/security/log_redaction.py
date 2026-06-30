from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .constants import SecurityConstants as security_constants


def redact_sensitive_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: security_constants.REDACTED if _is_sensitive_key(key) and value is not None else value
        for key, value in values.items()
    }


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in security_constants.SENSITIVE_EXACT_KEYS or any(
        part in normalized for part in security_constants.SENSITIVE_KEY_PARTS
    )


def __getattr__(name: str) -> str:
    if name == "REDACTED":
        return security_constants.REDACTED
    raise AttributeError(name)
