from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from email.utils import parseaddr
from html import escape

from inbox_lens.models import CATEGORY_MARKETING, CATEGORY_NEWSLETTER, CATEGORY_SOCIAL, Digest, ProcessedRecord


def render_digest_html(digest: Digest, timezone_name: str = "UTC") -> str:
    generated = _format_dt(digest.generated_at)
    since = _format_dt(digest.since)
    total = len(digest.records)
    display_records = _representatives(digest)
    rows: list[str] = [
        "<!doctype html><html><body style=\"margin:0;padding:0;background:#f6f7f9;color:#1f2937;font-family:Arial,'Microsoft YaHei',sans-serif;\">",
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"background:#f6f7f9;padding:20px 0;\"><tr><td align=\"center\">",
        "<table role=\"presentation\" width=\"720\" cellspacing=\"0\" cellpadding=\"0\" style=\"width:720px;max-width:96%;background:#ffffff;border:1px solid #e5e7eb;\">",
        _header_html(generated, since, total, digest, display_records),
    ]
    if not digest.records:
        rows.append(_section_html("今日没有新邮件", "<p style=\"margin:0;color:#4b5563;\">当前窗口内没有需要汇总的新邮件。</p>"))
    else:
        rows.append(_overview_lines_section(digest.overview_lines))
        rows.append(_action_agenda_section(_action_records(display_records), digest.thread_counts))
        rows.append(_records_section("今日重点", [r for r in display_records if r.classification.priority == "P0"], digest.thread_counts))
        rows.append(_records_section("分类浏览", [r for r in display_records if r.classification.priority == "P1"], digest.thread_counts))
        rows.append(_overview_section([r for r in display_records if r.classification.priority == "P2"], digest.thread_counts))
    rows.append(_footer_html(timezone_name))
    rows.append("</table></td></tr></table></body></html>")
    return "".join([row for row in rows if row])


def render_digest_text(digest: Digest) -> str:
    lines = [
        f"InboxLens 每日邮件简报",
        f"生成时间：{_format_dt(digest.generated_at)}",
        f"统计窗口：{_format_dt(digest.since)} -> {_format_dt(digest.generated_at)}",
        f"新邮件：{len(digest.records)}，P0：{digest.priority_counts.get('P0', 0)}，P1：{digest.priority_counts.get('P1', 0)}，P2：{digest.priority_counts.get('P2', 0)}",
        "",
    ]
    if not digest.records:
        lines.append("今日没有新邮件。")
        return "\n".join(lines)
    if digest.overview_lines:
        lines.append("== 今日总览 ==")
        for line in digest.overview_lines:
            lines.append(f"- {line}")
        lines.append("")
    display_records = _representatives(digest)
    action_records = _action_records(display_records)
    if action_records:
        lines.append("== 待处理事项 ==")
        for record in action_records:
            action = _agenda_action_label(record)
            deadline = f"；时效：{record.classification.deadline}" if record.classification.deadline else ""
            thread_tag = _thread_tag(record, digest.thread_counts)
            lines.append(f"- {record.mail.subject or '(无主题)'}{thread_tag}：{action}{deadline}")
        lines.append("")
    for title, records in (
        ("今日重点", [r for r in display_records if r.classification.priority == "P0"]),
        ("分类浏览", [r for r in display_records if r.classification.priority == "P1"]),
        ("概览", [r for r in display_records if r.classification.priority == "P2"]),
    ):
        if not records:
            continue
        lines.append(f"== {title} ==")
        for record in records:
            lines.extend(_record_text(record, digest.thread_counts))
        lines.append("")
    return "\n".join(lines).strip()


def _header_html(generated: str, since: str, total: int, digest: Digest, display_records: list[ProcessedRecord]) -> str:
    return f"""
<tr><td style="padding:24px 28px 16px 28px;border-bottom:1px solid #e5e7eb;">
  <h1 style="margin:0 0 8px 0;font-size:24px;line-height:32px;color:#111827;">InboxLens 每日邮件简报</h1>
  <p style="margin:0;color:#4b5563;font-size:14px;line-height:22px;">生成时间：{escape(generated)} · 统计窗口：{escape(since)} 至 {escape(generated)}</p>
  <p style="margin:12px 0 0 0;color:#111827;font-size:15px;line-height:22px;">共 {total} 封新邮件，其中 P0 {digest.priority_counts.get('P0', 0)} 封，P1 {digest.priority_counts.get('P1', 0)} 封，待处理 {_action_count(display_records)} 项。</p>
</td></tr>
"""


