from __future__ import annotations

import smtplib
import time
from email.message import EmailMessage

from inbox_lens.config import Settings


# Permanent SMTP failures should fail fast — retrying a bad password just delays the user.
_PERMANENT_SMTP_ERRORS = (
    smtplib.SMTPAuthenticationError,
    smtplib.SMTPRecipientsRefused,
    smtplib.SMTPSenderRefused,
    smtplib.SMTPHeloError,
    smtplib.SMTPNotSupportedError,
)


class SMTPSink:
    def __init__(self, settings: Settings, max_attempts: int = 3, initial_backoff: float = 2.0):
        self.settings = settings
        self.max_attempts = max(1, max_attempts)
        self.initial_backoff = initial_backoff

    def send(self, subject: str, html: str, text: str) -> None:
        self.settings.require_sink()
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.settings.smtp_from
        message["To"] = self.settings.digest_to
        message.set_content(text)
        message.add_alternative(html, subtype="html")

        # Only the connection/login phase is retried. Once the message has been handed to
        # send_message, a failure is NOT retried: the server may have already accepted the
        # message, and resending would deliver the digest twice.
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                smtp = self._connect()
            except _PERMANENT_SMTP_ERRORS:
                raise
            except (smtplib.SMTPException, OSError) as exc:
                last_error = exc
                if attempt >= self.max_attempts:
                    break
                time.sleep(self.initial_backoff * (2 ** (attempt - 1)))
                continue
            with smtp:
                self._send_once(smtp, message)
            return
        if last_error is not None:
            raise last_error

    def _connect(self) -> smtplib.SMTP:
        if self.settings.smtp_use_ssl:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(self.settings.smtp_host, self.settings.smtp_port, timeout=60)
        else:
            smtp = smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=60)
            if self.settings.smtp_starttls:
                smtp.starttls()
        smtp.login(self.settings.smtp_user, self.settings.smtp_password)
        return smtp

    def _send_once(self, smtp: smtplib.SMTP, message: EmailMessage) -> None:
        smtp.send_message(message)
