from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_file_path() -> Path:
    return Path(os.getenv("INBOX_LENS_ENV_FILE", ".env"))


def load_dotenv(path: str | Path | None = None) -> None:
    target = Path(path) if path is not None else env_file_path()
    for key, value in _parse_env_file(target).items():
        os.environ.setdefault(key, value)


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    imap_host: str
    imap_port: int
    imap_user: str
    imap_password: str
    imap_folder: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    digest_to: str
    smtp_use_ssl: bool
    smtp_starttls: bool
    database_path: Path
    timezone_name: str
    bootstrap_window_hours: int
    retention_days: int
    send_empty_digest: bool
    send_failure_email: bool
    user_rules_path: Path
    llm_enabled: bool
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_json_mode: bool
    llm_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            imap_host=os.getenv("IMAP_HOST", "imap.example.com"),
            imap_port=_int("IMAP_PORT", 993),
            imap_user=os.getenv("IMAP_USER", ""),
            imap_password=os.getenv("IMAP_PASSWORD", ""),
            imap_folder=os.getenv("IMAP_FOLDER", "INBOX"),
            smtp_host=os.getenv("SMTP_HOST", "smtp.example.com"),
            smtp_port=_int("SMTP_PORT", 465),
            smtp_user=os.getenv("SMTP_USER", ""),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            smtp_from=os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")),
            digest_to=os.getenv("DIGEST_TO", ""),
            smtp_use_ssl=_bool("SMTP_USE_SSL", True),
            smtp_starttls=_bool("SMTP_STARTTLS", False),
            database_path=Path(os.getenv("DATABASE_PATH", "data/inbox_lens.sqlite")),
            timezone_name=os.getenv("INBOX_LENS_TIMEZONE", "Europe/London"),
            bootstrap_window_hours=_int("BOOTSTRAP_WINDOW_HOURS", 24),
            retention_days=_int("RETENTION_DAYS", 30),
            send_empty_digest=_bool("SEND_EMPTY_DIGEST", False),
            send_failure_email=_bool("SEND_FAILURE_EMAIL", True),
            user_rules_path=Path(os.getenv("USER_RULES_PATH", "config/rules.toml")),
            llm_enabled=_bool("LLM_ENABLED", False),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1/chat/completions"),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            llm_json_mode=_bool("LLM_JSON_MODE", True),
            llm_timeout_seconds=_int("LLM_TIMEOUT_SECONDS", 45),
        )

    def require_source(self) -> None:
        missing = [
            name
            for name, value in {
                "IMAP_USER": self.imap_user,
                "IMAP_PASSWORD": self.imap_password,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"Missing source mailbox config: {', '.join(missing)}")

    def require_sink(self) -> None:
        missing = [
            name
            for name, value in {
                "SMTP_USER": self.smtp_user,
                "SMTP_PASSWORD": self.smtp_password,
                "SMTP_FROM": self.smtp_from,
                "DIGEST_TO": self.digest_to,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"Missing SMTP digest config: {', '.join(missing)}")

    def llm_is_configured(self) -> bool:
        return self.llm_enabled and bool(self.llm_base_url and self.llm_api_key and self.llm_model)
