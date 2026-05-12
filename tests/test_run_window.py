from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from inbox_lens.config import Settings
from inbox_lens.pipeline import run_digest
from inbox_lens.storage import Repository


class _FakeEmptySource:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def fetch_since(self, since, limit=None, already_processed=None):
        return []


def _settings(temp_dir: Path) -> Settings:
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
        database_path=temp_dir / "state.sqlite",
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


class RunWindowTests(unittest.TestCase):
    def test_empty_window_records_empty_status_and_advances_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _settings(Path(temp_dir))
            with patch("inbox_lens.pipeline.IMAPSource", _FakeEmptySource):
                with redirect_stdout(StringIO()):
                    run_digest(settings, dry_run=False, limit=None)

            repo = Repository(settings.database_path)
            runs = repo.recent_runs(1)
            self.assertEqual(runs[0]["status"], "empty")
            self.assertEqual(runs[0]["mail_count"], 0)
            self.assertIsNotNone(repo.last_success_finished_at())


if __name__ == "__main__":
    unittest.main()
