from __future__ import annotations

import re
from email.utils import parseaddr

from inbox_lens.models import (
    CATEGORY_FINANCE,
    CATEGORY_MARKETING,
    CATEGORY_NEWSLETTER,
    CATEGORY_PERSONAL,
    CATEGORY_SOCIAL,
    CATEGORY_SYSTEM,
    CATEGORY_TRANSACTION,
    Classification,
    ProcessedMail,
)


FINANCE_KEYWORDS = {
    "账单", "发票", "扣费", "付款", "还款", "退款", "invoice", "bill", "billing",
    "payment", "paid", "refund", "receipt", "statement", "subscription renewal",
}
TRANSACTION_KEYWORDS = {
    "订单", "发货", "配送", "预约", "预订", "票", "行程", "确认", "order", "shipped",
    "delivery", "booking", "reservation", "appointment", "ticket", "confirmed",
}
SYSTEM_KEYWORDS = {
    "安全", "登录", "验证码", "密码", "验证", "通知", "alert", "login", "security",
    "verify", "verification", "password", "code", "notification",
}
MARKETING_KEYWORDS = {
    "促销", "优惠", "折扣", "广告", "特价", "deal", "sale", "discount", "offer",
    "coupon", "promo", "promotion",
}
NEWSLETTER_KEYWORDS = {
    "newsletter", "weekly", "digest", "roundup", "周报", "日报", "订阅", "快讯",
}
SOCIAL_DOMAINS = {
    "linkedin.com", "github.com", "gitlab.com", "slack.com", "notion.so",
    "facebookmail.com", "twitter.com", "x.com", "zhihu.com", "quora.com",
}


def classify_with_rules(mail: ProcessedMail) -> Classification:
    searchable = _searchable(mail)
    sender_domain = _sender_domain(mail.raw.sender)
    headers = mail.raw.headers

    category, confidence, rationale = _category_from_rules(searchable, sender_domain, headers)
    priority = _priority_from_rules(category, searchable)
    action = _action_from_rules(category, searchable)
    deadline = _extract_deadline(searchable)

    if deadline and priority == "P2" and category not in {CATEGORY_MARKETING, CATEGORY_NEWSLETTER, CATEGORY_SOCIAL}:
        priority = "P1"
    if mail.security_flags:
        priority = "P0"
        rationale = f"{rationale}; prompt-injection risk: {', '.join(mail.security_flags)}"

    return Classification(
        category=category,
        priority=priority,
        action=action,
        deadline=deadline,
        confidence=confidence,
        rationale=rationale,
        source="rules",
    )


def _category_from_rules(
    searchable: str,
    sender_domain: str,
    headers: dict[str, str],
) -> tuple[str, float, str]:
    if _has_any(searchable, FINANCE_KEYWORDS) or _has_money(searchable):
        return CATEGORY_FINANCE, 0.82, "finance keywords or amount detected"
    if _has_any(searchable, TRANSACTION_KEYWORDS):
        return CATEGORY_TRANSACTION, 0.78, "transaction keywords detected"
    if any(sender_domain == domain or sender_domain.endswith(f".{domain}") for domain in SOCIAL_DOMAINS):
        return CATEGORY_SOCIAL, 0.86, f"known collaboration/social domain: {sender_domain}"
    if _looks_system_generated(searchable, sender_domain, headers):
        return CATEGORY_SYSTEM, 0.76, "system sender or auto-submitted header detected"
    if "list-unsubscribe" in headers:
        if _has_any(searchable, MARKETING_KEYWORDS):
            return CATEGORY_MARKETING, 0.78, "List-Unsubscribe with marketing language"
        return CATEGORY_NEWSLETTER, 0.72, "List-Unsubscribe without direct promotion language"
    if _has_any(searchable, MARKETING_KEYWORDS):
        return CATEGORY_MARKETING, 0.68, "marketing keywords detected"
    if _has_any(searchable, NEWSLETTER_KEYWORDS):
        return CATEGORY_NEWSLETTER, 0.65, "newsletter keywords detected"
    return CATEGORY_PERSONAL, 0.48, "no strong automation signal; defaulting to high-recall personal/work"


