from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from personal_knowledge_agent.security.token_hashing import (
    generate_token,
    generate_verification_code,
    hash_token,
    verify_token,
)

from .auth_models import (
    AuthFailure,
    AuthSessionRecord,
    AuthUser,
    IssuedLoginCode,
    LoginCodeRecord,
    VerifiedLoginSession,
)

LOGIN_CODE_PURPOSE = "login"
LLM_PROVIDER_USER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-_]+$")
MAX_LLM_PROVIDER_USER_ID_LENGTH = 512


class AuthRepository(Protocol):
    def get_user_by_email(self, email: str) -> AuthUser | None: ...

    def create_user(self, user: AuthUser) -> AuthUser: ...

    def save_login_code(self, login_code: LoginCodeRecord) -> None: ...

    def get_latest_login_code(self, email: str, purpose: str) -> LoginCodeRecord | None: ...

    def increment_login_code_attempt(self, login_code_id: str) -> None: ...

    def consume_login_code(self, login_code_id: str, consumed_at: datetime) -> None: ...

    def create_auth_session(self, session: AuthSessionRecord) -> None: ...


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        *,
        allowed_login_emails: set[str],
        code_ttl: timedelta = timedelta(minutes=10),
        session_ttl: timedelta = timedelta(days=30),
        max_attempts: int = 5,
        clock: Callable[[], datetime] | None = None,
        verification_code_factory: Callable[[], str] = generate_verification_code,
        token_factory: Callable[[], str] = generate_token,
        user_id_factory: Callable[[], str] | None = None,
        llm_provider_user_id_factory: Callable[[], str] | None = None,
        login_code_id_factory: Callable[[], str] | None = None,
        session_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        self._repository = repository
        self._allowed_login_emails = {normalize_email(email) for email in allowed_login_emails}
        self._code_ttl = code_ttl
        self._session_ttl = session_ttl
        self._max_attempts = max_attempts
        self._clock = clock or (lambda: datetime.now(UTC))
        self._verification_code_factory = verification_code_factory
        self._token_factory = token_factory
        self._user_id_factory = user_id_factory or (lambda: f"usr_{generate_token(18)}")
        self._llm_provider_user_id_factory = llm_provider_user_id_factory or (lambda: f"llm_{generate_token(18)}")
        self._login_code_id_factory = login_code_id_factory or (lambda: f"lc_{generate_token(18)}")
        self._session_id_factory = session_id_factory or (lambda: f"sess_{generate_token(18)}")

    def request_login_code(self, email: str) -> IssuedLoginCode | AuthFailure:
        normalized_email = normalize_email(email)
        if normalized_email not in self._allowed_login_emails:
            return AuthFailure(
                ok=False,
                error_code="email_not_allowed",
                message="email is not allowed to log in",
                email=normalized_email,
            )

        now = self._now()
        user = self._ensure_user(normalized_email, now)
        plaintext_code = self._verification_code_factory()
        expires_at = now + self._code_ttl

        self._repository.save_login_code(
            LoginCodeRecord(
                login_code_id=self._login_code_id_factory(),
                user_id=user.user_id,
                email=normalized_email,
                code_hash=hash_token(plaintext_code),
                expires_at=expires_at,
                purpose=LOGIN_CODE_PURPOSE,
                consumed=False,
                attempt_count=0,
                created_at=now,
            )
        )
        return IssuedLoginCode(ok=True, email=normalized_email, plaintext_code=plaintext_code, expires_at=expires_at)

    def verify_login_code(self, email: str, code: str) -> VerifiedLoginSession | AuthFailure:
        normalized_email = normalize_email(email)
        if normalized_email not in self._allowed_login_emails:
            return AuthFailure(
                ok=False,
                error_code="email_not_allowed",
                message="email is not allowed to log in",
                email=normalized_email,
            )

        login_code = self._repository.get_latest_login_code(normalized_email, LOGIN_CODE_PURPOSE)
        if login_code is None:
            return AuthFailure(ok=False, error_code="login_code_not_found", message="login code not found", email=normalized_email)

        now = self._now()
        if login_code.consumed:
            return AuthFailure(ok=False, error_code="login_code_consumed", message="login code has already been used", email=normalized_email)
        if login_code.expires_at <= now:
            return AuthFailure(ok=False, error_code="login_code_expired", message="login code has expired", email=normalized_email)
        if login_code.attempt_count >= self._max_attempts:
            return AuthFailure(ok=False, error_code="too_many_attempts", message="too many login code attempts", email=normalized_email)
        if not verify_token(code.strip(), login_code.code_hash):
            self._repository.increment_login_code_attempt(login_code.login_code_id)
            return AuthFailure(ok=False, error_code="invalid_login_code", message="login code is invalid", email=normalized_email)

        user = self._repository.get_user_by_email(normalized_email)
        if user is None:
            return AuthFailure(ok=False, error_code="user_not_found", message="user not found for login code", email=normalized_email)

        self._repository.consume_login_code(login_code.login_code_id, now)
        session_token = self._token_factory()
        session_expires_at = now + self._session_ttl
        self._repository.create_auth_session(
            AuthSessionRecord(
                session_id=self._session_id_factory(),
                user_id=user.user_id,
                token_hash=hash_token(session_token),
                expires_at=session_expires_at,
                created_at=now,
            )
        )

        return VerifiedLoginSession(
            ok=True,
            email=normalized_email,
            user_id=user.user_id,
            llm_provider_user_id=user.llm_provider_user_id,
            session_token=session_token,
            expires_at=session_expires_at,
        )

    def _ensure_user(self, email: str, now: datetime) -> AuthUser:
        existing = self._repository.get_user_by_email(email)
        if existing is not None:
            return existing

        user_id = self._user_id_factory()
        llm_provider_user_id = self._llm_provider_user_id_factory()
        _validate_non_private_llm_user_id(email, llm_provider_user_id)
        return self._repository.create_user(
            AuthUser(
                user_id=user_id,
                email=email,
                llm_provider_user_id=llm_provider_user_id,
                created_at=now,
                updated_at=now,
            )
        )

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            return now.replace(tzinfo=UTC)
        return now


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _validate_non_private_llm_user_id(email: str, llm_provider_user_id: str) -> None:
    normalized_email = normalize_email(email)
    local_part = normalized_email.split("@", 1)[0]
    normalized_llm_id = llm_provider_user_id.lower()
    if not llm_provider_user_id:
        raise ValueError("llm_provider_user_id must not be empty")
    if len(llm_provider_user_id) > MAX_LLM_PROVIDER_USER_ID_LENGTH:
        raise ValueError("llm_provider_user_id must be 512 characters or fewer")
    if normalized_email in normalized_llm_id or local_part in normalized_llm_id:
        raise ValueError("llm_provider_user_id must not contain email-derived values")
    if not LLM_PROVIDER_USER_ID_PATTERN.fullmatch(llm_provider_user_id):
        raise ValueError("llm_provider_user_id must match [a-zA-Z0-9\\-_]+")
