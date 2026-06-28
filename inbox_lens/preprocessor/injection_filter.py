from __future__ import annotations

import re


SUSPICIOUS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Verb + (within a short span) a directional/target word. [\s\S]{0,30} tolerates newlines
    # and filler ("the above", "all previous") so phrasings like "forget all previous
    # instructions" or "ignore the above and ..." are caught, not just the exact template.
    (
        "ignore_previous",
        re.compile(
            r"\b(?:ignore|disregard|forget|override|skip|bypass|reset|do\s+not\s+follow)\b"
            r"[\s\S]{0,30}?"
            r"\b(?:previous|prior|above|earlier|preceding|foregoing|former|system|original|instruction|prompt|rule)",
            re.I,
        ),
    ),
    ("system_prompt", re.compile(r"\b(system|developer)\s*prompt\b", re.I)),
    ("role_marker", re.compile(r"<\|(?:system|assistant|user)\|>", re.I)),
    ("reveal_secret", re.compile(r"\b(reveal|print|output|send|show|leak|expose).{0,40}(password|secret|token|api[\s_-]?key|credential)", re.I)),
    ("chinese_override", re.compile(r"(忽略|无视|忽视|忘记|忘掉|覆盖|重置).{0,16}(之前|以上|前面|上述|先前|所有|系统).{0,16}(指令|提示词|规则|设定|要求|命令)", re.I)),
]


def detect_prompt_injection(text: str) -> list[str]:
    flags: list[str] = []
    for name, pattern in SUSPICIOUS_PATTERNS:
        if pattern.search(text):
            flags.append(name)
    return flags
