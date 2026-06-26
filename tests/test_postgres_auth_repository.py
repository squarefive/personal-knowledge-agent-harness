from __future__ import annotations

from datetime import UTC, datetime, timedelta

from personal_knowledge_agent.auth import AuthSessionRecord, AuthSessionWithUserRecord, AuthUser, LoginCodeRecord
from personal_knowledge_agent.postgres import PostgresAuthRepository


NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


class FakeCursor:
    def __init__(self, row: object | None = None) -> None:
        self._row = row

    def fetchone(self) -> object | None:
        return self._row


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.next_row: object | None = None
        self.commit_count = 0

    def execute(self, query: str, params: tuple[object, ...] = ()) -> FakeCursor:
        self.executed.append((" ".join(query.split()), params))
        return FakeCursor(self.next_row)

    def commit(self) -> None:
        self.commit_count += 1


def test_get_user_by_email_uses_parameterized_sql_and_maps_fields() -> None:
    connection = FakeConnection()
    connection.next_row = ("usr_1", "1033795760@qq.com", "llm_1", NOW, NOW + timedelta(seconds=1))
    repo = PostgresAuthRepository(connection)

    user = repo.get_user_by_email("1033795760@qq.com")

    assert user == AuthUser(
        user_id="usr_1",
        email="1033795760@qq.com",
        llm_provider_user_id="llm_1",
        created_at=NOW,
        updated_at=NOW + timedelta(seconds=1),
    )
    sql, params = connection.executed[0]
    assert "WHERE email = %s" in sql
    assert params == ("1033795760@qq.com",)


def test_create_user_inserts_and_returns_database_row() -> None:
    connection = FakeConnection()
    connection.next_row = ("usr_1", "1033795760@qq.com", "llm_1", NOW, NOW)
    repo = PostgresAuthRepository(connection)

    created = repo.create_user(AuthUser("usr_1", "1033795760@qq.com", "llm_1", NOW, NOW))

    assert created.email == "1033795760@qq.com"
    sql, params = connection.executed[0]
    assert "INSERT INTO users" in sql
    assert "RETURNING user_id, email, llm_provider_user_id, created_at, updated_at" in sql
    assert params == ("usr_1", "1033795760@qq.com", "llm_1", NOW, NOW)
    assert connection.commit_count == 1


def test_save_login_code_inserts_hash_and_never_plaintext_code() -> None:
    connection = FakeConnection()
    repo = PostgresAuthRepository(connection)

    repo.save_login_code(
        LoginCodeRecord(
            login_code_id="lc_1",
            user_id="usr_1",
            email="1033795760@qq.com",
            code_hash="sha256:hash-only",
            expires_at=NOW + timedelta(minutes=10),
            purpose="login",
            consumed=False,
            attempt_count=0,
            created_at=NOW,
        )
    )

    sql, params = connection.executed[0]
    assert "INSERT INTO email_login_codes" in sql
    assert "code_hash" in sql
    assert "purpose" in sql
    assert "123456" not in sql
    assert "123456" not in params
    assert "sha256:hash-only" in params
    assert connection.commit_count == 1


def test_get_latest_login_code_filters_by_email_and_purpose_without_consumed_filter() -> None:
    connection = FakeConnection()
    connection.next_row = (
        "lc_2",
        "usr_1",
        "1033795760@qq.com",
        "sha256:hash-only",
        NOW + timedelta(minutes=10),
        "login",
        True,
        2,
        NOW,
    )
    repo = PostgresAuthRepository(connection)

    login_code = repo.get_latest_login_code("1033795760@qq.com", "login")

    assert login_code == LoginCodeRecord(
        login_code_id="lc_2",
        user_id="usr_1",
        email="1033795760@qq.com",
        code_hash="sha256:hash-only",
        expires_at=NOW + timedelta(minutes=10),
        purpose="login",
        consumed=True,
        attempt_count=2,
        created_at=NOW,
    )
    sql, params = connection.executed[0]
    assert "WHERE email = %s AND purpose = %s" in sql
    assert "consumed = false" not in sql.lower()
    assert "ORDER BY created_at DESC, login_code_id DESC LIMIT 1" in sql
    assert params == ("1033795760@qq.com", "login")


