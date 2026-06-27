from __future__ import annotations

import unittest
from datetime import UTC, datetime

from inbox_lens.classifier import classify_with_rules
from inbox_lens.models import (
    CATEGORY_FINANCE,
    CATEGORY_MARKETING,
    CATEGORY_PERSONAL,
    CATEGORY_SOCIAL,
    ProcessedMail,
    RawMail,
)


def _mail(subject: str, sender: str, text: str, headers: dict[str, str] | None = None) -> ProcessedMail:
    raw = RawMail(
        uid="1",
        message_id="<test@example.com>",
        sender=sender,
        recipients="me@example.com",
        subject=subject,
        received_at=datetime(2026, 5, 11, tzinfo=UTC),
        headers=headers or {},
        text_body=text,
        html_body="",
    )
    return ProcessedMail(raw=raw, clean_text=text, source_used="text/plain", was_truncated=False)


class ClassifierTests(unittest.TestCase):
    def test_finance_rule_detects_bill(self) -> None:
        result = classify_with_rules(_mail("Your invoice is ready", "billing@example.com", "Amount due $42.00 by tomorrow"))
        self.assertEqual(result.category, CATEGORY_FINANCE)
        self.assertEqual(result.action, "需执行")
        self.assertIn(result.priority, {"P0", "P1"})

    def test_marketing_rule_detects_list_unsubscribe_offer(self) -> None:
        result = classify_with_rules(
            _mail(
                "Big sale today",
                "shop@example.com",
                "Use this coupon for a discount.",
                {"list-unsubscribe": "<mailto:u@example.com>"},
            )
        )
        self.assertEqual(result.category, CATEGORY_MARKETING)
        self.assertEqual(result.priority, "P2")

    def test_default_is_high_recall_personal(self) -> None:
        result = classify_with_rules(_mail("Question about the project", "Alice <alice@example.com>", "Could you review this?"))
        self.assertEqual(result.category, CATEGORY_PERSONAL)
        self.assertEqual(result.action, "需执行")

    def test_social_domain_match_is_suffix_not_substring(self) -> None:
        # "x.com" is a social domain; "fax.com" must NOT match it via substring.
        result = classify_with_rules(_mail("Meeting notes", "team@fax.com", "see notes attached"))
        self.assertNotEqual(result.category, CATEGORY_SOCIAL)

    def test_social_domain_spoofed_suffix_is_not_trusted(self) -> None:
        result = classify_with_rules(_mail("Hi", "noreply@github.com.evil.example", "click here"))
        self.assertNotEqual(result.category, CATEGORY_SOCIAL)

    def test_real_social_subdomain_is_detected(self) -> None:
        result = classify_with_rules(_mail("New follower", "notifications@notifications.github.com", "you have a new follower"))
        self.assertEqual(result.category, CATEGORY_SOCIAL)


if __name__ == "__main__":
    unittest.main()
