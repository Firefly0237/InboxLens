from __future__ import annotations

import argparse
import sys

from inbox_lens.console import serve_console
from inbox_lens.config import Settings
from inbox_lens.onboarding import print_doctor, run_doctor, run_wizard
from inbox_lens.pipeline import run_digest, send_test_email
from inbox_lens.sample import render_sample_digest
from inbox_lens.storage import Repository


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "wizard":
            run_wizard()
            return 0
        if args.command == "console":
            serve_console(host=args.host, port=args.port, open_browser=not args.no_browser)
            return 0

        settings = Settings.from_env()
        if args.command == "doctor":
            print_doctor(run_doctor(settings, network=args.network, auth=args.auth))
            return 0
        if args.command == "run":
            run_digest(
                settings,
                dry_run=args.dry_run,
                limit=args.limit,
                force_send_empty=args.send_empty,
            )
            return 0
        if args.command == "send-test":
            send_test_email(settings)
            print("SMTP test email sent.")
            return 0
        if args.command == "inspect":
            _inspect(settings, args.limit)
            return 0
        if args.command == "init-db":
            Repository(settings.database_path).init_schema()
            print(f"Initialized database: {settings.database_path}")
            return 0
        if args.command == "render-sample":
            render_sample_digest(settings)
            print("Rendered sample digest to out/sample_digest.html and out/sample_digest.txt")
            return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="InboxLens daily email digest assistant")
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="Fetch, classify, summarize and send the digest")
    run.add_argument("--dry-run", action="store_true", help="Do not send email; print text digest and write out/last_digest.*")
    run.add_argument("--limit", type=int, default=None, help="Limit fetched messages for testing")
    run.add_argument("--send-empty", action="store_true", help="Send or render an empty digest")

    subparsers.add_parser("send-test", help="Send a small SMTP test email")
    subparsers.add_parser("init-db", help="Create SQLite schema")
    subparsers.add_parser("render-sample", help="Render a local sample digest to out/sample_digest.*")
    subparsers.add_parser("wizard", help="Interactive setup wizard for .env")

    doctor = subparsers.add_parser("doctor", help="Check local configuration and dependencies")
    doctor.add_argument("--network", action="store_true", help="Also test TCP reachability for IMAP/SMTP hosts")
    doctor.add_argument("--auth", action="store_true", help="Also perform IMAP login and SMTP authentication tests (no email sent)")

    console = subparsers.add_parser("console", help="Start the local browser control panel")
    console.add_argument("--host", default="127.0.0.1")
    console.add_argument("--port", type=int, default=8765)
    console.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically")

    inspect = subparsers.add_parser("inspect", help="Show recent run history")
    inspect.add_argument("--limit", type=int, default=10)
    return parser


def _inspect(settings: Settings, limit: int) -> None:
    rows = Repository(settings.database_path).recent_runs(limit)
    if not rows:
        print("No runs recorded.")
        return
    for row in rows:
        print(
            f"#{row['id']} {row['status']} count={row['mail_count']} "
            f"started={row['started_at']} finished={row['finished_at']} error={row['error'] or ''}"
        )