def test_increment_and_consume_login_code_update_target_id_with_params() -> None:
    connection = FakeConnection()
    repo = PostgresAuthRepository(connection)

    repo.increment_login_code_attempt("lc_1")
    repo.consume_login_code("lc_1", NOW)

    increment_sql, increment_params = connection.executed[0]
    consume_sql, consume_params = connection.executed[1]
    assert "SET attempt_count = attempt_count + 1 WHERE login_code_id = %s" in increment_sql
    assert increment_params == ("lc_1",)
    assert "SET consumed = true, consumed_at = %s WHERE login_code_id = %s" in consume_sql
    assert consume_params == (NOW, "lc_1")
    assert connection.commit_count == 2


def test_create_auth_session_inserts_token_hash_only() -> None:
    connection = FakeConnection()
    repo = PostgresAuthRepository(connection)

    repo.create_auth_session(
        AuthSessionRecord(
            session_id="sess_1",
            user_id="usr_1",
            token_hash="sha256:session-hash",
            expires_at=NOW + timedelta(days=30),
            created_at=NOW,
        )
    )

    sql, params = connection.executed[0]
    assert "INSERT INTO auth_sessions" in sql
    assert "token_hash" in sql
    assert "plain-session-token" not in sql
    assert "plain-session-token" not in params
    assert "sha256:session-hash" in params
    assert connection.commit_count == 1


def test_get_auth_session_by_token_hash_joins_user_and_maps_session_without_token_hash() -> None:
    connection = FakeConnection()
    connection.next_row = (
        "sess_1",
        "usr_1",
        "1033795760@qq.com",
        "llm_1",
        NOW + timedelta(days=30),
        None,
        NOW + timedelta(minutes=1),
    )
    repo = PostgresAuthRepository(connection)

    session = repo.get_auth_session_by_token_hash("sha256:session-hash")

    assert session == AuthSessionWithUserRecord(
        session_id="sess_1",
        user_id="usr_1",
        email="1033795760@qq.com",
        llm_provider_user_id="llm_1",
        expires_at=NOW + timedelta(days=30),
        revoked_at=None,
        last_seen_at=NOW + timedelta(minutes=1),
    )
    assert not hasattr(session, "token_hash")
    sql, params = connection.executed[0]
    assert "FROM auth_sessions s JOIN users u ON u.user_id = s.user_id WHERE s.token_hash = %s" in sql
    assert "s.revoked_at" in sql
    assert "s.last_seen_at" in sql
    assert "sha256:session-hash" not in sql
    assert params == ("sha256:session-hash",)


def test_update_auth_session_last_seen_uses_session_id_parameter() -> None:
    connection = FakeConnection()
    repo = PostgresAuthRepository(connection)

    repo.update_auth_session_last_seen("sess_1", NOW)

    sql, params = connection.executed[0]
    assert "UPDATE auth_sessions SET last_seen_at = %s WHERE session_id = %s" in sql
    assert params == (NOW, "sess_1")
    assert connection.commit_count == 1


def test_revoke_auth_session_uses_token_hash_parameter_and_never_plaintext_token() -> None:
    connection = FakeConnection()
    repo = PostgresAuthRepository(connection)

    repo.revoke_auth_session("sha256:session-hash", NOW)

    sql, params = connection.executed[0]
    assert "UPDATE auth_sessions SET revoked_at = %s WHERE token_hash = %s" in sql
    assert "plain-session-token" not in sql
    assert "plain-session-token" not in params
    assert "sha256:session-hash" not in sql
    assert params == (NOW, "sha256:session-hash")
    assert connection.commit_count == 1


def test_auth_session_lookup_does_not_concatenate_user_input_into_sql() -> None:
    connection = FakeConnection()
    repo = PostgresAuthRepository(connection)
    malicious_hash = "sha256:anything' OR '1'='1"

    repo.get_auth_session_by_token_hash(malicious_hash)

    sql, params = connection.executed[0]
    assert malicious_hash not in sql
    assert params == (malicious_hash,)