def _overview_lines_section(lines: list[str]) -> str:
    if not lines:
        return ""
    body = "".join(
        f"<p style=\"margin:0 0 8px 0;color:#1f2937;font-size:14px;line-height:22px;\">{escape(line)}</p>"
        for line in lines
    )
    return _section_html("今日总览", body)


def _action_agenda_section(records: list[ProcessedRecord], thread_counts: dict[str, int]) -> str:
    if not records:
        return ""
    rows: list[str] = []
    for record in records[:8]:
        action = _agenda_action_label(record)
        deadline = f" · 时效：{record.classification.deadline}" if record.classification.deadline else ""
        thread_tag = _thread_tag(record, thread_counts)
        rows.append(
            f"<tr><td style=\"padding:8px 0;border-top:1px solid #eef2f7;\">"
            f"<p style=\"margin:0;color:#111827;font-size:14px;line-height:22px;font-weight:bold;\">{escape(record.mail.subject or '(无主题)')}{escape(thread_tag)}</p>"
            f"<p style=\"margin:2px 0 0 0;color:#4b5563;font-size:13px;line-height:20px;\">"
            f"{escape(action)}{escape(deadline)} · {escape(_sender_label(record.mail.sender))}</p>"
            f"</td></tr>"
        )
    if len(records) > 8:
        rows.append(
            f"<tr><td style=\"padding:8px 0;color:#6b7280;font-size:13px;line-height:20px;\">"
            f"另有 {len(records) - 8} 项待处理事项。</td></tr>"
        )
    body = f"<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\">{''.join(rows)}</table>"
    return _section_html("待处理事项", body)


def _records_section(title: str, records: list[ProcessedRecord], thread_counts: dict[str, int]) -> str:
    if not records:
        return ""
    grouped: dict[str, list[ProcessedRecord]] = defaultdict(list)
    for record in records:
        grouped[record.classification.category].append(record)
    body: list[str] = []
    for category, items in grouped.items():
        body.append(f"<h3 style=\"margin:16px 0 8px 0;font-size:15px;color:#374151;\">{escape(category)} ({len(items)} 封)</h3>")
        for record in items:
            body.append(_record_html(record, thread_counts))
    return _section_html(title, "".join(body))


def _overview_section(records: list[ProcessedRecord], thread_counts: dict[str, int]) -> str:
    if not records:
        return ""
    noisy = {CATEGORY_MARKETING, CATEGORY_NEWSLETTER, CATEGORY_SOCIAL}
    grouped: dict[str, list[ProcessedRecord]] = defaultdict(list)
    details: list[ProcessedRecord] = []
    for record in records:
        if record.classification.category in noisy:
            grouped[record.classification.category].append(record)
        else:
            details.append(record)
    body: list[str] = []
    for category, items in grouped.items():
        senders = _top_senders(items)
        body.append(
            f"<p style=\"margin:0 0 8px 0;color:#4b5563;font-size:14px;line-height:22px;\">"
            f"{escape(category)}：{len(items)} 封"
            f"{'，主要来自：' + escape(', '.join(senders)) if senders else ''}</p>"
        )
    bundle_html = _sender_bundles_html(records)
    if bundle_html:
        body.append(bundle_html)
    for record in details:
        body.append(_record_html(record, thread_counts))
    return _section_html("概览", "".join(body))


def _sender_bundles_html(records: list[ProcessedRecord]) -> str:
    grouped: dict[tuple[str, str], list[ProcessedRecord]] = defaultdict(list)
    for record in records:
        if record.classification.category in {CATEGORY_MARKETING, CATEGORY_NEWSLETTER, CATEGORY_SOCIAL}:
            grouped[(_sender_label(record.mail.sender), record.classification.category)].append(record)
    bundles = []
    for (sender, category), items in sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True):
        if len(items) < 2:
            continue
        subjects = "；".join(escape(item.mail.subject or "(无主题)") for item in items[:3])
        bundles.append(
            f"<li style=\"margin:0 0 6px 0;color:#4b5563;font-size:13px;line-height:20px;\">"
            f"{escape(sender)} · {escape(category)} {len(items)} 封：{subjects}</li>"
        )
    if not bundles:
        return ""
    return f"<ul style=\"margin:10px 0 0 18px;padding:0;\">{''.join(bundles[:6])}</ul>"


