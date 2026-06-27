from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from inbox_lens.models import ProcessedRecord


class Repository:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    since_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    mail_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    uid TEXT,
                    run_id INTEGER NOT NULL,
                    sender TEXT,
                    recipients TEXT,
                    subject TEXT,
                    received_at TEXT,
                    processed_at TEXT NOT NULL,
                    category TEXT,
                    priority TEXT,
                    action TEXT,
                    deadline TEXT,
                    classification_json TEXT,
                    summary_json TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );
                """
            )

    def start_run(self, since: datetime) -> int:
        self.init_schema()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO runs (started_at, since_at, status) VALUES (?, ?, 'running')",
                (_to_iso(datetime.now(UTC)), _to_iso(since)),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, mail_count: int, error: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET finished_at = ?, status = ?, mail_count = ?, error = ?
                WHERE id = ?
                """,
                (_to_iso(datetime.now(UTC)), status, mail_count, error, run_id),
            )

    def last_success_finished_at(self) -> datetime | None:
        self.init_schema()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT finished_at FROM runs WHERE status IN ('success', 'empty') AND finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return _from_iso(row["finished_at"])

    def already_processed(self, message_id: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM messages WHERE message_id = ? LIMIT 1",
                (message_id,),
            ).fetchone()
        return row is not None

    def save_messages(self, run_id: int, records: list[ProcessedRecord]) -> int:
        """Persist records, returning the number actually inserted.

        message_id is the PRIMARY KEY and inserts use INSERT OR IGNORE, so a record whose
        Message-ID collides with an existing row (resent/forwarded mail, or a previously
        processed message) is dropped. Returning the count lets the caller surface that loss
        instead of it happening silently.
        """
        now = _to_iso(datetime.now(UTC))
        rows = []
        for record in records:
            classification = record.classification
            summary = record.summary
            rows.append(
                (
                    record.mail.message_id,
                    record.mail.uid,
                    run_id,
                    record.mail.sender,
                    record.mail.recipients,
                    record.mail.subject,
                    _to_iso(record.mail.received_at),
                    now,
                    classification.category,
                    classification.priority,
                    classification.action,
                    classification.deadline,
                    json.dumps(classification.__dict__, ensure_ascii=False),
                    json.dumps(summary.as_dict(), ensure_ascii=False),
                )
            )
        with self.connect() as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT OR IGNORE INTO messages (
                    message_id, uid, run_id, sender, recipients, subject, received_at,
                    processed_at, category, priority, action, deadline,
                    classification_json, summary_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            return connection.total_changes - before

    def cleanup(self, retention_days: int) -> None:
        if retention_days <= 0:
            return
        cutoff = _to_iso(datetime.now(UTC) - timedelta(days=retention_days))
        with self.connect() as connection:
            connection.execute("DELETE FROM messages WHERE processed_at < ?", (cutoff,))

    def recent_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        self.init_schema()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, started_at, finished_at, since_at, status, mail_count, error
                FROM runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


def _to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)
