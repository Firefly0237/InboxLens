from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from inbox_lens.config import Settings
from inbox_lens.models import RawMail
from inbox_lens.pipeline import run_digest
from inbox_lens.storage import Repository


class _FakeSource:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def fetch_since(self, since, limit=None, already_processed=None):
        return [
            RawMail(
                uid="1",
                message_id="<dry-run@example.com>",
                sender="Alice <alice@example.com>",
                recipients="me@example.com",
                subject="Please review",
                received_at=datetime(2026, 5, 11, 8, 0, tzinfo=UTC),
                headers={},
                text_body="Please review the attached plan today.",
                html_body="",
            )
        ]


class PipelineTests(unittest.TestCase):
    def test_dry_run_does_not_mark_messages_processed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _settings(Path(temp_dir))
            with patch("inbox_lens.pipeline.IMAPSource", _FakeSource):
                with redirect_stdout(StringIO()):
                    digest = run_digest(settings, dry_run=True, limit=1)

            repo = Repository(settings.database_path)
            runs = repo.recent_runs(1)
            processed = repo.already_processed("<dry-run@example.com>")

        self.assertEqual(len(digest.records), 1)
        self.assertEqual(runs[0]["status"], "dry_run")
        self.assertFalse(processed)


def _settings(temp_dir: Path) -> Settings:
    return Settings(
        imap_host="imap.example.com",
        imap_port=993,
        imap_user="source@example.com",
        imap_password="secret",
        imap_folder="INBOX",
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_user="sender@example.com",
        smtp_password="secret",
        smtp_from="sender@example.com",
        digest_to="receiver@example.com",
        smtp_use_ssl=True,
        smtp_starttls=False,
        database_path=temp_dir / "inbox_lens.sqlite",
        timezone_name="UTC",
        bootstrap_window_hours=24,
        retention_days=30,
        send_empty_digest=False,
        send_failure_email=False,
        user_rules_path=temp_dir / "rules.toml",
        llm_enabled=False,
        llm_base_url="",
        llm_api_key="",
        llm_model="",
        llm_json_mode=True,
        llm_timeout_seconds=45,
    )


if __name__ == "__main__":
    unittest.main()
