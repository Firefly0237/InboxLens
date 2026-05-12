from __future__ import annotations

import re

from inbox_lens.models import ProcessedMail, RawMail
from inbox_lens.preprocessor.html_to_text import html_to_text, normalize_whitespace
from inbox_lens.preprocessor.injection_filter import detect_prompt_injection


MAX_BODY_CHARS = 12000
TAIL_CHARS = 1800


def preprocess_mail(mail: RawMail) -> ProcessedMail:
    if mail.text_body.strip() and (len(mail.text_body.strip()) >= 50 or not mail.html_body):
        source = "text/plain"
        text = mail.text_body
    else:
        source = "text/html" if mail.html_body else "metadata"
        text = html_to_text(mail.html_body)
    if not text.strip():
        text = f"Subject: {mail.subject}\nFrom: {mail.sender}"

    text = _remove_quoted_history(text)
    text = _remove_common_footer_noise(text)
    text = normalize_whitespace(text)
    text, was_truncated = _truncate_for_llm(text)
    flags = detect_prompt_injection(text)
    return ProcessedMail(
        raw=mail,
        clean_text=text,
        source_used=source,
        was_truncated=was_truncated,
        security_flags=flags,
    )


def _remove_quoted_history(text: str) -> str:
    kept: list[str] = []
    quote_markers = [
        re.compile(r"^>"),
        re.compile(r"^On .+ wrote:$", re.I),
        re.compile(r"^-{2,}\s*Original Message\s*-{2,}$", re.I),
        re.compile(r"^发件人[:：].+发送时间[:：]", re.I),
    ]
    for line in text.splitlines():
        stripped = line.strip()
        if any(pattern.search(stripped) for pattern in quote_markers):
            continue
        kept.append(line)
    return "\n".join(kept)


def _remove_common_footer_noise(text: str) -> str:
    noise_patterns = [
        r"(?im)^unsubscribe\b.*$",
        r"(?im)^manage preferences\b.*$",
        r"(?im)^view this email in your browser\b.*$",
        r"(?im)^取消订阅.*$",
        r"(?im)^退订.*$",
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, "", text)
    return text


def _truncate_for_llm(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_BODY_CHARS:
        return text, False
    # The tail often contains deadlines or calls to action, so keep both the front and the end.
    head_chars = MAX_BODY_CHARS - TAIL_CHARS
    truncated = f"{text[:head_chars].rstrip()}\n\n[...truncated...]\n\n{text[-TAIL_CHARS:].lstrip()}"
    return truncated, True
