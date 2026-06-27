import re

import pytest

from personal_knowledge_agent.security.log_redaction import REDACTED, redact_sensitive_mapping
from personal_knowledge_agent.security.secrets import read_secret
from personal_knowledge_agent.security.token_hashing import (
    generate_token,
    generate_verification_code,
    hash_token,
    verify_token,
)


def test_read_secret_prefers_file_over_environment(tmp_path):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("from-file\n", encoding="utf-8")

    value = read_secret(
        "SMTP_PASSWORD",
        environ={
            "SMTP_PASSWORD": "from-env",
            "SMTP_PASSWORD_FILE": str(secret_file),
        },
    )

    assert value == "from-file"


def test_read_secret_reports_missing_file(tmp_path):
    missing_file = tmp_path / "missing.txt"

    with pytest.raises(ValueError, match="SMTP_PASSWORD_FILE does not exist"):
        read_secret("SMTP_PASSWORD", environ={"SMTP_PASSWORD_FILE": str(missing_file)})


def test_read_secret_reports_empty_file(tmp_path):
    secret_file = tmp_path / "empty.txt"
    secret_file.write_text("\n", encoding="utf-8")

    with pytest.raises(ValueError, match="SMTP_PASSWORD_FILE is empty"):
        read_secret("SMTP_PASSWORD", environ={"SMTP_PASSWORD_FILE": str(secret_file)})


def test_read_secret_can_treat_empty_optional_file_as_unset(tmp_path):
    secret_file = tmp_path / "empty.txt"
    secret_file.write_text("\n", encoding="utf-8")

    value = read_secret(
        "DASHSCOPE_API_KEY",
        allow_empty=True,
        environ={"DASHSCOPE_API_KEY_FILE": str(secret_file)},
    )

    assert value is None


def test_token_helpers_generate_and_verify_values():
    token = generate_token()
    token_hash = hash_token(token)

    assert token
    assert token_hash.startswith("sha256:")
    assert verify_token(token, token_hash)
    assert not verify_token("wrong-token", token_hash)


def test_verification_code_is_six_digits():
    code = generate_verification_code()

    assert re.fullmatch(r"\d{6}", code)


def test_redact_sensitive_mapping_only_redacts_sensitive_keys():
    redacted = redact_sensitive_mapping(
        {
            "DEEPSEEK_API_KEY": "secret-key",
            "smtp_password": "mail-secret",
            "session_secret": "session-secret",
            "verification_code": "123456",
            "error_code": "invalid_input",
            "message": "safe",
            "count": 3,
        }
    )

    assert redacted == {
        "DEEPSEEK_API_KEY": REDACTED,
        "smtp_password": REDACTED,
        "session_secret": REDACTED,
        "verification_code": REDACTED,
        "error_code": "invalid_input",
        "message": "safe",
        "count": 3,
    }
