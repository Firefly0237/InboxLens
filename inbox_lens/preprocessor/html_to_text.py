from __future__ import annotations

import re
from html.parser import HTMLParser


def html_to_text(html: str) -> str:
    if not html:
        return ""
    converted = _html2text_optional(html)
    if converted is None:
        converted = _beautifulsoup_optional(html)
    if converted is None:
        converted = _HTMLTextExtractor.extract(html)
    return normalize_whitespace(converted)


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _html2text_optional(html: str) -> str | None:
    try:
        import html2text  # type: ignore
    except ImportError:
        return None
    converter = html2text.HTML2Text()
    converter.ignore_images = True
    converter.ignore_emphasis = True
    converter.body_width = 0
    return converter.handle(html)


def _beautifulsoup_optional(html: str) -> str | None:
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n")


class _HTMLTextExtractor(HTMLParser):
    block_tags = {"p", "div", "br", "li", "tr", "table", "h1", "h2", "h3", "h4"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    @classmethod
    def extract(cls, html: str) -> str:
        parser = cls()
        parser.feed(html)
        parser.close()
        return "".join(parser._chunks)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag in self.block_tags:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag in self.block_tags:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if data.strip():
            self._chunks.append(data)
