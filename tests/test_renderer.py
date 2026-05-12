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


if __name__ == "__main__":
    unittest.main()
