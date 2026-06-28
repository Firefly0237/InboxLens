from __future__ import annotations

import re

from inbox_lens.models import ProcessedMail, RawMail
from inbox_lens.preprocessor.html_to_text import html_to_text, normalize_whitespace
from inbox_lens.preprocessor.injection_filter import detect_prompt_injection


MAX_BODY_CHARS = 12000
TAIL_CHARS = 1800


_HTML_PLACEHOLDER_RE = re.compile(
    r"(view\s+(?:this\s+)?(?:e-?mail|message|newsletter)\s+(?:online|in\s+(?:your\s+)?browser)"
    r"|can'?t\s+(?:see|view|read)\s+this"
    r"|trouble\s+viewing"
    r"|enable\s+(?:html|images)"
    r"|无法(?:正常)?(?:显示|查看)"
    r"|在浏览器中(?:查看|打开)"
    r"|查看网页版)",
    re.I,
)


def _is_html_placeholder_stub(text: str) -> bool:
    # A short plain part that is just a "view in browser" notice means the real content lives
    # in the HTML part. A short genuine reply ("Approved, thanks.") is NOT a stub and must be kept.
    return len(text) < 200 and bool(_HTML_PLACEHOLDER_RE.search(text))


def preprocess_mail(mail: RawMail) -> ProcessedMail:
    text_body = mail.text_body.strip()
    if text_body and (not mail.html_body or not _is_html_placeholder_stub(text_body)):
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
