from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from inbox_lens.onboarding import (
    read_env_values,
    run_doctor,
    settings_from_values,
    update_env_from_form,
    write_env_values,
)


class OnboardingTests(unittest.TestCase):
    def test_update_env_from_form_preserves_blank_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            write_env_values({"IMAP_PASSWORD": "existing-secret", "SMTP_PASSWORD": "smtp-secret"}, env_path)
            update_env_from_form({"IMAP_HOST": "imap.mail.test", "IMAP_PASSWORD": ""}, env_path)
            values = read_env_values(env_path)

        self.assertEqual(values["IMAP_HOST"], "imap.mail.test")
        self.assertEqual(values["IMAP_PASSWORD"], "existing-secret")
        self.assertEqual(values["SMTP_PASSWORD"], "smtp-secret")

    def test_doctor_reports_placeholder_mail_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = settings_from_values({"DATABASE_PATH": str(Path(temp_dir) / "state.sqlite")})
            checks = run_doctor(settings, network=False)

        statuses = {check.name: check.status for check in checks}
        self.assertEqual(statuses["IMAP config"], "fail")
        self.assertEqual(statuses["SMTP config"], "fail")


if __name__ == "__main__":
    unittest.main()
