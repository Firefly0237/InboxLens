from __future__ import annotations

import getpass
import imaplib
import importlib.util
import smtplib
import socket
import ssl
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from inbox_lens.config import Settings, _parse_env_file, env_file_path
from inbox_lens.personal_rules import PersonalRulesError, load_personal_rules
from inbox_lens.storage import Repository


DEFAULT_ENV_PATH = Path(".env")
SECRET_KEYS = {"IMAP_PASSWORD", "SMTP_PASSWORD", "LLM_API_KEY"}
BOOL_KEYS = {"SMTP_USE_SSL", "SMTP_STARTTLS", "SEND_EMPTY_DIGEST", "SEND_FAILURE_EMAIL", "LLM_ENABLED", "LLM_JSON_MODE"}
PLACEHOLDER_FRAGMENTS = {
    "example.com",
    "source_app_password",
    "smtp_app_password",
    "authorization_code",
    "your_",
}


ENV_SECTIONS: list[tuple[str, list[str]]] = [
    ("Source mailbox", ["IMAP_HOST", "IMAP_PORT", "IMAP_USER", "IMAP_PASSWORD", "IMAP_FOLDER"]),
    (
        "Digest sender",
        [
            "SMTP_HOST",
            "SMTP_PORT",
            "SMTP_USER",
            "SMTP_PASSWORD",
            "SMTP_FROM",
            "DIGEST_TO",
            "SMTP_USE_SSL",
            "SMTP_STARTTLS",
        ],
    ),
    (
        "Runtime behavior",
        [
            "DATABASE_PATH",
            "INBOX_LENS_TIMEZONE",
            "BOOTSTRAP_WINDOW_HOURS",
            "RETENTION_DAYS",
            "SEND_EMPTY_DIGEST",
            "SEND_FAILURE_EMAIL",
            "USER_RULES_PATH",
        ],
    ),
    (
        "Optional OpenAI-compatible LLM endpoint",
        ["LLM_ENABLED", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_JSON_MODE", "LLM_TIMEOUT_SECONDS"],
    ),
]


DEFAULT_ENV: dict[str, str] = {
    "IMAP_HOST": "imap.example.com",
    "IMAP_PORT": "993",
    "IMAP_USER": "source@example.com",
    "IMAP_PASSWORD": "source_app_password_or_authorization_code",
    "IMAP_FOLDER": "INBOX",
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": "465",
    "SMTP_USER": "sender@example.com",
    "SMTP_PASSWORD": "smtp_app_password_or_authorization_code",
    "SMTP_FROM": "sender@example.com",
    "DIGEST_TO": "receiver@example.com",
    "SMTP_USE_SSL": "true",
    "SMTP_STARTTLS": "false",
    "DATABASE_PATH": "data/inbox_lens.sqlite",
    "INBOX_LENS_TIMEZONE": "Europe/London",
    "BOOTSTRAP_WINDOW_HOURS": "24",
    "RETENTION_DAYS": "30",
    "SEND_EMPTY_DIGEST": "false",
    "SEND_FAILURE_EMAIL": "true",
    "USER_RULES_PATH": "config/rules.toml",
    "LLM_ENABLED": "false",
    "LLM_BASE_URL": "https://api.openai.com/v1/chat/completions",
    "LLM_API_KEY": "",
    "LLM_MODEL": "gpt-4o-mini",
    "LLM_JSON_MODE": "true",
    "LLM_TIMEOUT_SECONDS": "45",
}


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str
    action: str = ""


def _env_path(path: Path | None = None) -> Path:
    return path if path is not None else env_file_path()


def read_env_values(path: Path | None = None) -> dict[str, str]:
    values = dict(DEFAULT_ENV)
    values.update(_parse_env_file(_env_path(path)))
    return values


def settings_from_values(values: dict[str, str]) -> Settings:
    merged = dict(DEFAULT_ENV)
    merged.update(values)
    return Settings(
        imap_host=merged.get("IMAP_HOST", ""),
        imap_port=_int_value(merged.get("IMAP_PORT", "993"), 993),
        imap_user=merged.get("IMAP_USER", ""),
        imap_password=merged.get("IMAP_PASSWORD", ""),
        imap_folder=merged.get("IMAP_FOLDER", "INBOX"),
        smtp_host=merged.get("SMTP_HOST", ""),
        smtp_port=_int_value(merged.get("SMTP_PORT", "465"), 465),
        smtp_user=merged.get("SMTP_USER", ""),
        smtp_password=merged.get("SMTP_PASSWORD", ""),
        smtp_from=merged.get("SMTP_FROM", merged.get("SMTP_USER", "")),
        digest_to=merged.get("DIGEST_TO", ""),
        smtp_use_ssl=_bool_value(merged.get("SMTP_USE_SSL", "true"), True),
        smtp_starttls=_bool_value(merged.get("SMTP_STARTTLS", "false"), False),
        database_path=Path(merged.get("DATABASE_PATH", "data/inbox_lens.sqlite")),
        timezone_name=merged.get("INBOX_LENS_TIMEZONE", "Europe/London"),
        bootstrap_window_hours=_int_value(merged.get("BOOTSTRAP_WINDOW_HOURS", "24"), 24),
        retention_days=_int_value(merged.get("RETENTION_DAYS", "30"), 30),
        send_empty_digest=_bool_value(merged.get("SEND_EMPTY_DIGEST", "false"), False),
        send_failure_email=_bool_value(merged.get("SEND_FAILURE_EMAIL", "true"), True),
        user_rules_path=Path(merged.get("USER_RULES_PATH", "config/rules.toml")),
        llm_enabled=_bool_value(merged.get("LLM_ENABLED", "false"), False),
        llm_base_url=merged.get("LLM_BASE_URL", ""),
        llm_api_key=merged.get("LLM_API_KEY", ""),
        llm_model=merged.get("LLM_MODEL", ""),
        llm_json_mode=_bool_value(merged.get("LLM_JSON_MODE", "true"), True),
        llm_timeout_seconds=_int_value(merged.get("LLM_TIMEOUT_SECONDS", "45"), 45),
    )


def write_env_values(values: dict[str, str], path: Path | None = None) -> None:
    target = _env_path(path)
    merged = dict(DEFAULT_ENV)
    merged.update({key: str(value) for key, value in values.items()})
    lines: list[str] = []
    known_keys: set[str] = set()
    for section, keys in ENV_SECTIONS:
        if lines:
            lines.append("")
        lines.append(f"# {section}.")
        for key in keys:
            known_keys.add(key)
            lines.append(f"{key}={merged.get(key, '')}")
    extra_keys = sorted(key for key in merged if key not in known_keys)
    if extra_keys:
        lines.append("")
        lines.append("# Extra settings.")
        for key in extra_keys:
            lines.append(f"{key}={merged[key]}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def masked(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}{'*' * max(4, len(value) - 4)}{value[-2:]}"


def is_placeholder(value: str) -> bool:
    lowered = value.lower().strip()
    if not lowered:
        return True
    return any(fragment in lowered for fragment in PLACEHOLDER_FRAGMENTS)


def run_doctor(settings: Settings, network: bool = False, auth: bool = False) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    checks.append(_python_check())
    checks.append(_env_file_check())
    checks.extend(_mail_config_checks(settings))
    checks.extend(_optional_dependency_checks())
    checks.append(_database_check(settings))
    checks.append(_personal_rules_check(settings))
    checks.append(_llm_check(settings))
    if network:
        checks.extend(_network_checks(settings))
    if auth:
        checks.extend(_auth_checks(settings))
    return checks


def print_doctor(checks: Iterable[DoctorCheck]) -> None:
    for check in checks:
        marker = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}.get(check.status, check.status.upper())
        print(f"[{marker}] {check.name}: {check.detail}")
        if check.action:
            print(f"       {check.action}")


def run_wizard(path: Path | None = None) -> None:
    target = _env_path(path)
    current = read_env_values(target)
    print("InboxLens setup wizard")
    print("Press Enter to keep the current value. Password fields stay unchanged when left blank.")
    print()

    updates = dict(current)
    prompts = [
        ("IMAP_HOST", "Source IMAP host"),
        ("IMAP_PORT", "Source IMAP port"),
        ("IMAP_USER", "Source mailbox user"),
        ("IMAP_PASSWORD", "Source mailbox app password / authorization code"),
        ("IMAP_FOLDER", "Source mailbox folder"),
        ("SMTP_HOST", "SMTP host"),
        ("SMTP_PORT", "SMTP port"),
        ("SMTP_USER", "SMTP user"),
        ("SMTP_PASSWORD", "SMTP app password / authorization code"),
        ("SMTP_FROM", "Digest sender address"),
        ("DIGEST_TO", "Digest receiver address"),
        ("SMTP_USE_SSL", "Use SMTP SSL (true/false)"),
        ("SMTP_STARTTLS", "Use SMTP STARTTLS (true/false)"),
        ("INBOX_LENS_TIMEZONE", "Digest timezone"),
        ("LLM_ENABLED", "Enable LLM (true/false)"),
    ]
    for key, label in prompts:
        default = updates.get(key, DEFAULT_ENV.get(key, ""))
        shown = masked(default) if key in SECRET_KEYS else default
        if key in SECRET_KEYS:
            value = getpass.getpass(f"{label} [{shown}]: ")
        else:
            value = input(f"{label} [{shown}]: ").strip()
        if value:
            updates[key] = value

    if updates.get("LLM_ENABLED", "false").lower() in {"1", "true", "yes", "y", "on"}:
        for key, label in (
            ("LLM_BASE_URL", "LLM base URL"),
            ("LLM_API_KEY", "LLM API key"),
            ("LLM_MODEL", "LLM model"),
        ):
            default = updates.get(key, DEFAULT_ENV.get(key, ""))
            shown = masked(default) if key in SECRET_KEYS else default
            value = getpass.getpass(f"{label} [{shown}]: ") if key in SECRET_KEYS else input(f"{label} [{shown}]: ").strip()
            if value:
                updates[key] = value

    write_env_values(updates, target)
    print(f"Saved configuration to {target}")
    print("Next: run `python main.py doctor --network`, then `python main.py run --dry-run --limit 10`.")


def update_env_from_form(form: dict[str, str], path: Path | None = None) -> None:
    target = _env_path(path)
    current = read_env_values(target)
    updates = dict(current)
    for key in DEFAULT_ENV:
        if key in SECRET_KEYS and not form.get(key):
            continue
        if key in BOOL_KEYS:
            updates[key] = "true" if form.get(key) in {"on", "true", "1", "yes"} else "false"
        elif key in form:
            updates[key] = form.get(key, "")
    write_env_values(updates, target)


def _python_check() -> DoctorCheck:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info < (3, 10):
        return DoctorCheck("Python", f"fail", f"current version is {version}", "Use Python 3.10 or newer.")
    return DoctorCheck("Python", "ok", f"current version is {version}")


def _bool_value(value: str, default: bool) -> bool:
    if value == "":
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def _int_value(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _env_file_check() -> DoctorCheck:
    path = env_file_path()
    if path.exists():
        return DoctorCheck(".env", "ok", f"{path} file found")
    example = ".env.example" if path == DEFAULT_ENV_PATH else str(path)
    return DoctorCheck(".env", "fail", f"{path} file not found", f"Run `python main.py wizard` or create {example}.")


def _mail_config_checks(settings: Settings) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    source_values = {
        "IMAP_HOST": settings.imap_host,
        "IMAP_USER": settings.imap_user,
        "IMAP_PASSWORD": settings.imap_password,
    }
    sink_values = {
        "SMTP_HOST": settings.smtp_host,
        "SMTP_USER": settings.smtp_user,
        "SMTP_PASSWORD": settings.smtp_password,
        "SMTP_FROM": settings.smtp_from,
        "DIGEST_TO": settings.digest_to,
    }
    checks.append(_required_group_check("IMAP config", source_values))
    checks.append(_required_group_check("SMTP config", sink_values))
    return checks


def _required_group_check(name: str, values: dict[str, str]) -> DoctorCheck:
    missing = [key for key, value in values.items() if is_placeholder(value)]
    if missing:
        return DoctorCheck(name, "fail", f"missing or placeholder values: {', '.join(missing)}", "Run `python main.py wizard` or edit `.env`.")
    masked_values = ", ".join(f"{key}={masked(value) if key in SECRET_KEYS else value}" for key, value in values.items())
    return DoctorCheck(name, "ok", masked_values)


def _optional_dependency_checks() -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for import_name, install_name, purpose in (
        ("bs4", "beautifulsoup4", "better HTML parsing"),
        ("html2text", "html2text", "better HTML-to-text conversion"),
    ):
        if importlib.util.find_spec(import_name):
            checks.append(DoctorCheck(import_name, "ok", f"installed for {purpose}"))
        else:
            checks.append(DoctorCheck(import_name, "warn", f"not installed; built-in fallback will be used", f"Optional: pip install {install_name}"))
    if sys.version_info < (3, 11) and importlib.util.find_spec("tomli") is None:
        checks.append(DoctorCheck("tomli", "fail", "required for TOML rules on Python 3.10", "Run `pip install tomli`."))
    return checks


def _database_check(settings: Settings) -> DoctorCheck:
    try:
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        Repository(settings.database_path).init_schema()
    except Exception as exc:
        return DoctorCheck("SQLite", "fail", str(exc), "Check DATABASE_PATH permissions.")
    return DoctorCheck("SQLite", "ok", f"database ready at {settings.database_path}")


def _personal_rules_check(settings: Settings) -> DoctorCheck:
    if not settings.user_rules_path.exists():
        return DoctorCheck("Personal rules", "warn", f"{settings.user_rules_path} not found; personal rules disabled", "Copy config/rules.toml.example to config/rules.toml if needed.")
    try:
        count = len(load_personal_rules(settings.user_rules_path))
    except PersonalRulesError as exc:
        return DoctorCheck("Personal rules", "fail", str(exc), "Fix the TOML rule file.")
    return DoctorCheck("Personal rules", "ok", f"{count} rule(s) loaded")


def _llm_check(settings: Settings) -> DoctorCheck:
    if not settings.llm_enabled:
        return DoctorCheck("LLM", "warn", "disabled; rules and heuristic summaries will be used")
    if not settings.llm_is_configured():
        return DoctorCheck("LLM", "fail", "enabled but missing base URL, API key, or model", "Fill LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL.")
    return DoctorCheck("LLM", "ok", f"enabled with model {settings.llm_model}")


def _network_checks(settings: Settings) -> list[DoctorCheck]:
    return [
        _tcp_check("IMAP network", settings.imap_host, settings.imap_port),
        _tcp_check("SMTP network", settings.smtp_host, settings.smtp_port),
    ]


def _tcp_check(name: str, host: str, port: int) -> DoctorCheck:
    if is_placeholder(host):
        return DoctorCheck(name, "fail", f"placeholder host: {host}", "Configure the host first.")
    try:
        with socket.create_connection((host, port), timeout=8):
            pass
    except socket.gaierror as exc:
        return DoctorCheck(name, "fail", f"{host}:{port} DNS lookup failed: {exc}", "Check the host spelling and your network.")
    except socket.timeout:
        return DoctorCheck(name, "fail", f"{host}:{port} timed out", "Check firewall or VPN before retrying.")
    except OSError as exc:
        return DoctorCheck(name, "fail", f"{host}:{port} unreachable: {exc}", "Confirm the host and port with your mail provider.")
    return DoctorCheck(name, "ok", f"{host}:{port} reachable")


def _auth_checks(settings: Settings) -> list[DoctorCheck]:
    return [_imap_login_check(settings), _smtp_login_check(settings)]


def _imap_login_check(settings: Settings) -> DoctorCheck:
    if any(is_placeholder(value) for value in (settings.imap_host, settings.imap_user, settings.imap_password)):
        return DoctorCheck("IMAP auth", "fail", "IMAP host/user/password not configured", "Run `wizard` or fill `.env`.")
    try:
        with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port, timeout=15) as mailbox:
            mailbox.login(settings.imap_user, settings.imap_password)
            mailbox.select(settings.imap_folder, readonly=True)
            mailbox.logout()
    except imaplib.IMAP4.error as exc:
        message = str(exc)
        action = "Check the IMAP authorization code; some providers require a separate app password."
        return DoctorCheck("IMAP auth", "fail", f"login rejected: {message[:160]}", action)
    except (OSError, ssl.SSLError) as exc:
        return DoctorCheck("IMAP auth", "fail", f"network/TLS error: {exc}", "Verify host/port and network access.")
    return DoctorCheck("IMAP auth", "ok", f"signed in as {settings.imap_user}")


def _smtp_login_check(settings: Settings) -> DoctorCheck:
    placeholders = [
        ("SMTP_HOST", settings.smtp_host),
        ("SMTP_USER", settings.smtp_user),
        ("SMTP_PASSWORD", settings.smtp_password),
        ("SMTP_FROM", settings.smtp_from),
        ("DIGEST_TO", settings.digest_to),
    ]
    missing = [key for key, value in placeholders if is_placeholder(value)]
    if missing:
        return DoctorCheck("SMTP auth", "fail", f"missing fields: {', '.join(missing)}", "Run `wizard` or fill `.env`.")
    try:
        if settings.smtp_use_ssl:
            client = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15)
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
            if settings.smtp_starttls:
                client.starttls()
        try:
            client.login(settings.smtp_user, settings.smtp_password)
            client.noop()
        finally:
            try:
                client.quit()
            except smtplib.SMTPException:
                client.close()
    except smtplib.SMTPAuthenticationError as exc:
        return DoctorCheck("SMTP auth", "fail", f"login rejected: {exc.smtp_code} {exc.smtp_error!r}", "Reissue the SMTP authorization code or app password.")
    except smtplib.SMTPException as exc:
        return DoctorCheck("SMTP auth", "fail", f"SMTP error: {exc}", "Verify host/port and whether SSL or STARTTLS is required.")
    except (OSError, ssl.SSLError) as exc:
        return DoctorCheck("SMTP auth", "fail", f"network/TLS error: {exc}", "Check connectivity to the SMTP host.")
    return DoctorCheck("SMTP auth", "ok", f"signed in as {settings.smtp_user}")
