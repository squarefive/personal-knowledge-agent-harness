from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    email: str
    llm_provider_user_id: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class LoginCodeRecord:
    login_code_id: str
    user_id: str
    email: str
    code_hash: str
    expires_at: datetime
    purpose: str
    consumed: bool
    attempt_count: int
    created_at: datetime


@dataclass(frozen=True)
class AuthSessionRecord:
    session_id: str
    user_id: str
    token_hash: str
    expires_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class AuthSessionWithUserRecord:
    session_id: str
    user_id: str
    email: str
    llm_provider_user_id: str
    expires_at: datetime
    revoked_at: datetime | None
    last_seen_at: datetime | None


@dataclass(frozen=True)
class AuthenticatedSession:
    ok: bool
    user_id: str
    email: str
    llm_provider_user_id: str
    session_id: str
    expires_at: datetime


@dataclass(frozen=True)
class IssuedLoginCode:
    ok: bool
    email: str
    plaintext_code: str
    expires_at: datetime


@dataclass(frozen=True)
class VerifiedLoginSession:
    ok: bool
    email: str
    user_id: str
    llm_provider_user_id: str
    session_token: str
    expires_at: datetime


@dataclass(frozen=True)
class AuthFailure:
    ok: bool
    error_code: str
    message: str
    email: str | None = None
