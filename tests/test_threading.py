from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from inbox_lens.models import Classification, ProcessedRecord, RawMail, Summary  # noqa: F401
from inbox_lens.renderer import render_digest_html, render_digest_text
from inbox_lens.summarizer import build_digest


def _record(uid: str, subject: str, received_at: datetime, headers: dict[str, str] | None = None) -> ProcessedRecord:
    raw = RawMail(
        uid=uid,
        message_id=f"<{uid}@example.com>",
        sender="Alice <alice@example.com>",
        recipients="me@example.com",
        subject=subject,
        received_at=received_at,
        headers=headers or {},
        text_body="",
        html_body="",
    )
    return ProcessedRecord(
        mail=raw,
        classification=Classification("个人/工作沟通", "P1", "需回复", None, 0.7, "test"),
        summary=Summary(f"{subject} 摘要", [], "回复对方"),
    )


class ThreadingTests(unittest.TestCase):
    def test_replies_with_in_reply_to_collapse(self) -> None:
        now = datetime(2026, 5, 11, 9, 0, tzinfo=UTC)
        first = _record("a", "Project plan", now)
        reply = _record("b", "Re: Project plan", now + timedelta(minutes=20), {"in-reply-to": "<a@example.com>"})
        digest = build_digest([first, reply], now - timedelta(days=1), now + timedelta(hours=1))

        self.assertEqual(digest.category_counts.get("个人/工作沟通"), 2)
        self.assertEqual(len(digest.representative_ids), 1)
        representative_id = next(iter(digest.representative_ids))
        # Equal priority + action — latest wins as tiebreaker.
        self.assertEqual(representative_id, reply.mail.message_id)
        self.assertEqual(digest.thread_counts.get(representative_id), 2)

    def test_higher_priority_message_becomes_representative(self) -> None:
        from inbox_lens.models import Classification, Summary

        now = datetime(2026, 5, 11, 9, 0, tzinfo=UTC)
        original = _record("a", "Need decision", now)
        # Original is P0 / 需回复, reply is P2 / 仅知晓 — the urgent original must drive the digest.
        original = ProcessedRecord(
            mail=original.mail,
            classification=Classification("个人/工作沟通", "P0", "需回复", "今天", 0.9, "t"),
            summary=Summary("Need decision today", [], "请今天给反馈"),
        )
        reply = _record("b", "Re: Need decision", now + timedelta(minutes=30), {"in-reply-to": "<a@example.com>"})
        reply = ProcessedRecord(
            mail=reply.mail,
            classification=Classification("个人/工作沟通", "P2", "仅知晓", None, 0.6, "t"),
            summary=Summary("Confirming receipt.", [], None),
        )

        digest = build_digest([original, reply], now - timedelta(days=1), now + timedelta(hours=1))
        self.assertIn(original.mail.message_id, digest.representative_ids)

    def test_normalized_subject_collapses_when_headers_missing(self) -> None:
        now = datetime(2026, 5, 11, 9, 0, tzinfo=UTC)
        first = _record("a", "Quarterly review", now)
        followup = _record("b", "回复：Quarterly review", now + timedelta(minutes=5))
        digest = build_digest([first, followup], now - timedelta(days=1), now + timedelta(hours=1))

        self.assertEqual(len(digest.representative_ids), 1)

    def test_rendered_digest_shows_thread_badge(self) -> None:
        now = datetime(2026, 5, 11, 9, 0, tzinfo=UTC)
        first = _record("a", "Plan", now)
        reply = _record("b", "Re: Plan", now + timedelta(minutes=10), {"in-reply-to": "<a@example.com>"})
        digest = build_digest([first, reply], now - timedelta(days=1), now + timedelta(hours=1))
        html = render_digest_html(digest)
        text = render_digest_text(digest)

        self.assertIn("同主题 2 封", html)
        self.assertIn("同主题 2 封", text)
        # The earlier message should not appear as a separate top-level entry.
        self.assertEqual(html.count("Re: Plan"), 1 + html.count("Re: Plan（同主题"))


if __name__ == "__main__":
    unittest.main()
