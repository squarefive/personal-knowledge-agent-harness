from __future__ import annotations

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
    AuthenticatedSession,
    AuthSessionRecord,
    AuthSessionWithUserRecord,
    AuthUser,
    IssuedLoginCode,
    LoginCodeRecord,
    VerifiedLoginSession,
)
from .constants import AuthConstants as auth_constants


class AuthRepository(Protocol):
    def get_user_by_email(self, email: str) -> AuthUser | None: ...

    def create_user(self, user: AuthUser) -> AuthUser: ...

    def save_login_code(self, login_code: LoginCodeRecord) -> None: ...

    def get_latest_login_code(self, email: str, purpose: str) -> LoginCodeRecord | None: ...

    def increment_login_code_attempt(self, login_code_id: str) -> None: ...

    def consume_login_code(self, login_code_id: str, consumed_at: datetime) -> None: ...

    def create_auth_session(self, session: AuthSessionRecord) -> None: ...

    def get_auth_session_by_token_hash(self, token_hash: str) -> AuthSessionWithUserRecord | None: ...

    def update_auth_session_last_seen(self, session_id: str, last_seen_at: datetime) -> None: ...

    def revoke_auth_session(self, token_hash: str, revoked_at: datetime) -> None: ...


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        *,
        allowed_login_emails: set[str],
        code_ttl: timedelta = auth_constants.DEFAULT_CODE_TTL,
        session_ttl: timedelta = auth_constants.DEFAULT_SESSION_TTL,
        max_attempts: int = auth_constants.DEFAULT_MAX_ATTEMPTS,
        clock: Callable[[], datetime] | None = None,
        verification_code_factory: Callable[[], str] = generate_verification_code,
        token_factory: Callable[[], str] = generate_token,
        user_id_factory: Callable[[], str] | None = None,
        llm_provider_user_id_factory: Callable[[], str] | None = None,
        login_code_id_factory: Callable[[], str] | None = None,
        session_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError(auth_constants.MESSAGE_MAX_ATTEMPTS_POSITIVE)
        self._repository = repository
        self._allowed_login_emails = {normalize_email(email) for email in allowed_login_emails}
        self._code_ttl = code_ttl
        self._session_ttl = session_ttl
        self._max_attempts = max_attempts
        self._clock = clock or (lambda: datetime.now(UTC))
        self._verification_code_factory = verification_code_factory
        self._token_factory = token_factory
        self._user_id_factory = user_id_factory or (
            lambda: f"{auth_constants.USER_ID_PREFIX}_{generate_token(auth_constants.GENERATED_ID_TOKEN_BYTES)}"
        )
        self._llm_provider_user_id_factory = llm_provider_user_id_factory or (
            lambda: (
                f"{auth_constants.LLM_PROVIDER_USER_ID_PREFIX}_"
                f"{generate_token(auth_constants.GENERATED_ID_TOKEN_BYTES)}"
            )
        )
        self._login_code_id_factory = login_code_id_factory or (
            lambda: f"{auth_constants.LOGIN_CODE_ID_PREFIX}_{generate_token(auth_constants.GENERATED_ID_TOKEN_BYTES)}"
        )
        self._session_id_factory = session_id_factory or (
            lambda: f"{auth_constants.SESSION_ID_PREFIX}_{generate_token(auth_constants.GENERATED_ID_TOKEN_BYTES)}"
        )

    def request_login_code(self, email: str) -> IssuedLoginCode | AuthFailure:
        normalized_email = normalize_email(email)
        if normalized_email not in self._allowed_login_emails:
            return AuthFailure(
                ok=False,
                error_code=auth_constants.ERROR_EMAIL_NOT_ALLOWED,
                message=auth_constants.MESSAGE_EMAIL_NOT_ALLOWED,
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
                purpose=auth_constants.LOGIN_CODE_PURPOSE,
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
                error_code=auth_constants.ERROR_EMAIL_NOT_ALLOWED,
                message=auth_constants.MESSAGE_EMAIL_NOT_ALLOWED,
                email=normalized_email,
            )

        login_code = self._repository.get_latest_login_code(normalized_email, auth_constants.LOGIN_CODE_PURPOSE)
        if login_code is None:
            return AuthFailure(
                ok=False,
                error_code=auth_constants.ERROR_LOGIN_CODE_NOT_FOUND,
                message=auth_constants.MESSAGE_LOGIN_CODE_NOT_FOUND,
                email=normalized_email,
            )

        now = self._now()
        if login_code.consumed:
            return AuthFailure(
                ok=False,
                error_code=auth_constants.ERROR_LOGIN_CODE_CONSUMED,
                message=auth_constants.MESSAGE_LOGIN_CODE_CONSUMED,
                email=normalized_email,
            )
        if login_code.expires_at <= now:
            return AuthFailure(
                ok=False,
                error_code=auth_constants.ERROR_LOGIN_CODE_EXPIRED,
                message=auth_constants.MESSAGE_LOGIN_CODE_EXPIRED,
                email=normalized_email,
            )
        if login_code.attempt_count >= self._max_attempts:
            return AuthFailure(
                ok=False,
                error_code=auth_constants.ERROR_TOO_MANY_ATTEMPTS,
                message=auth_constants.MESSAGE_TOO_MANY_ATTEMPTS,
                email=normalized_email,
            )
        if not verify_token(code.strip(), login_code.code_hash):
            self._repository.increment_login_code_attempt(login_code.login_code_id)
            return AuthFailure(
                ok=False,
                error_code=auth_constants.ERROR_INVALID_LOGIN_CODE,
                message=auth_constants.MESSAGE_INVALID_LOGIN_CODE,
                email=normalized_email,
            )

        user = self._repository.get_user_by_email(normalized_email)
        if user is None:
            return AuthFailure(
                ok=False,
                error_code=auth_constants.ERROR_USER_NOT_FOUND,
                message=auth_constants.MESSAGE_USER_NOT_FOUND,
                email=normalized_email,
            )

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

    def authenticate_session_token(self, session_token: str) -> AuthenticatedSession | AuthFailure:
        stripped_token = session_token.strip()
        if not stripped_token:
            return AuthFailure(
                ok=False,
                error_code=auth_constants.ERROR_EMPTY_SESSION_TOKEN,
                message=auth_constants.MESSAGE_EMPTY_SESSION_TOKEN,
            )

        session = self._repository.get_auth_session_by_token_hash(hash_token(stripped_token))
        if session is None:
            return AuthFailure(
                ok=False,
                error_code=auth_constants.ERROR_AUTH_SESSION_NOT_FOUND,
                message=auth_constants.MESSAGE_AUTH_SESSION_NOT_FOUND,
            )

        now = self._now()
        if session.revoked_at is not None:
            return AuthFailure(
                ok=False,
                error_code=auth_constants.ERROR_AUTH_SESSION_REVOKED,
                message=auth_constants.MESSAGE_AUTH_SESSION_REVOKED,
            )
        if session.expires_at <= now:
            return AuthFailure(
                ok=False,
                error_code=auth_constants.ERROR_AUTH_SESSION_EXPIRED,
                message=auth_constants.MESSAGE_AUTH_SESSION_EXPIRED,
            )

        self._repository.update_auth_session_last_seen(session.session_id, now)
        return AuthenticatedSession(
            ok=True,
            user_id=session.user_id,
            email=session.email,
            llm_provider_user_id=session.llm_provider_user_id,
            session_id=session.session_id,
            expires_at=session.expires_at,
        )

    def revoke_session_token(self, session_token: str) -> bool:
        stripped_token = session_token.strip()
        if not stripped_token:
            return False

        token_hash = hash_token(stripped_token)
        session = self._repository.get_auth_session_by_token_hash(token_hash)
        if session is None:
            return False

        now = self._now()
        if session.revoked_at is not None or session.expires_at <= now:
            return False

        self._repository.revoke_auth_session(token_hash, now)
        return True

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
        raise ValueError(auth_constants.MESSAGE_LLM_PROVIDER_USER_ID_REQUIRED)
    if len(llm_provider_user_id) > auth_constants.MAX_LLM_PROVIDER_USER_ID_LENGTH:
        raise ValueError(auth_constants.MESSAGE_LLM_PROVIDER_USER_ID_TOO_LONG)
    if normalized_email in normalized_llm_id or local_part in normalized_llm_id:
        raise ValueError(auth_constants.MESSAGE_LLM_PROVIDER_USER_ID_PRIVATE)
    if not auth_constants.LLM_PROVIDER_USER_ID_PATTERN.fullmatch(llm_provider_user_id):
        raise ValueError(auth_constants.MESSAGE_LLM_PROVIDER_USER_ID_PATTERN)
