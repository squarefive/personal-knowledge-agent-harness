from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from personal_knowledge_agent.auth import AuthService, AuthSessionRecord, AuthSessionWithUserRecord, AuthUser, LoginCodeRecord
from personal_knowledge_agent.security.token_hashing import hash_token


ALLOWED_EMAIL = "1033795760@qq.com"
NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


class FakeAuthRepository:
    def __init__(self) -> None:
        self.users_by_email: dict[str, AuthUser] = {}
        self.login_codes: list[LoginCodeRecord] = []
        self.sessions: list[AuthSessionRecord] = []
        self.revoked_session_hashes: dict[str, datetime] = {}
        self.last_seen_updates: list[tuple[str, datetime]] = []

    def get_user_by_email(self, email: str) -> AuthUser | None:
        return self.users_by_email.get(email)

    def create_user(self, user: AuthUser) -> AuthUser:
        self.users_by_email[user.email] = user
        return user

    def save_login_code(self, login_code: LoginCodeRecord) -> None:
        self.login_codes.append(login_code)

    def get_latest_login_code(self, email: str, purpose: str) -> LoginCodeRecord | None:
        matching = [code for code in self.login_codes if code.email == email and code.purpose == purpose]
        if not matching:
            return None
        return matching[-1]

    def increment_login_code_attempt(self, login_code_id: str) -> None:
        self.login_codes = [
            replace(code, attempt_count=code.attempt_count + 1) if code.login_code_id == login_code_id else code
            for code in self.login_codes
        ]

    def consume_login_code(self, login_code_id: str, consumed_at: datetime) -> None:
        self.login_codes = [
            replace(code, consumed=True) if code.login_code_id == login_code_id else code for code in self.login_codes
        ]

    def create_auth_session(self, session: AuthSessionRecord) -> None:
        self.sessions.append(session)

    def get_auth_session_by_token_hash(self, token_hash: str) -> AuthSessionWithUserRecord | None:
        session = next((candidate for candidate in self.sessions if candidate.token_hash == token_hash), None)
        if session is None:
            return None
        user = next(candidate for candidate in self.users_by_email.values() if candidate.user_id == session.user_id)
        return AuthSessionWithUserRecord(
            session_id=session.session_id,
            user_id=session.user_id,
            email=user.email,
            llm_provider_user_id=user.llm_provider_user_id,
            expires_at=session.expires_at,
            revoked_at=self.revoked_session_hashes.get(token_hash),
            last_seen_at=None,
        )

    def update_auth_session_last_seen(self, session_id: str, last_seen_at: datetime) -> None:
        self.last_seen_updates.append((session_id, last_seen_at))

    def revoke_auth_session(self, token_hash: str, revoked_at: datetime) -> None:
        self.revoked_session_hashes[token_hash] = revoked_at


def build_service(repo: FakeAuthRepository, *, now: datetime = NOW, max_attempts: int = 5) -> AuthService:
    return AuthService(
        repo,
        allowed_login_emails={ALLOWED_EMAIL},
        clock=lambda: now,
        verification_code_factory=lambda: "123456",
        token_factory=lambda: "plain-session-token",
        user_id_factory=lambda: "usr_test_1",
        llm_provider_user_id_factory=lambda: "llm_test_1",
        login_code_id_factory=lambda: f"lc_{len(repo.login_codes) + 1}",
        session_id_factory=lambda: "sess_test_1",
        max_attempts=max_attempts,
    )


def build_service_with_llm_provider_user_id(repo: FakeAuthRepository, llm_provider_user_id: str) -> AuthService:
    return AuthService(
        repo,
        allowed_login_emails={ALLOWED_EMAIL},
        clock=lambda: NOW,
        verification_code_factory=lambda: "123456",
        token_factory=lambda: "plain-session-token",
        user_id_factory=lambda: "usr_test_1",
        llm_provider_user_id_factory=lambda: llm_provider_user_id,
        login_code_id_factory=lambda: "lc_1",
        session_id_factory=lambda: "sess_test_1",
    )


def test_request_login_code_rejects_non_allowlisted_email_without_creating_code():
    repo = FakeAuthRepository()
    service = build_service(repo)

    result = service.request_login_code("other@example.com")

    assert not result.ok
    assert result.error_code == "email_not_allowed"
    assert repo.users_by_email == {}
    assert repo.login_codes == []


