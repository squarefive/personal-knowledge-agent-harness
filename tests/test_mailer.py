import pytest

from personal_knowledge_agent.mail import SmtpEmailConfig, SmtpEmailSendError, SmtpEmailSender


class FakeSmtp:
    instances = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_calls = []
        self.sent_messages = []
        FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.login_calls.append((user, password))

    def send_message(self, message):
        self.sent_messages.append(message)


class FailingSmtp(FakeSmtp):
    def login(self, user, password):
        raise RuntimeError(f"bad password: {password}")


@pytest.fixture(autouse=True)
def reset_fake_smtp():
    FakeSmtp.instances = []


def test_send_login_code_uses_ssl_smtp_and_builds_plain_text_message():
    config = SmtpEmailConfig(
        host="smtp.qq.com",
        port=465,
        ssl=True,
        user="sender@qq.com",
        password="runtime-secret",
        mail_from="sender@qq.com",
    )
    sender = SmtpEmailSender(config, smtp_ssl_factory=FakeSmtp)

    sender.send_login_code("user@example.com", "123456", 5)

    smtp = FakeSmtp.instances[0]
    assert smtp.host == "smtp.qq.com"
    assert smtp.port == 465
    assert smtp.login_calls == [("sender@qq.com", "runtime-secret")]
    assert len(smtp.sent_messages) == 1
    message = smtp.sent_messages[0]
    assert message["From"] == "sender@qq.com"
    assert message["To"] == "user@example.com"
    assert message["Subject"] == "Your login verification code"
    body = message.get_content()
    assert "123456" in body
    assert "5 minutes" in body


def test_send_login_code_uses_starttls_for_non_ssl_smtp():
    config = SmtpEmailConfig(
        host="smtp.qq.com",
        port=587,
        ssl=False,
        user="sender@qq.com",
        password="runtime-secret",
        mail_from="sender@qq.com",
    )
    sender = SmtpEmailSender(config, smtp_factory=FakeSmtp)

    sender.send_login_code("user@example.com", "234567", 10)

    smtp = FakeSmtp.instances[0]
    assert smtp.host == "smtp.qq.com"
    assert smtp.port == 587
    assert smtp.started_tls is True
    assert smtp.login_calls == [("sender@qq.com", "runtime-secret")]
    assert "234567" in smtp.sent_messages[0].get_content()
    assert "10 minutes" in smtp.sent_messages[0].get_content()


def test_send_login_code_can_skip_starttls_for_plain_smtp():
    config = SmtpEmailConfig(
        host="localhost",
        port=25,
        ssl=False,
        starttls=False,
        user="sender",
        password="runtime-secret",
        mail_from="sender@example.com",
    )
    sender = SmtpEmailSender(config, smtp_factory=FakeSmtp)

    sender.send_login_code("user@example.com", "345678", 3)

    smtp = FakeSmtp.instances[0]
    assert smtp.started_tls is False
    assert smtp.login_calls == [("sender", "runtime-secret")]


def test_password_is_hidden_from_config_repr_and_send_exception_message():
    config = SmtpEmailConfig(
        host="smtp.qq.com",
        port=465,
        ssl=True,
        user="sender@qq.com",
        password="runtime-secret",
        mail_from="sender@qq.com",
    )
    sender = SmtpEmailSender(config, smtp_ssl_factory=FailingSmtp)

    assert "runtime-secret" not in repr(config)
    with pytest.raises(SmtpEmailSendError) as exc_info:
        sender.send_login_code("user@example.com", "456789", 5)

    error_message = str(exc_info.value)
    assert "runtime-secret" not in error_message
    assert "456789" not in error_message
