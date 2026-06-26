from __future__ import annotations

import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any, Callable


class SmtpEmailSendError(RuntimeError):
    pass


@dataclass(frozen=True)
class SmtpEmailConfig:
    host: str
    port: int
    ssl: bool
    user: str
    password: str = field(repr=False)
    mail_from: str
    starttls: bool = True
    timeout_seconds: int = 30


class SmtpEmailSender:
    def __init__(
        self,
        config: SmtpEmailConfig,
        *,
        smtp_factory: Callable[..., Any] = smtplib.SMTP,
        smtp_ssl_factory: Callable[..., Any] = smtplib.SMTP_SSL,
    ):
        self.config = config
        self._smtp_factory = smtp_factory
        self._smtp_ssl_factory = smtp_ssl_factory

    def send_login_code(self, to_email: str, code: str, expires_minutes: int) -> None:
        message = self._build_login_code_message(to_email, code, expires_minutes)
        try:
            with self._connect() as smtp:
                if not self.config.ssl and self.config.starttls:
                    smtp.starttls()
                smtp.login(self.config.user, self.config.password)
                smtp.send_message(message)
        except Exception:
            raise SmtpEmailSendError("SMTP email send failed") from None

    def _connect(self) -> Any:
        factory = self._smtp_ssl_factory if self.config.ssl else self._smtp_factory
        return factory(
            self.config.host,
            self.config.port,
            timeout=self.config.timeout_seconds,
        )

    def _build_login_code_message(
        self,
        to_email: str,
        code: str,
        expires_minutes: int,
    ) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self.config.mail_from
        message["To"] = to_email
        message["Subject"] = "Your login verification code"
        message.set_content(
            "\n".join(
                [
                    f"Your login verification code is: {code}",
                    f"This code expires in {expires_minutes} minutes.",
                    "If you did not request this code, ignore this email.",
                ]
            )
        )
        return message