def test_request_login_code_normalizes_email_and_stores_hash_not_plaintext():
    repo = FakeAuthRepository()
    service = build_service(repo)

    result = service.request_login_code("  1033795760@QQ.COM  ")

    assert result.ok
    assert result.email == ALLOWED_EMAIL
    assert result.plaintext_code == "123456"
    assert repo.login_codes[0].email == ALLOWED_EMAIL
    assert repo.login_codes[0].purpose == "login"
    assert repo.login_codes[0].code_hash != "123456"
    assert repo.login_codes[0].code_hash.startswith("sha256:")


def test_verify_login_code_increments_attempt_for_wrong_code():
    repo = FakeAuthRepository()
    service = build_service(repo)
    service.request_login_code(ALLOWED_EMAIL)

    result = service.verify_login_code(ALLOWED_EMAIL, "000000")

    assert not result.ok
    assert result.error_code == "invalid_login_code"
    assert repo.login_codes[0].attempt_count == 1
    assert repo.sessions == []


def test_verify_login_code_rejects_expired_code():
    repo = FakeAuthRepository()
    service = build_service(repo, now=NOW)
    service.request_login_code(ALLOWED_EMAIL)
    later_service = build_service(repo, now=NOW + timedelta(minutes=11))

    result = later_service.verify_login_code(ALLOWED_EMAIL, "123456")

    assert not result.ok
    assert result.error_code == "login_code_expired"
    assert not repo.login_codes[0].consumed
    assert repo.sessions == []


def test_verify_login_code_rejects_when_attempt_limit_is_reached():
    repo = FakeAuthRepository()
    service = build_service(repo, max_attempts=1)
    service.request_login_code(ALLOWED_EMAIL)
    service.verify_login_code(ALLOWED_EMAIL, "000000")

    result = service.verify_login_code(ALLOWED_EMAIL, "123456")

    assert not result.ok
    assert result.error_code == "too_many_attempts"
    assert not repo.login_codes[0].consumed
    assert repo.sessions == []


def test_verify_login_code_consumes_code_and_stores_session_token_hash_only():
    repo = FakeAuthRepository()
    service = build_service(repo)
    service.request_login_code(ALLOWED_EMAIL)

    result = service.verify_login_code("  1033795760@QQ.COM ", "123456")

    assert result.ok
    assert result.email == ALLOWED_EMAIL
    assert result.session_token == "plain-session-token"
    assert repo.login_codes[0].consumed
    assert repo.sessions[0].token_hash != "plain-session-token"
    assert repo.sessions[0].token_hash.startswith("sha256:")


def test_authenticate_session_token_returns_user_session_and_updates_last_seen_without_token_hash():
    repo = FakeAuthRepository()
    service = build_service(repo)
    service.request_login_code(ALLOWED_EMAIL)
    login_result = service.verify_login_code(ALLOWED_EMAIL, "123456")

    result = service.authenticate_session_token(login_result.session_token)

    assert result.ok
    assert result.user_id == "usr_test_1"
    assert result.email == ALLOWED_EMAIL
    assert result.llm_provider_user_id == "llm_test_1"
    assert result.session_id == "sess_test_1"
    assert result.expires_at == NOW + timedelta(days=30)
    assert not hasattr(result, "token_hash")
    assert repo.last_seen_updates == [("sess_test_1", NOW)]


def test_authenticate_session_token_rejects_empty_token_without_hashing():
    repo = FakeAuthRepository()
    service = build_service(repo)

    result = service.authenticate_session_token("  ")

    assert not result.ok
    assert result.error_code == "empty_session_token"
    assert repo.last_seen_updates == []


def test_authenticate_session_token_rejects_missing_token_hash():
    repo = FakeAuthRepository()
    service = build_service(repo)

    result = service.authenticate_session_token("missing-session-token")

    assert not result.ok
    assert result.error_code == "auth_session_not_found"
    assert repo.last_seen_updates == []


