from __future__ import annotations

import unittest
from datetime import UTC, datetime

from inbox_lens.classifier import classify_with_rules
from inbox_lens.models import ProcessedMail, RawMail


def _mail(subject: str, text: str) -> ProcessedMail:
    raw = RawMail(
        uid="1",
        message_id="<deadline@example.com>",
        sender="Alice <alice@example.com>",
        recipients="me@example.com",
        subject=subject,
        received_at=datetime(2026, 5, 11, tzinfo=UTC),
        headers={},
        text_body=text,
        html_body="",
    )
    return ProcessedMail(raw=raw, clean_text=text, source_used="text/plain", was_truncated=False)


class DeadlineExtractionTests(unittest.TestCase):
    def test_by_weekday_is_detected(self) -> None:
        result = classify_with_rules(_mail("Need your sign-off", "Please review and confirm by Monday."))
        self.assertIsNotNone(result.deadline)
        self.assertIn("monday", (result.deadline or "").lower())

    def test_by_eod_is_detected(self) -> None:
        result = classify_with_rules(_mail("Deck for tomorrow", "We need the slides by EOD."))
        self.assertIsNotNone(result.deadline)
        self.assertIn("eod", (result.deadline or "").lower())

    def test_relative_in_days_is_detected(self) -> None:
        result = classify_with_rules(_mail("Renewal coming up", "Your plan renews in 3 days."))
        self.assertIsNotNone(result.deadline)
        self.assertIn("in 3 days", (result.deadline or "").lower())

    def test_chinese_relative_phrase_is_detected(self) -> None:
        result = classify_with_rules(_mail("项目需求确认", "请在本周内回复，最晚周五前给反馈。"))
        self.assertIsNotNone(result.deadline)

    def test_no_false_positive_on_marketing_blurb(self) -> None:
        result = classify_with_rules(_mail("Promo today", "Save 20 percent."))
        # "today" is still considered a deadline keyword, but the priority must not be P0 for marketing-style copy.
        self.assertNotEqual(result.priority, "P0")


if __name__ == "__main__":
    unittest.main()
