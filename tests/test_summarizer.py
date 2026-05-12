from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from inbox_lens.models import Classification, ProcessedMail, RawMail
from inbox_lens.summarizer import build_digest, summarize_email


class SummarizerTests(unittest.TestCase):
    def test_finance_summary_extracts_amount_and_deadline(self) -> None:
        raw = RawMail(
            uid="1",
            message_id="<finance@example.com>",
            sender="Bank <notice@bank.example>",
            recipients="me@example.com",
            subject="信用卡账单",
            received_at=datetime(2026, 5, 11, tzinfo=UTC),
            headers={},
            text_body="",
            html_body="",
        )
        processed = ProcessedMail(raw, "Your payment of ¥3,247.00 is due 5月18日.", "text/plain", False)
        classification = Classification("账单与财务", "P1", "需执行", "5月18日", 0.9, "test")
        summary = summarize_email(processed, classification, None)

        self.assertIn("金额：¥3,247.00", summary.key_facts)
        self.assertTrue(summary.one_liner.startswith("Bank 的财务邮件"))

    def test_digest_builds_overview_and_sender_bundles(self) -> None:
        now = datetime(2026, 5, 11, tzinfo=UTC)
        records = []
        for index in range(3):
            raw = RawMail(
                uid=str(index),
                message_id=f"<news-{index}@example.com>",
                sender="Weekly <news@example.com>",
                recipients="me@example.com",
                subject=f"Issue {index}",
                received_at=now + timedelta(minutes=index),
                headers={},
                text_body="",
                html_body="",
            )
            processed = ProcessedMail(raw, "Newsletter body.", "text/plain", False)
            classification = Classification("资讯订阅", "P2", "仅知晓", None, 0.8, "test")
            records.append((raw, classification, summarize_email(processed, classification, None)))

        from inbox_lens.models import ProcessedRecord

        digest = build_digest([ProcessedRecord(*record) for record in records], now - timedelta(days=1), now)
        self.assertTrue(any("共 3 封新邮件" in line for line in digest.overview_lines))
        self.assertEqual(len(digest.sender_bundles), 1)
        self.assertEqual(digest.sender_bundles[0].count, 3)


if __name__ == "__main__":
    unittest.main()
