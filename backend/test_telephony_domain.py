"""Pure Telephony domain rules: no database, no framework, no network."""

import unittest

from app.modules.telephony.domain.capacity import ACTIVE_CALLBACK_STATUSES, is_at_capacity
from app.modules.telephony.domain.errors import SipDialError
from app.modules.telephony.domain.routes import (
    normalize_allowed_countries,
    normalize_route_host,
    sip_username_for_route,
    validate_sip_password,
)
from app.modules.telephony.infrastructure.livekit_sip import map_sip_status


class CapacityPolicyTests(unittest.TestCase):
    def test_capacity_boundaries(self) -> None:
        self.assertFalse(is_at_capacity(0, 1))
        self.assertTrue(is_at_capacity(1, 1))
        self.assertFalse(is_at_capacity(2, 3))
        self.assertTrue(is_at_capacity(3, 3))
        self.assertTrue(is_at_capacity(4, 3))

    def test_active_callback_statuses_are_pinned(self) -> None:
        self.assertEqual(ACTIVE_CALLBACK_STATUSES, ("starting", "queued", "ringing", "in_progress"))


class SipStatusMappingTests(unittest.TestCase):
    def test_mapping_table(self) -> None:
        expected = {486: "busy", 603: "rejected", 607: "rejected", 608: "rejected",
                    408: "no_answer", 480: "no_answer", 487: "no_answer",
                    500: "failed", 404: "failed", None: "failed"}
        for code, status in expected.items():
            self.assertEqual(map_sip_status(code), status, code)

    def test_dial_error_defaults_to_failed(self) -> None:
        error = SipDialError("runtime_not_ready")
        self.assertEqual((error.code, error.call_status), ("runtime_not_ready", "failed"))


class RouteInvariantTests(unittest.TestCase):
    def test_username_requires_uuid(self) -> None:
        route_id = "0a1b2c3d-0000-4000-8000-0123456789ab"
        self.assertEqual(sip_username_for_route(route_id), "route-0a1b2c3d000040008000" "0123456789ab")
        with self.assertRaises(ValueError):
            sip_username_for_route("not-a-uuid")

    def test_host_is_normalised_and_validated(self) -> None:
        self.assertEqual(normalize_route_host("  PBX.Example.COM "), "pbx.example.com")
        for bad in ("sip:pbx.example.com", "pbx.example.com:5060", "pbx example", ""):
            with self.assertRaises(ValueError):
                normalize_route_host(bad)

    def test_password_rejects_config_injection(self) -> None:
        validate_sip_password(None)
        validate_sip_password("plain-Secret_123")
        for bad in ("a\nb", "a;b", "a#b", "a[b]", "contraseña"):
            with self.assertRaises(ValueError):
                validate_sip_password(bad)

    def test_countries(self) -> None:
        self.assertEqual(normalize_allowed_countries(["CO", "CO"], "CO"), ["CO"])
        with self.assertRaises(ValueError):
            normalize_allowed_countries([], "CO")
        with self.assertRaises(ValueError):
            normalize_allowed_countries(["CO"], "MX")
        with self.assertRaises(ValueError):
            normalize_allowed_countries(["ZZ"], "ZZ")


if __name__ == "__main__":
    unittest.main()
