from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from inbox_lens.models import Classification, ProcessedRecord, RawMail, Summary
from inbox_lens.renderer import render_digest_html, render_digest_text
from inbox_lens.summarizer import build_digest


class RendererTests(unittest.TestCase):
    def test_renderer_escapes_subject(self) -> None:
        now = datetime(2026, 5, 11, 8, 0, tzinfo=UTC)
        record = ProcessedRecord(
            mail=RawMail(
                uid="1",
                message_id="<x@example.com>",
                sender="A <a@example.com>",
                recipients="me@example.com",
                subject="<script>alert(1)</script>",
                received_at=now,
                headers={},
                text_body="",
                html_body="",
            ),
            classification=Classification("个人/工作沟通", "P1", "需回复", None, 0.6, "test"),
            summary=Summary("Need reply", [], "回复对方"),
        )
        digest = build_digest([record], now - timedelta(days=1), now)
        html = render_digest_html(digest)
        text = render_digest_text(digest)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Need reply", text)

    def test_renderer_includes_action_agenda(self) -> None:
        now = datetime(2026, 5, 11, 8, 0, tzinfo=UTC)
        record = ProcessedRecord(
            mail=RawMail(
                uid="1",
                message_id="<action@example.com>",
                sender="A <a@example.com>",
                recipients="me@example.com",
                subject="Please approve",
                received_at=now,
                headers={},
                text_body="",
                html_body="",
            ),
            classification=Classification("个人/工作沟通", "P1", "需执行", "今天", 0.8, "test"),
            summary=Summary("Approval needed", ["时效：今天"], "批准请求"),
        )
        digest = build_digest([record], now - timedelta(days=1), now)
        html = render_digest_html(digest)
        text = render_digest_text(digest)
        self.assertIn("待处理事项", html)
        self.assertIn("待处理事项", text)

    def test_agenda_orders_by_priority_then_action(self) -> None:
        now = datetime(2026, 5, 11, 8, 0, tzinfo=UTC)

        def _rec(mid: str, subject: str, priority: str, action: str, deadline: str | None) -> ProcessedRecord:
            return ProcessedRecord(
                mail=RawMail(
                    uid=mid,
                    message_id=f"<{mid}@example.com>",
                    sender="A <a@example.com>",
                    recipients="me@example.com",
                    subject=subject,
                    received_at=now,
                    headers={},
                    text_body="",
                    html_body="",
                ),
                classification=Classification("个人/工作沟通", priority, action, deadline, 0.6, "test"),
                summary=Summary(subject, [], None),
            )

        # A low-priority reply must NOT outrank an urgent P0 deadline item (the old min() bug).
        low = _rec("low", "Low reply", "P2", "需回复", None)
        urgent = _rec("urgent", "Urgent FYI with deadline", "P0", "仅知晓", "今天")
        digest = build_digest([low, urgent], now - timedelta(days=1), now)
        text = render_digest_text(digest)
        self.assertLess(
            text.index("Urgent FYI with deadline"),
            text.index("Low reply"),
            "P0 item should appear before the P2 reply in the agenda",
        )

    def test_deadline_only_item_does_not_render_label_as_action(self) -> None:
        now = datetime(2026, 5, 11, 8, 0, tzinfo=UTC)
        record = ProcessedRecord(
            mail=RawMail(
                uid="1",
                message_id="<fyi@example.com>",
                sender="A <a@example.com>",
                recipients="me@example.com",
                subject="Bill FYI",
                received_at=now,
                headers={},
                text_body="",
                html_body="",
            ),
            classification=Classification("账单与财务", "P1", "仅知晓", "2026-07-01", 0.8, "test"),
            summary=Summary("Bill due", [], None),
        )
        digest = build_digest([record], now - timedelta(days=1), now)
        text = render_digest_text(digest)
        agenda = text.split("待处理事项", 1)[1]
        # The agenda line must not present "仅知晓" (just-be-aware) as the action to take.
        self.assertNotIn("：仅知晓", agenda)


if __name__ == "__main__":
    unittest.main()
