from __future__ import annotations

import unittest

from inbox_lens.fetcher.imap_source import _extract_uid_from_response, _peek_message_id, _peek_received_at


class FetcherFilterTests(unittest.TestCase):
    def test_extract_uid_from_response_header(self) -> None:
        response = "1234 (UID 42 BODY[HEADER.FIELDS (MESSAGE-ID DATE)] {78}"
        self.assertEqual(_extract_uid_from_response(response), "42")

    def test_peek_message_id_parses_header_block(self) -> None:
        headers = b"Message-ID: <abc@example.com>\r\nDate: Mon, 11 May 2026 08:00:00 +0000\r\n\r\n"
        self.assertEqual(_peek_message_id(headers), "<abc@example.com>")

    def test_peek_received_at_returns_utc(self) -> None:
        headers = b"Message-ID: <abc@example.com>\r\nDate: Mon, 11 May 2026 08:00:00 +0000\r\n\r\n"
        parsed = _peek_received_at(headers)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.tzname(), "UTC")


if __name__ == "__main__":
    unittest.main()