def _priority_from_rules(category: str, searchable: str) -> str:
    if category in {CATEGORY_MARKETING, CATEGORY_NEWSLETTER, CATEGORY_SOCIAL}:
        return "P2"
    urgent_terms = {"urgent", "asap", "立即", "紧急", "today", "今天", "overdue", "逾期"}
    if _has_any(searchable, urgent_terms):
        return "P0"
    if category in {CATEGORY_PERSONAL, CATEGORY_FINANCE}:
        return "P1"
    if category == CATEGORY_TRANSACTION and _extract_deadline(searchable):
        return "P1"
    if category == CATEGORY_SYSTEM and _has_any(searchable, {"security", "password", "验证码", "安全", "登录"}):
        return "P0"
    return "P1"


def _action_from_rules(category: str, searchable: str) -> str:
    reply_terms = {"reply", "respond", "回复", "回信", "答复", "let me know"}
    execute_terms = {
        "pay", "付款", "还款", "confirm", "确认", "verify", "验证", "review",
        "complete", "提交", "sign", "签署", "activate", "reset password",
    }
    if _has_any(searchable, reply_terms):
        return "需回复"
    if _has_any(searchable, execute_terms) or category in {CATEGORY_FINANCE, CATEGORY_TRANSACTION}:
        return "需执行"
    return "仅知晓"


DEADLINE_PATTERNS: tuple[str, ...] = (
    r"\b20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}日?\b",
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,\s*20\d{2})?\b",
    r"\b\d{1,2}月\d{1,2}日\b",
    r"\b(?:by|before|until|due|no later than)\s+(?:end of (?:day|week)|eod|eow|cob|"
    r"mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?|"
    r"today|tomorrow|next\s+(?:week|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)|"
    r"\d{1,2}(?::\d{2})?\s*(?:am|pm)?(?:\s+(?:today|tomorrow))?)",
    r"\bin\s+\d+\s+(?:days?|hours?|hrs?)\b",
    r"\bnext\s+(?:mon|tue|wed|thu|fri|sat|sun)(?:day)?\b",
    r"\b(?:today|tomorrow|tonight)\b",
    r"\b(?:this|next)\s+week\b",
    r"截止(?:日期|时间)?[:：]?\s*[^\s。！？.!?]{2,20}",
    r"(?:今天|明天|后天|本周内|下周|周[一二三四五六日天])(?:之前|前|内)?",
    r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
    r"\b\d{1,2}点(?:整|半|\d{1,2}分)?\b",
)


def _extract_deadline(searchable: str) -> str | None:
    for pattern in DEADLINE_PATTERNS:
        match = re.search(pattern, searchable, re.I)
        if match:
            return match.group(0).strip()
    return None


def _looks_system_generated(searchable: str, sender_domain: str, headers: dict[str, str]) -> bool:
    auto_submitted = headers.get("auto-submitted", "").lower()
    sender = sender_domain.lower()
    return (
        auto_submitted not in {"", "no"}
        or any(marker in sender for marker in ("noreply", "no-reply", "notification", "notify"))
        or _has_any(searchable, SYSTEM_KEYWORDS)
    )


def _searchable(mail: ProcessedMail) -> str:
    return f"{mail.raw.sender}\n{mail.raw.subject}\n{mail.clean_text}".lower()


def _sender_domain(sender: str) -> str:
    address = parseaddr(sender)[1]
    return address.split("@", 1)[1].lower() if "@" in address else sender.lower()


def _has_any(text: str, keywords: set[str]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _has_money(text: str) -> bool:
    return bool(re.search(r"(?:[$€£¥￥]\s?\d[\d,]*(?:\.\d{1,2})?|\d[\d,]*(?:\.\d{1,2})?\s?(?:usd|eur|gbp|rmb|cny|元))", text, re.I))
