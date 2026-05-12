from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from inbox_lens.models import Classification, ProcessedMail, RawMail
from inbox_lens.personal_rules import apply_personal_rules


class PersonalRulesTests(unittest.TestCase):
    def test_personal_rule_overrides_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rules_path = Path(temp_dir) / "rules.toml"
            rules_path.write_text(
                """
[[rules]]
sender_contains = "boss@example.com"
category = "个人/工作沟通"
priority = "P0"
action = "需回复"
note = "boss"
""".strip(),
                encoding="utf-8",
            )
            raw = RawMail(
                uid="1",
                message_id="<rule@example.com>",
                sender="Boss <boss@example.com>",
                recipients="me@example.com",
                subject="Project",
                received_at=datetime(2026, 5, 11, tzinfo=UTC),
                headers={},
                text_body="",
                html_body="",
            )
            processed = ProcessedMail(raw, "Please check this.", "text/plain", False)
            base = Classification("资讯订阅", "P2", "仅知晓", None, 0.5, "base")
            result = apply_personal_rules(processed, base, rules_path)

        self.assertEqual(result.category, "个人/工作沟通")
        self.assertEqual(result.priority, "P0")
        self.assertEqual(result.action, "需回复")
        self.assertEqual(result.source, "personal_rules")


if __name__ == "__main__":
    unittest.main()
