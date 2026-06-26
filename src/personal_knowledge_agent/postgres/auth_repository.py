from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from personal_knowledge_agent.auth import AuthSessionRecord, AuthUser, LoginCodeRecord


class PostgresConnection(Protocol):
    def execute(self, query: str, params: Sequence[object] = ()) -> object: ...


class PostgresAuthRepository:
    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def get_user_by_email(self, email: str) -> AuthUser | None:
        cursor = self._connection.execute(
            """
            SELECT user_id, email, llm_provider_user_id, created_at, updated_at
            FROM users
            WHERE email = %s
            """,
            (email,),
        )
        row = _fetchone(cursor)
        if row is None:
            return None
        return _auth_user_from_row(row)

    def create_user(self, user: AuthUser) -> AuthUser:
        cursor = self._connection.execute(
            """
            INSERT INTO users (user_id, email, llm_provider_user_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING user_id, email, llm_provider_user_id, created_at, updated_at
            """,
            (user.user_id, user.email, user.llm_provider_user_id, user.created_at, user.updated_at),
        )
        row = _fetchone(cursor)
        self._commit()
        if row is None:
            return user
        return _auth_user_from_row(row)

    def save_login_code(self, login_code: LoginCodeRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO email_login_codes (
              login_code_id,
              user_id,
              email,
              code_hash,
              expires_at,
              purpose,
              consumed,
              attempt_count,
              created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                login_code.login_code_id,
                login_code.user_id,
                login_code.email,
                login_code.code_hash,
                login_code.expires_at,
                login_code.purpose,
                login_code.consumed,
                login_code.attempt_count,
                login_code.created_at,
            ),
        )
        self._commit()

    def get_latest_login_code(self, email: str, purpose: str) -> LoginCodeRecord | None:
        cursor = self._connection.execute(
            """
            SELECT
              login_code_id,
              user_id,
              email,
              code_hash,
              expires_at,
              purpose,
              consumed,
              attempt_count,
              created_at
            FROM email_login_codes
            WHERE email = %s AND purpose = %s
            ORDER BY created_at DESC, login_code_id DESC
            LIMIT 1
            """,
            (email, purpose),
        )
        row = _fetchone(cursor)
        if row is None:
            return None
        return _login_code_from_row(row)

    def increment_login_code_attempt(self, login_code_id: str) -> None:
        self._connection.execute(
            """
            UPDATE email_login_codes
            SET attempt_count = attempt_count + 1
            WHERE login_code_id = %s
            """,
            (login_code_id,),
        )
        self._commit()

    def consume_login_code(self, login_code_id: str, consumed_at: datetime) -> None:
        self._connection.execute(
            """
            UPDATE email_login_codes
            SET consumed = true, consumed_at = %s
            WHERE login_code_id = %s
            """,
            (consumed_at, login_code_id),
        )
        self._commit()

    def create_auth_session(self, session: AuthSessionRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO auth_sessions (session_id, user_id, token_hash, expires_at, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (session.session_id, session.user_id, session.token_hash, session.expires_at, session.created_at),
        )
        self._commit()

    def _commit(self) -> None:
        commit = getattr(self._connection, "commit", None)
        if callable(commit):
            commit()


def _fetchone(cursor: object) -> object | None:
    fetchone = getattr(cursor, "fetchone")
    return fetchone()


def _auth_user_from_row(row: object) -> AuthUser:
    return AuthUser(
        user_id=_row_value(row, 0, "user_id"),
        email=_row_value(row, 1, "email"),
        llm_provider_user_id=_row_value(row, 2, "llm_provider_user_id"),
        created_at=_row_value(row, 3, "created_at"),
        updated_at=_row_value(row, 4, "updated_at"),
    )


def _login_code_from_row(row: object) -> LoginCodeRecord:
    return LoginCodeRecord(
        login_code_id=_row_value(row, 0, "login_code_id"),
        user_id=_row_value(row, 1, "user_id"),
        email=_row_value(row, 2, "email"),
        code_hash=_row_value(row, 3, "code_hash"),
        expires_at=_row_value(row, 4, "expires_at"),
        purpose=_row_value(row, 5, "purpose"),
        consumed=_row_value(row, 6, "consumed"),
        attempt_count=_row_value(row, 7, "attempt_count"),
        created_at=_row_value(row, 8, "created_at"),
    )


def _row_value(row: object, index: int, key: str) -> object:
    if isinstance(row, dict):
        return row[key]
    return row[index]  # type: ignore[index]
