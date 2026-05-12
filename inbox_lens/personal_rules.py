from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from inbox_lens.models import ACTIONS, CATEGORIES, PRIORITIES, Classification, ProcessedMail


class PersonalRulesError(ValueError):
    pass


def apply_personal_rules(
    mail: ProcessedMail,
    classification: Classification,
    rules_path: Path,
) -> Classification:
    return apply_loaded_personal_rules(mail, classification, load_personal_rules(rules_path))


def apply_loaded_personal_rules(
    mail: ProcessedMail,
    classification: Classification,
    rules: list[dict[str, Any]],
) -> Classification:
    for rule in rules:
        if _matches_rule(mail, rule):
            return _apply_rule(classification, rule)
    return classification


def load_personal_rules(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = _load_toml(path)
    except Exception as exc:
        raise PersonalRulesError(f"Failed to load personal rules from {path}: {exc}") from exc
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        raise PersonalRulesError("[[rules]] must be an array of tables")
    return [_validate_rule(rule, index + 1) for index, rule in enumerate(rules)]


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError as exc:
            raise PersonalRulesError("TOML rules require Python 3.11+ or the tomli package") from exc
    with path.open("rb") as file:
        data = tomllib.load(file)
    if not isinstance(data, dict):
        raise PersonalRulesError("rules file must contain a TOML table")
    return data


def _validate_rule(rule: Any, index: int) -> dict[str, Any]:
    if not isinstance(rule, dict):
        raise PersonalRulesError(f"rule #{index} must be a table")
    normalized = dict(rule)
    for key in ("sender_contains", "subject_contains", "body_contains"):
        if key in normalized:
            normalized[key] = _string_list(normalized[key], f"rule #{index}.{key}")
    if "category" in normalized and normalized["category"] not in CATEGORIES:
        raise PersonalRulesError(f"rule #{index}.category must be one of: {', '.join(CATEGORIES)}")
    if "priority" in normalized and normalized["priority"] not in PRIORITIES:
        raise PersonalRulesError(f"rule #{index}.priority must be one of: {', '.join(PRIORITIES)}")
    if "action" in normalized and normalized["action"] not in ACTIONS:
        raise PersonalRulesError(f"rule #{index}.action must be one of: {', '.join(ACTIONS)}")
    if "deadline" in normalized and normalized["deadline"] is not None:
        normalized["deadline"] = str(normalized["deadline"])
    if "note" in normalized and normalized["note"] is not None:
        normalized["note"] = str(normalized["note"])
    if not any(key in normalized for key in ("sender_contains", "subject_contains", "body_contains")):
        raise PersonalRulesError(f"rule #{index} needs at least one match condition")
    if not any(key in normalized for key in ("category", "priority", "action", "deadline", "note")):
        raise PersonalRulesError(f"rule #{index} needs at least one override")
    return normalized


def _string_list(value: Any, label: str) -> list[str]:
    if isinstance(value, str):
        return [value.lower()]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PersonalRulesError(f"{label} must be a string or a list of strings")
    return [item.lower() for item in value]


def _matches_rule(mail: ProcessedMail, rule: dict[str, Any]) -> bool:
    checks: list[bool] = []
    if "sender_contains" in rule:
        sender = mail.raw.sender.lower()
        checks.append(any(value in sender for value in rule["sender_contains"]))
    if "subject_contains" in rule:
        subject = mail.raw.subject.lower()
        checks.append(any(value in subject for value in rule["subject_contains"]))
    if "body_contains" in rule:
        body = mail.clean_text.lower()
        checks.append(any(value in body for value in rule["body_contains"]))
    return bool(checks) and all(checks)


def _apply_rule(classification: Classification, rule: dict[str, Any]) -> Classification:
    updates: dict[str, Any] = {
        "source": "personal_rules",
        "confidence": max(classification.confidence, 0.95),
    }
    for key in ("category", "priority", "action", "deadline"):
        if key in rule:
            updates[key] = rule[key]
    note = rule.get("note")
    if note:
        updates["rationale"] = f"{classification.rationale}; personal rule: {note}"
    else:
        updates["rationale"] = f"{classification.rationale}; personal rule matched"
    return replace(classification, **updates)
