from __future__ import annotations

import smtplib
import unittest
from pathlib import Path

from inbox_lens.config import Settings
from inbox_lens.sender import SMTPSink


def _settings() -> Settings:
    return Settings(
        imap_host="imap.example.com",
        imap_port=993,
        imap_user="src@example.com",
        imap_password="x",
        imap_folder="INBOX",
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_user="send@example.com",
        smtp_password="x",
        smtp_from="send@example.com",
        digest_to="to@example.com",
        smtp_use_ssl=True,
        smtp_starttls=False,
        database_path=Path("data/test.sqlite"),
        timezone_name="UTC",
        bootstrap_window_hours=24,
        retention_days=30,
        send_empty_digest=False,
        send_failure_email=False,
        user_rules_path=Path("rules.toml"),
        llm_enabled=False,
        llm_base_url="",
        llm_api_key="",
        llm_model="",
        llm_json_mode=True,
        llm_timeout_seconds=45,
    )


class SMTPRetryTests(unittest.TestCase):
    def test_transient_error_is_retried(self) -> None:
        sink = SMTPSink(_settings(), max_attempts=3, initial_backoff=0)
        attempts = {"n": 0}

        def fake_send(_message):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise smtplib.SMTPServerDisconnected("temporary")

        sink._send_once = fake_send  # type: ignore[assignment]
        sink.send("subject", "<p>hi</p>", "hi")

        self.assertEqual(attempts["n"], 3)

    def test_authentication_error_fails_fast(self) -> None:
        sink = SMTPSink(_settings(), max_attempts=3, initial_backoff=0)
        attempts = {"n": 0}

        def fake_send(_message):
            attempts["n"] += 1
            raise smtplib.SMTPAuthenticationError(535, b"bad password")

        sink._send_once = fake_send  # type: ignore[assignment]
        with self.assertRaises(smtplib.SMTPAuthenticationError):
            sink.send("subject", "<p>hi</p>", "hi")
        self.assertEqual(attempts["n"], 1)


if __name__ == "__main__":
    unittest.main()
