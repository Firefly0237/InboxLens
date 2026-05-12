from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from email.utils import parseaddr

from inbox_lens.models import (
    CATEGORIES,
    PRIORITIES,
    CATEGORY_MARKETING,
    CATEGORY_NEWSLETTER,
    CATEGORY_SOCIAL,
    Digest,
    ProcessedRecord,
    SenderBundle,
)


def build_digest(records: list[ProcessedRecord], since: datetime, generated_at: datetime) -> Digest:
    category_counts = {category: 0 for category in CATEGORIES}
    priority_counts = {priority: 0 for priority in PRIORITIES}
    senders: Counter[str] = Counter()
    for record in records:
        category_counts[record.classification.category] = category_counts.get(record.classification.category, 0) + 1
        priority_counts[record.classification.priority] = priority_counts.get(record.classification.priority, 0) + 1
        senders[_sender_label(record.mail.sender)] += 1
    sorted_records = sorted(records, key=_record_sort_key)
    representative_ids, thread_counts = _thread_groups(sorted_records)
    threaded_count = sum(1 for count in thread_counts.values() if count > 1)
    return Digest(
        generated_at=generated_at,
        since=since,
        records=sorted_records,
        category_counts=category_counts,
        priority_counts=priority_counts,
        top_senders=senders.most_common(8),
        overview_lines=_overview_lines(sorted_records, category_counts, priority_counts, threaded_count),
        sender_bundles=_sender_bundles(sorted_records),
        representative_ids=frozenset(representative_ids),
        thread_counts=thread_counts,
    )


def _record_sort_key(record: ProcessedRecord) -> tuple[int, str, datetime]:
    priority_rank = {"P0": 0, "P1": 1, "P2": 2}.get(record.classification.priority, 3)
    return priority_rank, record.classification.category, record.mail.received_at


def _sender_label(sender: str) -> str:
    display, address = parseaddr(sender)
    return display or address or sender or "(unknown)"


def _overview_lines(
    records: list[ProcessedRecord],
    category_counts: dict[str, int],
    priority_counts: dict[str, int],
    threaded_count: int = 0,
) -> list[str]:
    if not records:
        return ["当前窗口没有新邮件。"]
    lines = [
        f"共 {len(records)} 封新邮件，P0 {priority_counts.get('P0', 0)} 封，P1 {priority_counts.get('P1', 0)} 封。",
    ]
    actionable = [record for record in records if record.classification.action != "仅知晓" or record.classification.deadline]
    if actionable:
        lines.append(f"待处理 {len(actionable)} 项，其中需回复 {sum(1 for r in actionable if r.classification.action == '需回复')} 项。")
    top_categories = [
        f"{category} {count} 封"
        for category, count in sorted(category_counts.items(), key=lambda item: item[1], reverse=True)
        if count
    ][:3]
    if top_categories:
        lines.append("主要类别：" + "，".join(top_categories) + "。")
    if threaded_count:
        lines.append(f"识别到 {threaded_count} 个会话出现多封新回复，已折叠到对应条目。")
    noisy_count = sum(category_counts.get(category, 0) for category in (CATEGORY_MARKETING, CATEGORY_NEWSLETTER, CATEGORY_SOCIAL))
    if noisy_count:
        lines.append(f"已将 {noisy_count} 封订阅、营销或平台通知压缩到概览区。")
    return lines


_REPLY_PREFIX = re.compile(r"^\s*(re|fwd?|回复|答复|转发)\s*[:：]\s*", re.IGNORECASE)


def _normalize_subject(subject: str) -> str:
    current = (subject or "").strip().lower()
    previous = None
    while previous != current:
        previous = current
        current = _REPLY_PREFIX.sub("", current).strip()
    return current


def _thread_groups(records: list[ProcessedRecord]) -> tuple[set[str], dict[str, int]]:
    # Union-find lets us merge threads discovered via headers (In-Reply-To / References)
    # with threads discovered via normalized subject + sender, so a starter message and
    # its replies end up in the same bucket even when only one side has thread headers.
    parent: dict[str, str] = {}

    def find(value: str) -> str:
        while parent.setdefault(value, value) != value:
            parent[value] = parent.setdefault(parent[value], parent[value])
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for record in records:
        parent.setdefault(record.mail.message_id, record.mail.message_id)

    for record in records:
        headers = record.mail.headers or {}
        in_reply_to = (headers.get("in-reply-to") or "").strip()
        references = (headers.get("references") or "").split()
        targets: list[str] = []
        if in_reply_to:
            targets.append(in_reply_to)
        if references:
            targets.append(references[0].strip())
        for target in targets:
            if not target:
                continue
            parent.setdefault(target, target)
            union(target, record.mail.message_id)

    seen_subject: dict[tuple[str, str], str] = {}
    for record in records:
        normalized = _normalize_subject(record.mail.subject)
        if not normalized:
            continue
        sender_addr = parseaddr(record.mail.sender)[1].lower()
        if not sender_addr:
            continue
        key = (sender_addr, normalized)
        previous = seen_subject.get(key)
        if previous is None:
            seen_subject[key] = record.mail.message_id
        else:
            union(previous, record.mail.message_id)

    groups: dict[str, list[ProcessedRecord]] = {}
    for record in records:
        groups.setdefault(find(record.mail.message_id), []).append(record)

    representative_ids: set[str] = set()
    thread_counts: dict[str, int] = {}
    for group in groups.values():
        # The representative drives what the user sees, so pick the most urgent and most actionable
        # message in the thread. Latest message is only the tiebreaker.
        representative = max(group, key=_thread_representative_key)
        representative_ids.add(representative.mail.message_id)
        if len(group) > 1:
            thread_counts[representative.mail.message_id] = len(group)
    return representative_ids, thread_counts


_PRIORITY_SCORE = {"P0": 3, "P1": 2, "P2": 1}
_ACTION_SCORE = {"需回复": 3, "需执行": 2, "仅知晓": 1}


def _thread_representative_key(record: ProcessedRecord) -> tuple[int, int, datetime]:
    classification = record.classification
    return (
        _PRIORITY_SCORE.get(classification.priority, 0),
        _ACTION_SCORE.get(classification.action, 0),
        record.mail.received_at,
    )


def _sender_bundles(records: list[ProcessedRecord]) -> list[SenderBundle]:
    bundle_categories = {CATEGORY_MARKETING, CATEGORY_NEWSLETTER, CATEGORY_SOCIAL}
    grouped: dict[tuple[str, str], list[ProcessedRecord]] = {}
    for record in records:
        if record.classification.category not in bundle_categories:
            continue
        key = (_sender_label(record.mail.sender), record.classification.category)
        grouped.setdefault(key, []).append(record)

    bundles: list[SenderBundle] = []
    for (sender, category), items in grouped.items():
        if len(items) < 2:
            continue
        subjects = [item.mail.subject or "(无主题)" for item in sorted(items, key=lambda record: record.mail.received_at)[:5]]
        bundles.append(SenderBundle(sender=sender, category=category, count=len(items), subjects=subjects))
    return sorted(bundles, key=lambda bundle: bundle.count, reverse=True)
