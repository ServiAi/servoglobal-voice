"""The staging provider smoke harness must stay opt-in and never leak recipients or secrets."""

from __future__ import annotations

import importlib.util
import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parent / "scripts" / "smoke_integrations_providers.py"


def _load():
    spec = importlib.util.spec_from_file_location("smoke_integrations_providers", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SmokeHarnessTests(unittest.TestCase):
    def test_refuses_without_the_staging_flag(self) -> None:
        smoke = _load()
        argv = ["whatsapp", "--tenant-id", "t", "--template-key", "k", "--to-phone", "+573001112233", "--execute"]
        with patch.dict(os.environ, {}, clear=False) as env:
            env.pop(smoke.FLAG, None)
            err = io.StringIO()
            with redirect_stderr(err):
                code = smoke.main(argv)
        self.assertEqual(code, 2)
        self.assertIn(smoke.FLAG, err.getvalue())

    def test_refuses_without_a_database(self) -> None:
        smoke = _load()
        argv = ["resend", "--tenant-id", "t", "--to-email", "qa@example.com"]
        with patch.dict(os.environ, {smoke.FLAG: "1"}, clear=False) as env:
            env.pop("DATABASE_URL", None)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(smoke.main(argv), 2)

    def test_every_action_requires_an_explicit_recipient(self) -> None:
        smoke = _load()
        for argv in (["whatsapp", "--tenant-id", "t", "--template-key", "k"], ["resend", "--tenant-id", "t"], ["chatwoot", "--tenant-id", "t"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                smoke.main(argv)

    def test_recipients_are_masked_in_output(self) -> None:
        smoke = _load()
        out = io.StringIO()
        with redirect_stdout(out):
            smoke._step(f"send to {smoke._mask_phone('+573001112233')} / {smoke._mask_email('qa.team@example.com')}", True)
        text = out.getvalue()
        self.assertNotIn("573001112233", text)
        self.assertNotIn("qa.team", text)
        self.assertIn("***2233", text)


if __name__ == "__main__":
    unittest.main()
