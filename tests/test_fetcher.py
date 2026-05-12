from __future__ import annotations

import unittest
from email.message import EmailMessage

from inbox_lens.fetcher.imap_source import parse_raw_mail


class FetcherTests(unittest.TestCase):
    def test_parse_raw_mail_extracts_attachment_metadata(self) -> None:
        message = EmailMessage()
        message["From"] = "sender@example.com"
        message["To"] = "me@example.com"
        message["Subject"] = "Report"
        message["Message-ID"] = "<attachment@example.com>"
        message["Date"] = "Mon, 11 May 2026 08:00:00 +0000"
        message.set_content("See attached report.")
        message.add_attachment(
            b"abc123",
            maintype="application",
            subtype="pdf",
            filename="report.pdf",
        )

        raw = parse_raw_mail("42", message.as_bytes())

        self.assertEqual(raw.message_id, "<attachment@example.com>")
        self.assertEqual(len(raw.attachments), 1)
        self.assertEqual(raw.attachments[0].filename, "report.pdf")
        self.assertEqual(raw.attachments[0].content_type, "application/pdf")
        self.assertEqual(raw.attachments[0].size_bytes, 6)


if __name__ == "__main__":
    unittest.main()