def test_authenticate_session_token_rejects_expired_token():
    repo = FakeAuthRepository()
    service = build_service(repo)
    service.request_login_code(ALLOWED_EMAIL)
    login_result = service.verify_login_code(ALLOWED_EMAIL, "123456")
    later_service = build_service(repo, now=NOW + timedelta(days=31))

    result = later_service.authenticate_session_token(login_result.session_token)

    assert not result.ok
    assert result.error_code == "auth_session_expired"
    assert repo.last_seen_updates == []


def test_authenticate_session_token_rejects_revoked_token():
    repo = FakeAuthRepository()
    service = build_service(repo)
    service.request_login_code(ALLOWED_EMAIL)
    login_result = service.verify_login_code(ALLOWED_EMAIL, "123456")
    repo.revoked_session_hashes[hash_token(login_result.session_token)] = NOW + timedelta(minutes=1)

    result = service.authenticate_session_token(login_result.session_token)

    assert not result.ok
    assert result.error_code == "auth_session_revoked"
    assert repo.last_seen_updates == []


def test_revoke_session_token_hashes_token_and_marks_valid_session_revoked():
    repo = FakeAuthRepository()
    service = build_service(repo)
    service.request_login_code(ALLOWED_EMAIL)
    login_result = service.verify_login_code(ALLOWED_EMAIL, "123456")

    result = service.revoke_session_token(login_result.session_token)

    assert result is True
    assert repo.revoked_session_hashes == {hash_token("plain-session-token"): NOW}
    assert "plain-session-token" not in repo.revoked_session_hashes


def test_revoke_session_token_returns_false_for_empty_missing_expired_or_already_revoked_token():
    repo = FakeAuthRepository()
    service = build_service(repo)

    assert service.revoke_session_token(" ") is False
    assert service.revoke_session_token("missing-session-token") is False

    service.request_login_code(ALLOWED_EMAIL)
    login_result = service.verify_login_code(ALLOWED_EMAIL, "123456")
    expired_service = build_service(repo, now=NOW + timedelta(days=31))
    assert expired_service.revoke_session_token(login_result.session_token) is False

    repo.revoked_session_hashes[hash_token(login_result.session_token)] = NOW + timedelta(minutes=1)
    assert service.revoke_session_token(login_result.session_token) is False


def test_verify_login_code_rejects_consumed_code():
    repo = FakeAuthRepository()
    service = build_service(repo)
    service.request_login_code(ALLOWED_EMAIL)
    service.verify_login_code(ALLOWED_EMAIL, "123456")

    result = service.verify_login_code(ALLOWED_EMAIL, "123456")

    assert not result.ok
    assert result.error_code == "login_code_consumed"
    assert len(repo.sessions) == 1


def test_llm_provider_user_id_does_not_contain_email():
    repo = FakeAuthRepository()
    service = build_service(repo)

    result = service.request_login_code(ALLOWED_EMAIL)

    assert result.ok
    user = repo.users_by_email[ALLOWED_EMAIL]
    assert ALLOWED_EMAIL not in user.llm_provider_user_id
    assert ALLOWED_EMAIL.split("@", 1)[0] not in user.llm_provider_user_id


def test_llm_provider_user_id_rejects_invalid_characters_before_creating_user():
    repo = FakeAuthRepository()
    service = build_service_with_llm_provider_user_id(repo, "llm.user.1")

    with pytest.raises(ValueError, match=r"match \[a-zA-Z0-9\\-_]\+"):
        service.request_login_code(ALLOWED_EMAIL)

    assert repo.users_by_email == {}
    assert repo.login_codes == []


def test_llm_provider_user_id_rejects_too_long_value_before_creating_user():
    repo = FakeAuthRepository()
    service = build_service_with_llm_provider_user_id(repo, "a" * 513)

    with pytest.raises(ValueError, match="512 characters or fewer"):
        service.request_login_code(ALLOWED_EMAIL)

    assert repo.users_by_email == {}
    assert repo.login_codes == []


def test_llm_provider_user_id_rejects_email_or_local_part_before_creating_user():
    for provider_user_id in (ALLOWED_EMAIL, f"llm_{ALLOWED_EMAIL.split('@', 1)[0]}"):
        repo = FakeAuthRepository()
        service = build_service_with_llm_provider_user_id(repo, provider_user_id)

        with pytest.raises(ValueError, match="email-derived values"):
            service.request_login_code(ALLOWED_EMAIL)

        assert repo.users_by_email == {}
        assert repo.login_codes == []
