from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_token(byte_count: int = 32) -> str:
    if byte_count <= 0:
        raise ValueError("byte_count must be positive")
    return secrets.token_urlsafe(byte_count)


def generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_token(token: str) -> str:
    if not token:
        raise ValueError("token must not be empty")
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def verify_token(token: str, expected_hash: str) -> bool:
    if not token or not expected_hash:
        return False
    return hmac.compare_digest(hash_token(token), expected_hash)
