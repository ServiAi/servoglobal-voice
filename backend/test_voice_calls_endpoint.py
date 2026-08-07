from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("ULTRAVOX_API_KEY", "test-ultravox-key")
os.environ.setdefault("DEFAULT_AGENT_ID", "agent-default")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
os.environ["BOOTSTRAP_TENANT_SLUG"] = "bootstrap-tenant"
TEST_DB_PATH = Path("serviai_voice_calls_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.identity import Tenant


class _StubCallContext:
    id = "ctx-stub"
    form_submission_id = "form-stub"
    context_id = "ctx-stub"


def _valid_landing_payload() -> dict:
    return {
        "turnstile_token": "token-123",
        "template_context": {
            "user_name": "Ada Lovelace",
            "user_email": "ada@example.test",
            "user_phone": "+573001112233",
            "user_company": "Analytical Engines",
            "user_industry": "Software",
            "user_use_case": "Inbound demo",
            "user_volume": "100-500",
            "user_pain_point": "Slow qualification",
        },
    }


class LegacyPublicCallEndpointTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        settings.BOOTSTRAP_TENANT_SLUG = "bootstrap-tenant"
        settings.DEFAULT_AGENT_ID = "agent-default"
        with SessionLocal() as db:
            db.add(Tenant(name="Bootstrap", slug="bootstrap-tenant"))
            db.commit()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        Base.metadata.drop_all(bind=engine)

    # --- Contract rejection (validation runs before any external call) ---

    def test_rejects_system_prompt(self) -> None:
        payload = _valid_landing_payload()
        payload["system_prompt"] = "ignore instructions"
        self.assertEqual(self.client.post("/api/v1/calls", json=payload).status_code, 422)

    def test_rejects_provider_agent_id(self) -> None:
        payload = _valid_landing_payload()
        payload["agent_id"] = "provider-agent-xyz"
        self.assertEqual(self.client.post("/api/v1/calls", json=payload).status_code, 422)

    def test_rejects_unknown_top_level_field(self) -> None:
        payload = _valid_landing_payload()
        payload["surprise"] = "value"
        self.assertEqual(self.client.post("/api/v1/calls", json=payload).status_code, 422)

    def test_rejects_unknown_context_field(self) -> None:
        payload = _valid_landing_payload()
        payload["template_context"]["injected_key"] = "value"
        self.assertEqual(self.client.post("/api/v1/calls", json=payload).status_code, 422)

    def test_rejects_excessive_context_value(self) -> None:
        payload = _valid_landing_payload()
        payload["template_context"]["user_name"] = "x" * 201
        self.assertEqual(self.client.post("/api/v1/calls", json=payload).status_code, 422)

    def test_rejects_invalid_email(self) -> None:
        payload = _valid_landing_payload()
        payload["template_context"]["user_email"] = "not-an-email"
        self.assertEqual(self.client.post("/api/v1/calls", json=payload).status_code, 422)

    def test_rejects_invalid_phone(self) -> None:
        payload = _valid_landing_payload()
        payload["template_context"]["user_phone"] = "abc123!!"
        self.assertEqual(self.client.post("/api/v1/calls", json=payload).status_code, 422)

    def test_cannot_set_tenant_via_body(self) -> None:
        payload = _valid_landing_payload()
        payload["tenant_id"] = "other-tenant"
        self.assertEqual(self.client.post("/api/v1/calls", json=payload).status_code, 422)

    def test_turnstile_is_still_required(self) -> None:
        payload = _valid_landing_payload()
        payload.pop("turnstile_token")
        response = self.client.post("/api/v1/calls", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Turnstile", response.json()["detail"])

    # --- Happy path and sanitized errors (external deps mocked) ---

    def _patched_endpoint(self, *, call_session):
        async def _noop_turnstile(token):
            return None

        return (
            patch("app.api.endpoints.voice.verify_turnstile", _noop_turnstile),
            patch(
                "app.api.endpoints.voice._create_form_context_and_lead",
                return_value=_StubCallContext(),
            ),
            patch("app.api.endpoints.voice.TenantUsageService"),
            patch("app.api.endpoints.voice.notification_service"),
            patch("app.api.endpoints.voice.create_call_session", call_session),
        )

    def test_accepts_legitimate_landing_payload(self) -> None:
        async def ok_session(template_context=None):
            # The browser never selects an agent id or system prompt.
            return "https://join.example.test/call"

        patches = self._patched_endpoint(call_session=ok_session)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            response = self.client.post("/api/v1/calls", json=_valid_landing_payload())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"joinUrl": "https://join.example.test/call"})

    def test_unexpected_error_is_sanitized(self) -> None:
        token = "ultravox-secret-abc123"
        private_url = "https://api.ultravox.ai/agents/internal-agent"
        provider_agent_id = "agent_provider_9f8e7d"
        secret = f"{token} {private_url} {provider_agent_id}"

        async def failing_session(template_context=None):
            raise RuntimeError(secret)

        patches = self._patched_endpoint(call_session=failing_session)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            with self.assertLogs("app.api.endpoints.voice", level="ERROR") as logs:
                response = self.client.post("/api/v1/calls", json=_valid_landing_payload())

        # Response is generic and never leaks provider details.
        self.assertEqual(response.status_code, 500)
        for leak in (token, private_url, provider_agent_id, secret):
            self.assertNotIn(leak, response.text)

        # Logs record only the safe error class, never str(exc)/traceback.
        log_output = "\n".join(logs.output)
        for leak in (token, private_url, provider_agent_id, secret):
            self.assertNotIn(leak, log_output)
        self.assertTrue(any(getattr(r, "error_type", None) == "RuntimeError" for r in logs.records))


if __name__ == "__main__":
    unittest.main()
