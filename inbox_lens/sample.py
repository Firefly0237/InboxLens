from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from inbox_lens.config import Settings
from inbox_lens.models import Classification, ProcessedRecord, RawMail, Summary
from inbox_lens.renderer import render_digest_html, render_digest_text
from inbox_lens.summarizer import build_digest


def render_sample_digest(settings: Settings) -> None:
    now = datetime.now(UTC)
    recipients = settings.digest_to or "you@example.com"
    records: list[ProcessedRecord] = [
        ProcessedRecord(
            mail=RawMail(
                uid="1",
                message_id="<sample-personal-1@example.com>",
                sender="Alice <alice@example.com>",
                recipients=recipients,
                subject="项目周会纪要 + 下一步分工",
                received_at=now - timedelta(hours=1),
                headers={},
                text_body="",
                html_body="",
            ),
            classification=Classification("个人/工作沟通", "P0", "需回复", "周三", 0.78, "sample"),
            summary=Summary(
                "Alice 同步了周会决议，请在周三前确认你负责的两项任务。",
                ["时效：周三", "对方：Alice", "动作：确认分工"],
                "周三之前回复确认两项任务",
            ),
        ),
        ProcessedRecord(
            mail=RawMail(
                uid="2",
                message_id="<sample-personal-2@example.com>",
                sender="Alice <alice@example.com>",
                recipients=recipients,
                subject="Re: 项目周会纪要 + 下一步分工",
                received_at=now - timedelta(minutes=45),
                headers={"in-reply-to": "<sample-personal-1@example.com>"},
                text_body="",
                html_body="",
            ),
            classification=Classification("个人/工作沟通", "P1", "仅知晓", None, 0.62, "sample"),
            summary=Summary("Alice 补充了一份周会附件。", ["附件：minutes.pdf"], None),
        ),
        ProcessedRecord(
            mail=RawMail(
                uid="3",
                message_id="<sample-finance@example.com>",
                sender="Bank Notice <notice@bank.example>",
                recipients=recipients,
                subject="信用卡 5 月账单已生成",
                received_at=now - timedelta(hours=3),
                headers={},
                text_body="",
                html_body="",
            ),
            classification=Classification("账单与财务", "P1", "需执行", "5月18日", 0.86, "sample"),
            summary=Summary("信用卡账单已生成，需要在还款日前处理。", ["金额：¥3,247.00", "时效：5月18日"], "在 5月18日前完成还款"),
        ),
        ProcessedRecord(
            mail=RawMail(
                uid="4",
                message_id="<sample-transaction@example.com>",
                sender="顺丰速运 <notice@sf-express.example>",
                recipients=recipients,
                subject="您的订单 SF1234567890 已发货",
                received_at=now - timedelta(hours=4),
                headers={},
                text_body="",
                html_body="",
            ),
            classification=Classification("事务记录", "P1", "需执行", "tomorrow", 0.78, "sample"),
            summary=Summary("顺丰速运 的事务邮件：您的订单 SF1234567890 已发货", ["物流：SF1234567890", "时效：tomorrow"], "明日到达，留意签收"),
        ),
        ProcessedRecord(
            mail=RawMail(
                uid="5",
                message_id="<sample-system@example.com>",
                sender="Security <noreply@accounts.example>",
                recipients=recipients,
                subject="新设备登录提醒",
                received_at=now - timedelta(hours=2),
                headers={"auto-submitted": "auto-generated"},
                text_body="",
                html_body="",
            ),
            classification=Classification("系统通知", "P0", "需执行", "今天", 0.76, "sample"),
            summary=Summary("检测到来自新设备的登录请求。", ["地点：Edinburgh", "时间：今天 09:12"], "如非本人立刻修改密码"),
        ),
        ProcessedRecord(
            mail=RawMail(
                uid="6",
                message_id="<sample-newsletter@example.com>",
                sender="Bytes Newsletter <news@bytesnewsletter.example>",
                recipients=recipients,
                subject="Bytes Issue 304",
                received_at=now - timedelta(hours=5),
                headers={"list-unsubscribe": "<mailto:unsubscribe@example.com>"},
                text_body="",
                html_body="",
            ),
            classification=Classification("资讯订阅", "P2", "仅知晓", None, 0.72, "sample"),
            summary=Summary("Bytes Newsletter：Bytes Issue 304", [], None),
        ),
        ProcessedRecord(
            mail=RawMail(
                uid="7",
                message_id="<sample-marketing@example.com>",
                sender="Coffee Shop <promo@cafe.example>",
                recipients=recipients,
                subject="周末买一送一",
                received_at=now - timedelta(hours=6),
                headers={"list-unsubscribe": "<mailto:unsubscribe@cafe.example>"},
                text_body="",
                html_body="",
            ),
            classification=Classification("营销推广", "P2", "仅知晓", None, 0.68, "sample"),
            summary=Summary("Coffee Shop：周末买一送一", [], None),
        ),
        ProcessedRecord(
            mail=RawMail(
                uid="8",
                message_id="<sample-marketing-2@example.com>",
                sender="Coffee Shop <promo@cafe.example>",
                recipients=recipients,
                subject="本周新品上架",
                received_at=now - timedelta(hours=7),
                headers={"list-unsubscribe": "<mailto:unsubscribe@cafe.example>"},
                text_body="",
                html_body="",
            ),
            classification=Classification("营销推广", "P2", "仅知晓", None, 0.68, "sample"),
            summary=Summary("Coffee Shop：本周新品上架", [], None),
        ),
        ProcessedRecord(
            mail=RawMail(
                uid="9",
                message_id="<sample-social@example.com>",
                sender="GitHub <notifications@github.com>",
                recipients=recipients,
                subject="[org/repo] PR #128 等待 review",
                received_at=now - timedelta(hours=8),
                headers={},
                text_body="",
                html_body="",
            ),
            classification=Classification("社交与协作平台", "P2", "仅知晓", None, 0.86, "sample"),
            summary=Summary("GitHub：[org/repo] PR #128 等待 review", [], None),
        ),
    ]
    digest = build_digest(records, now - timedelta(days=1), now)
    html = render_digest_html(digest, settings.timezone_name)
    text = render_digest_text(digest)
    out_dir = Path("out")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sample_digest.html").write_text(html, encoding="utf-8")
    (out_dir / "sample_digest.txt").write_text(text, encoding="utf-8")
