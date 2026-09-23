from __future__ import annotations

import socket
from unittest.mock import patch

import httpx

from _integrations_2a_test_base import Integration2ATestCase
from app.core.config import settings
from app.db.session import SessionLocal
from app.security.voice_runtime_auth import create_runtime_token
from app.services.tenant_feature_service import AGENT_BUILDER, CUSTOM_HTTP_TOOLS, TenantFeatureService
from app.services.tool_http_safety import SafeHttpClient
from app.services.voice_session_service import VoiceSessionService


def _addrinfo(ip: str) -> list[tuple]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


class CustomToolsEndToEndTests(Integration2ATestCase):
    """Full lifecycle through the real HTTP stack: create -> credential ->
    activate -> bind to an agent -> publish -> compile -> invoke through the
    same internal endpoint contract LiveKit uses -- no shortcuts through
    services directly, to prove the whole chain wired in Increments A-G
    actually holds together end to end."""

    def _enable_features(self) -> None:
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(self.tenant.id, AGENT_BUILDER, True, {}, self.user.id)
            TenantFeatureService(db).set_feature(self.tenant.id, CUSTOM_HTTP_TOOLS, True, {}, self.user.id)

    def _runtime_headers(self) -> dict:
        # The secret must still be patched when the request is actually
        # sent/verified, not just when the token is minted -- callers must
        # keep this inside the same `with patch.object(settings, ...)`
        # block as the request itself.
        token = create_runtime_token()
        return {"Authorization": f"Bearer {token}"}

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_full_lifecycle_create_to_invoke(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo("93.184.216.34")
        self._enable_features()

        # 1. Create the custom tool.
        create_response = self.client.post(
            "/api/v1/tools/custom",
            json={
                "key": "custom.customer_balance",
                "name": "Consultar saldo",
                "description": "Consulta el saldo pendiente del cliente.",
                "method": "GET",
                "base_url": "https://example-api.test",
                "path_template": "/customers/{document}/balance",
                "path_mapping": {"document": "args.document"},
                "input_schema": {
                    "type": "object",
                    "properties": {"document": {"type": "string"}},
                    "required": ["document"],
                },
                "response_mapping": {"balance": "response.billing.balance"},
                "auth_type": "bearer",
                "secrets": {"token": "s3cr3t-token"},
            },
        )
        self.assertEqual(create_response.status_code, 201, create_response.text)
        tool = create_response.json()
        self.assertNotIn("s3cr3t-token", create_response.text)

        # 2. Activate it.
        activate_response = self.client.post(f"/api/v1/tools/custom/{tool['id']}/activate")
        self.assertEqual(activate_response.status_code, 200, activate_response.text)
        self.assertEqual(activate_response.json()["status"], "active")

        # 3. Confirm it appears in the unified catalog as available+custom.
        catalog_response = self.client.get("/api/v1/agents/tools/catalog")
        catalog_by_key = {item["key"]: item for item in catalog_response.json()}
        self.assertIn("custom.customer_balance", catalog_by_key)
        self.assertTrue(catalog_by_key["custom.customer_balance"]["available"])
        self.assertEqual(catalog_by_key["custom.customer_balance"]["source"], "custom")

        # 4. Bind it to a serviglobal_managed agent and publish.
        create_agent = self.client.post(
            "/api/v1/agents",
            json={
                "name": "Sandra",
                "description": "Asesora",
                "language": "es",
                "timezone": "America/Bogota",
                "instructions": {
                    "role": "Asesora",
                    "objective": "Ayudar",
                    "system_prompt": "Eres Sandra.",
                    "greeting": "Hola",
                    "closing": "Gracias",
                },
                "behavior": {
                    "response_style": "balanced",
                    "interruptions": "balanced",
                    "turn_detection": "automatic",
                    "confirmation_strategy": "important_data",
                    "agent_first": True,
                },
                "tools": [{"key": "custom.customer_balance", "enabled": True, "config": {}}],
            },
        )
        self.assertEqual(create_agent.status_code, 201, create_agent.text)
        agent_id = create_agent.json()["id"]

        with patch("app.services.ultravox_admin_service.UltravoxAdminService.get_voice"):
            publish_response = self.client.post(f"/api/v1/agents/{agent_id}/publish", json={})
        self.assertEqual(publish_response.status_code, 200, publish_response.text)

        # 5. Start a VoiceSession against the published agent.
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(
                self.tenant.id, agent_id, channel="webrtc", direction="internal"
            )
            db.commit()
            session_id = session.id

        with patch.object(settings, "VOICE_RUNTIME_SERVICE_SECRET", "x" * 32):
            headers = self._runtime_headers()

            # 6. Compiled spec must include the tool with no endpoint/credential.
            spec_response = self.client.get(
                f"/api/v1/internal/voice-runtime/sessions/{session_id}/spec", headers=headers
            )
            self.assertEqual(spec_response.status_code, 200, spec_response.text)
            spec_json = spec_response.json()
            compiled_tools = {t["key"]: t for t in spec_json["tools"]}
            self.assertIn("custom.customer_balance", compiled_tools)
            self.assertNotIn("example-api.test", spec_response.text)
            self.assertNotIn("s3cr3t-token", spec_response.text)

            # 7. Invoke through the exact same internal endpoint LiveKit calls.
            def handler(request: httpx.Request) -> httpx.Response:
                self.assertEqual(request.headers["authorization"], "Bearer s3cr3t-token")
                self.assertTrue(request.url.path.endswith("/customers/79123456/balance"))
                return httpx.Response(
                    200, json={"billing": {"balance": 4500}}, headers={"content-type": "application/json"}
                )

            transport = httpx.MockTransport(handler)
            with patch("app.services.custom_http_tool_executor.SafeHttpClient") as mock_cls:
                mock_cls.return_value = SafeHttpClient(transport=transport)
                invoke_response = self.client.post(
                    f"/api/v1/internal/voice-runtime/sessions/{session_id}/tools/custom.customer_balance/invoke",
                    json={"arguments": {"document": "79123456"}},
                    headers=headers,
                )
            self.assertEqual(invoke_response.status_code, 200, invoke_response.text)
            self.assertEqual(invoke_response.json(), {"result": {"balance": 4500}})

            # 8. SSRF: repointing the same tool at a private IP must be
            # blocked before any connection is attempted -- no mock needed,
            # the real validate_and_resolve rejects it.
            mock_getaddrinfo.return_value = _addrinfo("10.0.0.5")
            blocked_response = self.client.post(
                f"/api/v1/internal/voice-runtime/sessions/{session_id}/tools/custom.customer_balance/invoke",
                json={"arguments": {"document": "1"}},
                headers=headers,
            )
            self.assertEqual(blocked_response.status_code, 502, blocked_response.text)


if __name__ == "__main__":
    import unittest

    unittest.main()
