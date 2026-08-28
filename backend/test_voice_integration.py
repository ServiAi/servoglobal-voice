from __future__ import annotations

import unittest
from unittest.mock import patch

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.integrations import (
    TenantIntegrationEvent,
    TenantSipRoute,
    TenantVoiceProviderConfig,
)


class VoiceEndpointTests(Integration2ATestCase):
    def setUp(self):
        super().setUp()
        self.provider = "ultravox"

    def configure_voice(self):
        payload = self.voice_payload()
        response = self.client.post(
            "/api/v1/integrations/voice/config",
            json=payload,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            data["sip_route"]["sip_username"],
            f"route-{data['sip_route']['id'].replace('-', '')}",
        )
        self.assertEqual(data["sip_route"]["provision_status"], "pending")
        self.assertEqual(data["sip_route"]["desired_revision"], 1)
        self.assertEqual(data["sip_route"]["applied_revision"], 0)
        return data

    def voice_payload(self):
        return {
                "provider": self.provider,
                "display_name": "My Ultravox",
                "api_key": "uvx_api_secret_token_12345",
                "webhook_secret": "wh_secret_123",
                "default_from_number": "+573001112233",
                "default_language": "es",
                "default_timezone": "America/Bogota",
                "status": "active",
                "sip_route": {
                    "status": "active",
                    "pbx_host": "pbx.example.com",
                    "pbx_port": 5060,
                    "sip_username": "tenant-a",
                    "sip_password": "test-sip-password",
                    "caller_id": "+573001112233",
                    "default_country": "CO",
                    "allowed_countries": ["CO"],
                    "max_concurrent_calls": 1,
                },
            }

    def test_existing_sip_username_is_normalized_on_save(self):
        data = self.configure_voice()
        route_id = data["sip_route"]["id"]
        expected_username = f"route-{route_id.replace('-', '')}"

        with SessionLocal() as db:
            route = db.get(TenantSipRoute, route_id)
            route.sip_username = "legacy-user"
            route.provision_status = "active"
            route.applied_revision = route.desired_revision
            db.commit()

        payload = self.voice_payload()
        payload["sip_route"].pop("sip_password")
        payload["sip_route"]["sip_username"] = "user-controlled-value"
        response = self.client.post("/api/v1/integrations/voice/config", json=payload)

        self.assertEqual(response.status_code, 200)
        route = response.json()["sip_route"]
        self.assertEqual(route["sip_username"], expected_username)
        self.assertEqual(route["desired_revision"], 2)
        self.assertEqual(route["provision_status"], "pending")

    def test_voice_test_endpoint_canonical_works(self):
        self.configure_voice()

        with patch("app.api.endpoints.integrations.VoiceConfigService.test_connection") as mock_test:
            mock_test.return_value = ("active", None)
            response = self.client.post(
                "/api/v1/integrations/voice/test",
                params={"provider": "ultravox"},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["status"], "active")

    def test_voice_test_endpoint_legacy_alias_works(self):
        self.configure_voice()

        with patch("app.api.endpoints.crm_voice.VoiceConfigService.test_connection") as mock_test:
            mock_test.return_value = ("healthy", None)
            response = self.client.post(
                "/api/v1/integrations/voice/config/test",
                params={"provider": "ultravox"},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["status"], "healthy")

    def test_voice_test_uses_tenant_from_context_not_request(self):
        self.configure_voice()

        other_tenant, _ = self._seed_tenant_user(slug="tenant-b", email="b@example.com")

        with patch("app.api.endpoints.integrations.VoiceConfigService.test_connection") as mock_test:
            mock_test.return_value = ("active", None)
            response = self.client.post(
                "/api/v1/integrations/voice/test",
                params={"provider": "ultravox"},
            )
            self.assertEqual(response.status_code, 200)
            mock_test.assert_called_once()
            call_args = mock_test.call_args
            self.assertEqual(call_args[0][0], self.tenant.id)


class VoiceClientLogSanitizationTests(Integration2ATestCase):
    def test_voice_client_does_not_log_provider_response_body(self):
        from app.services.voice_client import VoiceClient, VoiceClientConfig, VoiceSipRouteConfig
        import httpx

        config = VoiceClientConfig(
            provider="ultravox",
            api_key="test_key",
            base_url="https://api.ultravox.ai",
            sip_route=VoiceSipRouteConfig(
                host="pbx.example.com",
                port=5060,
                username="tenant-a",
                password="test-sip-password",
                caller_id="+573001112233",
                default_country="CO",
                allowed_countries=("CO",),
            ),
        )

        with patch("httpx.Client.post") as mock_post:
            mock_response = httpx.Response(
                status_code=500,
                content=b'{"detail": "secret provider data here"}',
                request=httpx.Request("POST", "https://api.ultravox.ai/test"),
            )
            mock_post.side_effect = httpx.HTTPStatusError(
                "Server error",
                request=httpx.Request("POST", "https://api.ultravox.ai/test"),
                response=mock_response,
            )

            with self.assertRaises(httpx.HTTPStatusError):
                client = VoiceClient()
                client.start_outbound_call(
                    config,
                    to_phone="+573001112233",
                    agent_id="agent-123",
                    metadata={"voice_call_id": "vc-1"},
                    context={},
                )


if __name__ == "__main__":
    unittest.main()
