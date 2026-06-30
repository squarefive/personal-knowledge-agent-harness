import re
from datetime import timedelta


class AuthConstants:
    LOGIN_CODE_PURPOSE = "login"
    LLM_PROVIDER_USER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-_]+$")
    MAX_LLM_PROVIDER_USER_ID_LENGTH = 512
    DEFAULT_CODE_TTL = timedelta(minutes=10)
    DEFAULT_SESSION_TTL = timedelta(days=30)
    DEFAULT_MAX_ATTEMPTS = 5
    GENERATED_ID_TOKEN_BYTES = 18
    USER_ID_PREFIX = "usr"
    LLM_PROVIDER_USER_ID_PREFIX = "llm"
    LOGIN_CODE_ID_PREFIX = "lc"
    SESSION_ID_PREFIX = "sess"
    ERROR_EMAIL_NOT_ALLOWED = "email_not_allowed"
    ERROR_LOGIN_CODE_NOT_FOUND = "login_code_not_found"
    ERROR_LOGIN_CODE_CONSUMED = "login_code_consumed"
    ERROR_LOGIN_CODE_EXPIRED = "login_code_expired"
    ERROR_TOO_MANY_ATTEMPTS = "too_many_attempts"
    ERROR_INVALID_LOGIN_CODE = "invalid_login_code"
    ERROR_USER_NOT_FOUND = "user_not_found"
    ERROR_EMPTY_SESSION_TOKEN = "empty_session_token"
    ERROR_AUTH_SESSION_NOT_FOUND = "auth_session_not_found"
    ERROR_AUTH_SESSION_REVOKED = "auth_session_revoked"
    ERROR_AUTH_SESSION_EXPIRED = "auth_session_expired"
    MESSAGE_EMAIL_NOT_ALLOWED = "email is not allowed to log in"
    MESSAGE_LOGIN_CODE_NOT_FOUND = "login code not found"
    MESSAGE_LOGIN_CODE_CONSUMED = "login code has already been used"
    MESSAGE_LOGIN_CODE_EXPIRED = "login code has expired"
    MESSAGE_TOO_MANY_ATTEMPTS = "too many login code attempts"
    MESSAGE_INVALID_LOGIN_CODE = "login code is invalid"
    MESSAGE_USER_NOT_FOUND = "user not found for login code"
    MESSAGE_EMPTY_SESSION_TOKEN = "session token is required"
    MESSAGE_AUTH_SESSION_NOT_FOUND = "auth session not found"
    MESSAGE_AUTH_SESSION_REVOKED = "auth session has been revoked"
    MESSAGE_AUTH_SESSION_EXPIRED = "auth session has expired"
    MESSAGE_MAX_ATTEMPTS_POSITIVE = "max_attempts must be positive"
    MESSAGE_LLM_PROVIDER_USER_ID_REQUIRED = "llm_provider_user_id must not be empty"
    MESSAGE_LLM_PROVIDER_USER_ID_TOO_LONG = "llm_provider_user_id must be 512 characters or fewer"
    MESSAGE_LLM_PROVIDER_USER_ID_PRIVATE = "llm_provider_user_id must not contain email-derived values"
    MESSAGE_LLM_PROVIDER_USER_ID_PATTERN = "llm_provider_user_id must match [a-zA-Z0-9\\-_]+"
