from __future__ import annotations

import email
import imaplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage, Message
from email.policy import default
from email.utils import parsedate_to_datetime
from typing import Callable

from inbox_lens.config import Settings
from inbox_lens.models import AttachmentInfo, RawMail


class IMAPSource:
    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch_since(
        self,
        since: datetime,
        limit: int | None = None,
        already_processed: Callable[[str], bool] | None = None,
    ) -> list[RawMail]:
        self.settings.require_source()
        since_utc = since.astimezone(UTC)
        search_date = (since_utc - timedelta(days=1)).strftime("%d-%b-%Y")
        messages: list[RawMail] = []
        with imaplib.IMAP4_SSL(
            self.settings.imap_host,
            self.settings.imap_port,
            timeout=60,
        ) as mailbox:
            mailbox.login(self.settings.imap_user, self.settings.imap_password)
            mailbox.select(self.settings.imap_folder, readonly=True)
            status, data = mailbox.uid("search", None, f"SINCE {search_date}")
            if status != "OK":
                raise RuntimeError(f"IMAP search failed: {status}")

            uids = data[0].split() if data and data[0] else []
            candidate_uids = self._filter_candidates(mailbox, uids, since_utc, already_processed)
            for uid in candidate_uids:
                if limit is not None and len(messages) >= limit:
                    break
                raw = self._fetch_one(mailbox, uid)
                mail = parse_raw_mail(uid, raw)
                # Date may differ slightly between the cheap header peek and the parsed body; keep the window check.
                if mail.received_at.astimezone(UTC) >= since_utc:
                    messages.append(mail)
        messages.sort(key=lambda item: item.received_at)
        return messages

    def _filter_candidates(
        self,
        mailbox: imaplib.IMAP4_SSL,
        uids: list[bytes],
        since_utc: datetime,
        already_processed: Callable[[str], bool] | None,
    ) -> list[str]:
        if not uids:
            return []
        survivors: list[str] = []
        for chunk in _chunked(uids, 200):
            uid_set = ",".join(item.decode("ascii", errors="replace") for item in chunk)
            status, data = mailbox.uid(
                "fetch",
                uid_set,
                "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID DATE)])",
            )
            if status != "OK":
                # Fall back to including every UID in the chunk; full fetch will still validate the window.
                survivors.extend(item.decode("ascii", errors="replace") for item in chunk)
                continue
            for uid, headers in _iter_header_responses(data):
                received_at = _peek_received_at(headers)
                if received_at is not None and received_at < since_utc:
                    continue
                message_id = _peek_message_id(headers)
                if message_id and already_processed and already_processed(message_id):
                    continue
                survivors.append(uid)
        return survivors

    @staticmethod
    def _fetch_one(mailbox: imaplib.IMAP4_SSL, uid: str) -> bytes:
        # BODY.PEEK avoids marking messages as seen while still retrieving the full RFC822 payload.
        status, data = mailbox.uid("fetch", uid, "(BODY.PEEK[])")
        if status != "OK":
            raise RuntimeError(f"IMAP fetch failed for UID {uid}: {status}")
        for part in data:
            if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], bytes):
                return part[1]
        raise RuntimeError(f"IMAP fetch returned no message body for UID {uid}")


def parse_raw_mail(uid: str, raw: bytes) -> RawMail:
    message = email.message_from_bytes(raw, policy=default)
    headers = {str(key).lower(): str(value) for key, value in message.items()}
    text_body, html_body, attachments = _extract_parts(message)
    received_at = _parse_received_at(message)
    message_id = str(message.get("Message-ID") or f"imap-uid-{uid}").strip()
    return RawMail(
        uid=uid,
        message_id=message_id,
        sender=str(message.get("From", "")),
        recipients=str(message.get("To", "")),
        subject=str(message.get("Subject", "")),
        received_at=received_at,
        headers=headers,
        text_body=text_body,
        html_body=html_body,
        raw_size=len(raw),
        attachments=attachments,
    )


def _parse_received_at(message: Message) -> datetime:
    raw_date = message.get("Date")
    if raw_date:
        try:
            parsed = parsedate_to_datetime(str(raw_date))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except (TypeError, ValueError, IndexError):
            pass
    return datetime.now(UTC)


def _extract_parts(message: Message) -> tuple[str, str, list[AttachmentInfo]]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[AttachmentInfo] = []
    if message.is_multipart():
        for part in message.walk():
            _append_part(part, text_parts, html_parts, attachments)
    else:
        _append_part(message, text_parts, html_parts, attachments)
    return "\n".join(text_parts).strip(), "\n".join(html_parts).strip(), attachments


def _append_part(
    part: Message,
    text_parts: list[str],
    html_parts: list[str],
    attachments: list[AttachmentInfo],
) -> None:
    if part.is_multipart():
        return
    if _is_attachment(part):
        attachments.append(_attachment_info(part))
        return
    content_type = part.get_content_type()
    try:
        content = part.get_content() if isinstance(part, EmailMessage) else _decode_legacy_part(part)
    except Exception:
        content = _decode_legacy_part(part)
    if not isinstance(content, str):
        return
    if content_type == "text/plain":
        text_parts.append(content)
    elif content_type == "text/html":
        html_parts.append(content)


def _is_attachment(part: Message) -> bool:
    disposition = part.get_content_disposition()
    return disposition == "attachment" or bool(part.get_filename())


def _attachment_info(part: Message) -> AttachmentInfo:
    payload = part.get_payload(decode=True) or b""
    return AttachmentInfo(
        filename=str(part.get_filename() or ""),
        content_type=part.get_content_type(),
        size_bytes=len(payload),
    )


def _decode_legacy_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _chunked(items: list[bytes], size: int) -> list[list[bytes]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _iter_header_responses(data) -> list[tuple[str, bytes]]:
    results: list[tuple[str, bytes]] = []
    for part in data or []:
        if not (isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], (bytes, bytearray))):
            continue
        header = part[0]
        if not isinstance(header, (bytes, bytearray)):
            continue
        header_str = header.decode("ascii", errors="replace")
        uid = _extract_uid_from_response(header_str)
        if not uid:
            continue
        results.append((uid, bytes(part[1])))
    return results


def _extract_uid_from_response(header: str) -> str:
    marker = "UID "
    index = header.find(marker)
    if index < 0:
        return ""
    tail = header[index + len(marker) :].lstrip()
    digits = []
    for char in tail:
        if char.isdigit():
            digits.append(char)
        else:
            break
    return "".join(digits)


def _peek_received_at(headers: bytes) -> datetime | None:
    message = email.message_from_bytes(headers, policy=default)
    raw_date = message.get("Date")
    if not raw_date:
        return None
    try:
        parsed = parsedate_to_datetime(str(raw_date))
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _peek_message_id(headers: bytes) -> str:
    message = email.message_from_bytes(headers, policy=default)
    return str(message.get("Message-ID") or "").strip()
