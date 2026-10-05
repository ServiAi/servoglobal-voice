"""Pure-domain tests of Integrations / Messaging: no I/O, no framework."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from app.modules.integrations.domain.catalog import CatalogFacts, SUPPORTED_PROVIDERS, catalog_status
from app.modules.integrations.domain.chatwoot import sanitize_chatwoot_error
from app.modules.integrations.domain.email import mask_email, sanitize_resend_error
from app.modules.integrations.domain.errors import (
    ProviderConfigurationError,
    ProviderError,
    ProviderOutcomeUnknown,
    ProviderRejected,
    ProviderUnavailable,
)
from app.modules.integrations.domain.events import MAX_MESSAGE_LENGTH, SENSITIVE_KEYS, sanitize_event_metadata
from app.modules.integrations.domain.whatsapp import (
    can_advance_status,
    extract_provider_message_id,
    mask_phone,
    normalize_phone,
    safe_preview,
    sanitize_whatsapp_error,
)

DOMAIN = Path(__file__).resolve().parent / "app" / "modules" / "integrations" / "domain"
FORBIDDEN = (
    "sqlalchemy",
    "fastapi",
    "starlette",
    "httpx",
    "requests",
    "app.models",
    "app.services",
    "app.db",
    "app.core",
    "app.api",
    "app.modules.integrations.application",
    "app.modules.integrations.infrastructure",
    "app.modules.integrations.api",
    "app.modules.integrations.wiring",
    "app.modules.crm",
    "app.modules.notifications",
    "app.modules.scheduling",
    "app.modules.voice",
)


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


class IntegrationsDomainPurityTests(unittest.TestCase):
    def test_domain_imports_no_framework_persistence_provider_or_foreign_module(self) -> None:
        offenders = [
            f"{path.name}: {name}"
            for path in DOMAIN.rglob("*.py")
            for name in _imports(path)
            if name.startswith(FORBIDDEN)
        ]
        self.assertEqual(offenders, [])

    def test_email_renderer_is_pure(self) -> None:
        source = (DOMAIN / "email_render.py").read_text(encoding="utf-8")
        self.assertNotIn("import httpx", source)
        self.assertNotIn("sqlalchemy", source)


class IntegrationEventSanitizationTests(unittest.TestCase):
    """What may be persisted in tenant_integration_events: never secrets, payloads or contact data."""

    def test_sensitive_keys_are_redacted_whatever_their_value(self) -> None:
        metadata = {
            "api_key": "re_secret",
            "Authorization": "Bearer abc",
            "payload": {"a": 1},
            "html": "<p>x</p>",
            "text": "body",
            "base64": "AAAA",
            "phone": "+573001112233",
            "email": "ana@example.com",
            "contact_email": "ana@example.com",
            "to_phone_number": "573001112233",
        }
        sanitized = sanitize_event_metadata(metadata)
        self.assertEqual(set(sanitized.values()), {"[redacted]"})
        self.assertEqual(set(sanitized), set(metadata))

    def test_scalars_are_kept_and_structures_are_omitted(self) -> None:
        sanitized = sanitize_event_metadata(
            {"count": 3, "ok": True, "ratio": 0.5, "name": "x", "none": None, "items": [1], "nested": {"a": 1}}
        )
        self.assertEqual(
            sanitized,
            {"count": 3, "ok": True, "ratio": 0.5, "name": "x", "none": None, "items": "[omitted]", "nested": "[omitted]"},
        )

    def test_sensitive_key_set_is_the_documented_one(self) -> None:
        self.assertEqual(SENSITIVE_KEYS, {"api_key", "authorization", "payload", "html", "text", "base64", "phone", "email"})

    def test_message_cap_is_500(self) -> None:
        self.assertEqual(MAX_MESSAGE_LENGTH, 500)


class SanitizerTests(unittest.TestCase):
    def test_whatsapp_error_redacts_tokens_phones_and_emails(self) -> None:
        raw = "Bearer EAAGabcdefghijklmnopqrstuv failed for +57 300 111 2233 / ana@example.com"
        cleaned = sanitize_whatsapp_error(raw)
        self.assertNotIn("EAAG", cleaned)
        self.assertNotIn("300 111", cleaned)
        self.assertNotIn("ana@example.com", cleaned)
        self.assertIsNone(sanitize_whatsapp_error(None))
        self.assertLessEqual(len(sanitize_whatsapp_error("x" * 900)), 500)

    def test_resend_error_redacts_keys_headers_and_contacts(self) -> None:
        cleaned = sanitize_resend_error("key re_abc123 Authorization: Bearer s3cr3tvalue to ana@example.com +573001112233")
        for leaked in ("re_abc123", "s3cr3tvalue", "ana@example.com", "573001112233"):
            self.assertNotIn(leaked, cleaned)
        self.assertEqual(sanitize_resend_error(None), "Resend request failed.")

    def test_chatwoot_error_hides_html_pages_and_tokens(self) -> None:
        self.assertIn("pagina HTML", sanitize_chatwoot_error("<!DOCTYPE html><html>boom</html>"))
        self.assertNotIn("sekret", sanitize_chatwoot_error('api_access_token="sekret" rejected'))

    def test_mask_email(self) -> None:
        self.assertEqual(mask_email("ana@example.com"), "an***@example.com")
        self.assertEqual(mask_email("not-an-email"), "")


class WhatsAppRulesTests(unittest.TestCase):
    def test_status_never_moves_backwards(self) -> None:
        self.assertTrue(can_advance_status("sent", "delivered"))
        self.assertTrue(can_advance_status("delivered", "read"))
        self.assertTrue(can_advance_status("delivered", "delivered"))
        self.assertFalse(can_advance_status("read", "delivered"))
        self.assertFalse(can_advance_status("delivered", "sent"))

    def test_failed_and_unknown_statuses_are_always_accepted(self) -> None:
        self.assertTrue(can_advance_status("read", "failed"))
        self.assertTrue(can_advance_status("sent", "failed"))
        self.assertTrue(can_advance_status("received", "delivered"))
        self.assertTrue(can_advance_status(None, "read"))

    def test_phone_helpers(self) -> None:
        self.assertEqual(normalize_phone("+57 (300) 111-2233"), "573001112233")
        self.assertIsNone(normalize_phone("abc"))
        self.assertEqual(mask_phone("573001112233"), "***2233")
        self.assertEqual(mask_phone("12"), "***")
        self.assertEqual(safe_preview("a\nb\r" + "c" * 300), "a b " + "c" * 236)

    def test_provider_message_id_extraction(self) -> None:
        self.assertEqual(extract_provider_message_id({"messages": [{"id": "wamid.1"}]}), "wamid.1")
        self.assertIsNone(extract_provider_message_id({"messages": []}))
        self.assertIsNone(extract_provider_message_id({"messages": [{"id": 5}]}))
        self.assertIsNone(extract_provider_message_id({}))


class CatalogAndErrorTests(unittest.TestCase):
    def test_catalog_status_rules(self) -> None:
        self.assertEqual(catalog_status(configured=False, provider_status=None, has_error=False), "not_configured")
        self.assertEqual(catalog_status(configured=True, provider_status="active", has_error=False), "active")
        self.assertEqual(catalog_status(configured=True, provider_status="connected", has_error=False), "active")
        self.assertEqual(catalog_status(configured=True, provider_status="inactive", has_error=False), "configured")
        self.assertEqual(catalog_status(configured=True, provider_status="active", has_error=True), "error")
        self.assertEqual(catalog_status(configured=True, provider_status="failed", has_error=False), "error")
        self.assertEqual(CatalogFacts(True, "active", False).configured, True)

    def test_supported_providers_are_the_documented_catalog(self) -> None:
        self.assertEqual(SUPPORTED_PROVIDERS, ("resend", "voice", "whatsapp", "calcom", "google_calendar", "chatwoot"))

    def test_neutral_errors_share_one_base(self) -> None:
        for error in (ProviderUnavailable, ProviderRejected, ProviderConfigurationError, ProviderOutcomeUnknown):
            self.assertTrue(issubclass(error, ProviderError))

    def test_adapter_errors_map_to_neutral_errors(self) -> None:
        from app.modules.integrations.infrastructure.chatwoot.client import ChatwootClientError
        from app.modules.integrations.infrastructure.chatwoot.platform_client import ChatwootPlatformError
        from app.modules.integrations.infrastructure.email.resend import ResendServiceError
        from app.modules.integrations.infrastructure.whatsapp.meta_client import WhatsAppCloudClientError

        for error in (WhatsAppCloudClientError, ResendServiceError, ChatwootClientError, ChatwootPlatformError):
            self.assertTrue(issubclass(error, ProviderRejected), error)


if __name__ == "__main__":
    unittest.main()
