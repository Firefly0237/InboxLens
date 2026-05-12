from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


CATEGORY_PERSONAL = "个人/工作沟通"
CATEGORY_TRANSACTION = "事务记录"
CATEGORY_FINANCE = "账单与财务"
CATEGORY_SYSTEM = "系统通知"
CATEGORY_NEWSLETTER = "资讯订阅"
CATEGORY_MARKETING = "营销推广"
CATEGORY_SOCIAL = "社交与协作平台"

CATEGORIES = [
    CATEGORY_PERSONAL,
    CATEGORY_TRANSACTION,
    CATEGORY_FINANCE,
    CATEGORY_SYSTEM,
    CATEGORY_NEWSLETTER,
    CATEGORY_MARKETING,
    CATEGORY_SOCIAL,
]

PRIORITIES = ["P0", "P1", "P2"]
ACTIONS = ["需回复", "需执行", "仅知晓"]


@dataclass(frozen=True)
class AttachmentInfo:
    filename: str
    content_type: str
    size_bytes: int

    def display_name(self) -> str:
        size = _format_size(self.size_bytes)
        return f"{self.filename or '(unnamed attachment)'} ({self.content_type}, {size})"


@dataclass(frozen=True)
class RawMail:
    uid: str
    message_id: str
    sender: str
    recipients: str
    subject: str
    received_at: datetime
    headers: dict[str, str]
    text_body: str
    html_body: str
    raw_size: int = 0
    attachments: list[AttachmentInfo] = field(default_factory=list)


@dataclass(frozen=True)
class ProcessedMail:
    raw: RawMail
    clean_text: str
    source_used: str
    was_truncated: bool
    security_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Classification:
    category: str
    priority: str
    action: str
    deadline: str | None
    confidence: float
    rationale: str
    source: str = "rules"


@dataclass(frozen=True)
class Summary:
    one_liner: str
    key_facts: list[str]
    action_required: str | None
    source: str = "heuristic"

    def as_dict(self) -> dict[str, Any]:
        return {
            "one_liner": self.one_liner,
            "key_facts": list(self.key_facts),
            "action_required": self.action_required,
            "source": self.source,
        }


@dataclass(frozen=True)
class ProcessedRecord:
    mail: RawMail
    classification: Classification
    summary: Summary


@dataclass(frozen=True)
class Digest:
    generated_at: datetime
    since: datetime
    records: list[ProcessedRecord]
    category_counts: dict[str, int]
    priority_counts: dict[str, int]
    top_senders: list[tuple[str, int]]
    overview_lines: list[str] = field(default_factory=list)
    sender_bundles: list["SenderBundle"] = field(default_factory=list)
    representative_ids: frozenset[str] = field(default_factory=frozenset)
    thread_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class SenderBundle:
    sender: str
    category: str
    count: int
    subjects: list[str]


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"
