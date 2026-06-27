from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from inbox_lens.models import Classification, ProcessedRecord, RawMail, Summary
from inbox_lens.storage import Repository


def _record(message_id: str, subject: str) -> ProcessedRecord:
    return ProcessedRecord(
        mail=RawMail(
            uid=message_id,
            message_id=message_id,
            sender="a@example.com",
            recipients="me@example.com",
            subject=subject,
            received_at=datetime(2026, 5, 11, 8, 0, tzinfo=UTC),
            headers={},
            text_body="",
            html_body="",
        ),
        classification=Classification("个人/工作沟通", "P1", "需回复", None, 0.6, "test"),
        summary=Summary("one liner", [], None),
    )


class StorageTests(unittest.TestCase):
    def test_save_messages_reports_inserted_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Repository(Path(temp_dir) / "inbox.sqlite")
            run_id = repo.start_run(datetime(2026, 5, 10, tzinfo=UTC))
            stored = repo.save_messages(run_id, [_record("<a@x.com>", "A"), _record("<b@x.com>", "B")])
        self.assertEqual(stored, 2)

    def test_message_id_collision_is_reported_not_silent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Repository(Path(temp_dir) / "inbox.sqlite")
            run_id = repo.start_run(datetime(2026, 5, 10, tzinfo=UTC))
            # Two distinct emails sharing a Message-ID: only one row is stored.
            stored = repo.save_messages(
                run_id,
                [_record("<dup@x.com>", "First"), _record("<dup@x.com>", "Second")],
            )
        self.assertEqual(stored, 1)

    def test_already_stored_message_is_not_reinserted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Repository(Path(temp_dir) / "inbox.sqlite")
            run_id = repo.start_run(datetime(2026, 5, 10, tzinfo=UTC))
            repo.save_messages(run_id, [_record("<seen@x.com>", "First")])
            again = repo.save_messages(run_id, [_record("<seen@x.com>", "First again")])
        self.assertEqual(again, 0)


if __name__ == "__main__":
    unittest.main()
