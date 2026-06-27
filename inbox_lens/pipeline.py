from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from inbox_lens.classifier import classify_with_optional_llm, classify_with_rules
from inbox_lens.config import Settings
from inbox_lens.fetcher import IMAPSource
from inbox_lens.llm import OpenAICompatibleClient
from inbox_lens.models import Digest, ProcessedRecord
from inbox_lens.personal_rules import apply_loaded_personal_rules, load_personal_rules
from inbox_lens.preprocessor import preprocess_mail
from inbox_lens.renderer import render_digest_html, render_digest_text
from inbox_lens.sender import SMTPSink
from inbox_lens.storage import Repository
from inbox_lens.summarizer import build_digest, summarize_email


def run_digest(
    settings: Settings,
    dry_run: bool = False,
    limit: int | None = None,
    force_send_empty: bool = False,
) -> Digest:
    repo = Repository(settings.database_path)
    since = _since_window(repo, settings)
    run_id = repo.start_run(since)
    records: list[ProcessedRecord] = []
    try:
        client = _build_llm_client(settings)
        personal_rules = load_personal_rules(settings.user_rules_path)
        source = IMAPSource(settings)
        raw_messages = source.fetch_since(since, limit=limit, already_processed=repo.already_processed)
        for raw_mail in raw_messages:
            if repo.already_processed(raw_mail.message_id):
                continue
            processed = preprocess_mail(raw_mail)
            base_classification = classify_with_rules(processed)
            ruled_classification = apply_loaded_personal_rules(processed, base_classification, personal_rules)
            classification = classify_with_optional_llm(processed, ruled_classification, client)
            summary = summarize_email(processed, classification, client)
            records.append(ProcessedRecord(raw_mail, classification, summary))

        generated_at = datetime.now(_local_zone(settings))
        digest = build_digest(records, since.astimezone(generated_at.tzinfo), generated_at)
        should_send = bool(records) or force_send_empty or settings.send_empty_digest
        if should_send:
            html = render_digest_html(digest, settings.timezone_name)
            text = render_digest_text(digest)
            if dry_run:
                _write_preview(html, text)
                print(text)
            else:
                subject = f"InboxLens 每日邮件简报 - {generated_at.strftime('%Y-%m-%d')}"
                SMTPSink(settings).send(subject=subject, html=html, text=text)
        elif dry_run:
            print("No new messages in the selected window.")

        if dry_run:
            repo.finish_run(run_id, "dry_run", len(records))
        else:
            # Mark messages as processed only after render/send has succeeded.
            stored = repo.save_messages(run_id, records)
            if stored < len(records):
                # Distinct emails can share a Message-ID (resent/forwarded mail); INSERT OR
                # IGNORE drops the duplicate. Surface it so the loss is not silent.
                print(
                    f"警告：{len(records) - stored} 封邮件因 Message-ID 冲突未写入数据库"
                    "（可能是被转发或重复的邮件）。"
                )
            repo.cleanup(settings.retention_days)
            # "empty" surfaces a no-op run in the dashboard so the user can tell quiet days from missed runs.
            status = "success" if records else "empty"
            repo.finish_run(run_id, status, len(records))
        return digest
    except Exception as exc:
        repo.finish_run(run_id, "failed", len(records), str(exc))
        if settings.send_failure_email and not dry_run:
            _try_send_failure_notice(settings, exc)
        raise


def send_test_email(settings: Settings) -> None:
    now = datetime.now(_local_zone(settings))
    html = (
        "<html><body><p>InboxLens SMTP test succeeded.</p>"
        f"<p>Time: {now.isoformat()}</p></body></html>"
    )
    text = f"InboxLens SMTP test succeeded.\nTime: {now.isoformat()}"
    SMTPSink(settings).send("InboxLens SMTP 连通性测试", html=html, text=text)


def _since_window(repo: Repository, settings: Settings) -> datetime:
    last_success = repo.last_success_finished_at()
    if last_success:
        # A small overlap handles clock skew and IMAP date granularity; Message-ID keeps the run idempotent.
        return last_success - timedelta(minutes=5)
    return datetime.now(UTC) - timedelta(hours=settings.bootstrap_window_hours)


def _build_llm_client(settings: Settings) -> OpenAICompatibleClient | None:
    if not settings.llm_is_configured():
        return None
    return OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        json_mode=settings.llm_json_mode,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def _local_zone(settings: Settings):
    try:
        return ZoneInfo(settings.timezone_name)
    except ZoneInfoNotFoundError:
        return UTC


def _write_preview(html: str, text: str) -> None:
    out_dir = Path("out")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "last_digest.html").write_text(html, encoding="utf-8")
    (out_dir / "last_digest.txt").write_text(text, encoding="utf-8")


def _try_send_failure_notice(settings: Settings, exc: Exception) -> None:
    try:
        html = (
            "<html><body><p>InboxLens 运行失败。</p>"
            f"<pre>{_escape_basic(str(exc))}</pre></body></html>"
        )
        text = f"InboxLens 运行失败：\n{exc}"
        SMTPSink(settings).send("InboxLens 运行失败", html=html, text=text)
    except Exception:
        pass


def _escape_basic(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