def _record_html(record: ProcessedRecord, thread_counts: dict[str, int] | None = None) -> str:
    mail = record.mail
    classification = record.classification
    summary = record.summary
    facts = "".join(
        f"<li style=\"margin:0 0 4px 0;\">{escape(fact)}</li>"
        for fact in summary.key_facts
    )
    facts_html = f"<ul style=\"margin:8px 0 0 18px;padding:0;color:#4b5563;font-size:13px;line-height:20px;\">{facts}</ul>" if facts else ""
    action_html = (
        f"<p style=\"margin:8px 0 0 0;color:#991b1b;font-size:13px;line-height:20px;\">建议行动：{escape(summary.action_required)}</p>"
        if summary.action_required else ""
    )
    thread_tag = _thread_tag(record, thread_counts or {})
    return f"""
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-top:1px solid #eef2f7;padding:10px 0;">
  <tr><td style="padding:10px 0;">
    <p style="margin:0 0 4px 0;color:#111827;font-size:15px;line-height:22px;font-weight:bold;">{escape(_sender_label(mail.sender))} / {escape(mail.subject or '(无主题)')}{escape(thread_tag)}</p>
    <p style="margin:0;color:#4b5563;font-size:13px;line-height:20px;">{escape(classification.priority)} · {escape(classification.action)} · {escape(_format_dt(mail.received_at))}</p>
    <p style="margin:8px 0 0 0;color:#1f2937;font-size:14px;line-height:22px;">{escape(summary.one_liner)}</p>
    {facts_html}
    {action_html}
  </td></tr>
</table>
"""


def _section_html(title: str, body: str) -> str:
    return f"""
<tr><td style="padding:20px 28px;border-bottom:1px solid #e5e7eb;">
  <h2 style="margin:0 0 12px 0;font-size:18px;line-height:26px;color:#111827;">{escape(title)}</h2>
  {body}
</td></tr>
"""


def _footer_html(timezone_name: str) -> str:
    return f"""
<tr><td style="padding:16px 28px;color:#6b7280;font-size:12px;line-height:18px;">
  本简报由 InboxLens 生成。时区：{escape(timezone_name)}。邮件原文未写入本地数据库。
</td></tr>
"""


def _record_text(record: ProcessedRecord, thread_counts: dict[str, int] | None = None) -> list[str]:
    thread_tag = _thread_tag(record, thread_counts or {})
    lines = [
        f"- {record.mail.subject or '(无主题)'}{thread_tag}",
        f"  发件人：{_sender_label(record.mail.sender)}",
        f"  分类：{record.classification.category} / {record.classification.priority} / {record.classification.action}",
        f"  摘要：{record.summary.one_liner}",
    ]
    if record.summary.key_facts:
        lines.append(f"  关键事实：{'；'.join(record.summary.key_facts)}")
    if record.summary.action_required:
        lines.append(f"  建议行动：{record.summary.action_required}")
    return lines


def _top_senders(records: list[ProcessedRecord]) -> list[str]:
    counts: dict[str, int] = {}
    for record in records:
        label = _sender_label(record.mail.sender)
        counts[label] = counts.get(label, 0) + 1
    return [name for name, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]]


def _sender_label(sender: str) -> str:
    display, address = parseaddr(sender)
    return display or address or sender or "(unknown)"


def _format_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def _agenda_action_label(record: ProcessedRecord) -> str:
    label = record.summary.action_required or record.classification.action
    # Items reach the agenda either because they need action or only because they carry a
    # deadline. For the deadline-only case the action is "仅知晓", which reads as a
    # contradictory to-do, so surface the deadline instead of the bare label.
    if label == "仅知晓":
        return "留意时效" if record.classification.deadline else "仅知晓"
    return label


def _action_records(records: list[ProcessedRecord]) -> list[ProcessedRecord]:
    actionable = [
        record
        for record in records
        if record.classification.action != "仅知晓" or bool(record.classification.deadline)
    ]
    return sorted(actionable, key=_agenda_sort_key)


def _agenda_sort_key(record: ProcessedRecord) -> tuple[int, int, datetime]:
    priority_rank = {"P0": 0, "P1": 1, "P2": 2}.get(record.classification.priority, 3)
    action_rank = {"需回复": 0, "需执行": 1, "仅知晓": 2}.get(record.classification.action, 3)
    # Priority is the primary key; action breaks ties within a priority. These are two
    # independent scales, so combining them with min() (the old bug) scrambled the order.
    return priority_rank, action_rank, record.mail.received_at


def _action_count(records: list[ProcessedRecord]) -> int:
    return len(_action_records(records))


def _representatives(digest: Digest) -> list[ProcessedRecord]:
    if not digest.representative_ids:
        return list(digest.records)
    return [record for record in digest.records if record.mail.message_id in digest.representative_ids]


def _thread_tag(record: ProcessedRecord, thread_counts: dict[str, int]) -> str:
    count = thread_counts.get(record.mail.message_id, 0)
    if count > 1:
        return f"（同主题 {count} 封）"
    return ""
