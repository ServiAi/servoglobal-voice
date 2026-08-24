from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.workers.asterisk_provisioner import (
    AsteriskProvisioner,
    ProvisionerSettings,
    render_pjsip_include,
)


ROUTE = {
    "route_id": "12345678-1234-1234-1234-1234567890ab",
    "route_key": "route-123456781234123412341234567890ab",
    "desired_revision": 2,
    "applied_revision": 1,
    "enabled": True,
    "sip_username": "tenant-a",
    "sip_password": "SipPassword2026*+",
    "caller_id": "+573001112233",
}


class AsteriskProvisionerAgentTests(unittest.TestCase):
    def test_render_uses_template_and_does_not_render_disabled_routes(self) -> None:
        rendered = render_pjsip_include([ROUTE, {**ROUTE, "enabled": False}])
        self.assertIn("[route-123456781234123412341234567890ab](ultravox-tenant)", rendered)
        self.assertIn("set_var=TENANT_CALLER_ID=+573001112233", rendered)
        self.assertEqual(rendered.count("type=auth"), 1)

    def test_render_rejects_configuration_injection(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_sip_password"):
            render_pjsip_include([{**ROUTE, "sip_password": "unsafe;password"}])

    def test_reconcile_writes_reports_and_remembers_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provisioner = AsteriskProvisioner(
                ProvisionerSettings(
                    api_url="https://api.example.test",
                    shared_secret="secret",
                    include_path=root / "serviglobal-tenants.conf",
                    state_path=root / "state.json",
                )
            )
            desired = {"snapshot_revision": "abc", "routes": [ROUTE]}
            with patch.object(provisioner, "_request", side_effect=[desired, {"accepted": 1}]) as request, patch.object(
                provisioner, "_reload_and_verify"
            ):
                self.assertTrue(provisioner.reconcile_once())
            self.assertIn("password=SipPassword2026*+", provisioner.settings.include_path.read_text())
            self.assertEqual(request.call_args_list[1].args[0], "apply-results")
            self.assertEqual(provisioner._last_snapshot(), "abc")

    def test_reconcile_restores_backup_when_asterisk_binary_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            include_path = root / "serviglobal-tenants.conf"
            include_path.write_text("; previous include\n", encoding="utf-8")
            provisioner = AsteriskProvisioner(
                ProvisionerSettings(
                    api_url="https://api.example.test",
                    shared_secret="secret",
                    include_path=include_path,
                    state_path=root / "state.json",
                )
            )
            desired = {"snapshot_revision": "abc", "routes": [ROUTE]}
            with patch.object(
                provisioner, "_request", side_effect=[desired, {"accepted": 0}]
            ) as request, patch.object(
                provisioner, "_reload_and_verify", side_effect=FileNotFoundError()
            ):
                self.assertFalse(provisioner.reconcile_once())
            self.assertEqual(include_path.read_text(), "; previous include\n")
            reported = request.call_args_list[1].args[1]["results"]
            self.assertEqual(reported[0]["error_code"], "asterisk_command_unavailable")
            self.assertIsNone(provisioner._last_snapshot())


if __name__ == "__main__":
    unittest.main()
