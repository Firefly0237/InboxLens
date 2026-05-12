from __future__ import annotations

import re


SUSPICIOUS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ignore_previous", re.compile(r"ignore (all )?(previous|prior|above) instructions", re.I)),
    ("disregard_instructions", re.compile(r"disregard (all )?(previous|prior|above) instructions", re.I)),
    ("system_prompt", re.compile(r"\b(system|developer)\s*prompt\b", re.I)),
    ("role_marker", re.compile(r"<\|(?:system|assistant|user)\|>", re.I)),
    ("reveal_secret", re.compile(r"\b(reveal|print|output|send).{0,40}(password|secret|token|api key)\b", re.I)),
    ("chinese_override", re.compile(r"(忽略|无视).{0,12}(之前|以上|所有).{0,12}(指令|提示词)", re.I)),
]


def detect_prompt_injection(text: str) -> list[str]:
    flags: list[str] = []
    for name, pattern in SUSPICIOUS_PATTERNS:
        if pattern.search(text):
            flags.append(name)
    return flags
