"""The `EmailSender` boundary — the only code that performs outbound email.

Phase 1 sends two kinds of message (email verification and password reset)
synchronously in the request path (no queue). The transactional provider is not
chosen yet (`specification.md` §11.9), so the real implementation is plain SMTP
configured from the environment; anything provider-specific slots in behind the
same `send()` contract later.
"""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as _MIMEMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


class EmailSender:
    """Interface. Real senders talk to a provider; the test fake records."""

    def send(self, message: EmailMessage) -> None:  # pragma: no cover - abstract
        raise NotImplementedError


class SmtpEmailSender(EmailSender):
    """Sends via a plain SMTP server (STARTTLS). Config comes from env vars."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_addr: str,
        use_tls: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_addr = from_addr
        self._use_tls = use_tls

    def send(self, message: EmailMessage) -> None:
        mime = _MIMEMessage()
        mime["From"] = self._from_addr
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.body)

        with smtplib.SMTP(self._host, self._port, timeout=30) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._username and self._password:
                smtp.login(self._username, self._password)
            smtp.send_message(mime)


class LoggingEmailSender(EmailSender):
    """Fallback when no SMTP server is configured (local dev). Logs instead."""

    def send(self, message: EmailMessage) -> None:
        logger.warning(
            "EMAIL NOT SENT (no SMTP configured). to=%s subject=%s\n%s",
            message.to,
            message.subject,
            message.body,
        )


def get_email_sender() -> EmailSender:
    """FastAPI dependency. Overridden with a recording fake in tests."""
    host = os.getenv("SMTP_HOST")
    if not host:
        return LoggingEmailSender()
    return SmtpEmailSender(
        host=host,
        port=int(os.getenv("SMTP_PORT", "587")),
        username=os.getenv("SMTP_USERNAME"),
        password=os.getenv("SMTP_PASSWORD"),
        from_addr=os.getenv("SMTP_FROM", "no-reply@mentisq.com"),
        use_tls=os.getenv("SMTP_TLS", "1") != "0",
    )
