class SecurityConstants:
    DEFAULT_TOKEN_BYTE_COUNT = 32
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
    SENSITIVE_EXACT_KEYS = {"code", "verification_code"}
    VERIFICATION_CODE_UPPER_BOUND = 1_000_000
    VERIFICATION_CODE_WIDTH = 6
