from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.ultravox_admin_service import UltravoxAdminService


class FakeConfigService:
    def get_active_provider_config(self, tenant_id: str, provider: str):
        return SimpleNamespace(tenant_id=tenant_id, provider=provider)

    def decrypt_api_key(self, config):
        return f"key:{config.tenant_id}"


class FakeClient:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    @staticmethod
    def _cursor(value):
        return None

    def list_agents(self, api_key: str, **_filters):
        self.calls.append(("agents", api_key))
        return {"results": [{"agentId": api_key, "name": "Private agent"}], "total": 1}

    def get_voice(self, api_key: str, voice_id: str):
        self.calls.append(("voice", api_key))
        return {
            "voiceId": voice_id,
            "name": "Private voice",
            "previewUrl": "https://must-not-leak.example",
            "definition": {"elevenLabs": {"apiKey": "must-not-leak"}},
        }

    def get_voice_preview(self, api_key: str, voice_id: str):
        self.calls.append(("preview", api_key))
        return b"RIFF-test"


class UltravoxAdminServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.service = UltravoxAdminService(Mock(), client=self.client)
        self.service.config_service = FakeConfigService()

    def test_catalog_requests_are_tenant_scoped(self):
        tenant_a = self.service.list_agents("tenant-a")
        tenant_b = self.service.list_agents("tenant-b")

        self.assertEqual(tenant_a.results[0].agent_id, "key:tenant-a")
        self.assertEqual(tenant_b.results[0].agent_id, "key:tenant-b")
        self.assertEqual(self.client.calls, [("agents", "key:tenant-a"), ("agents", "key:tenant-b")])

    def test_voice_projection_never_exposes_definition_or_preview_url(self):
        result = self.service.get_voice("tenant-a", "voice-1").model_dump()

        self.assertNotIn("definition", result)
        self.assertNotIn("previewUrl", result)
        self.assertEqual(result["voice_id"], "voice-1")
        self.assertTrue(result["capabilities"]["external_voice"])

    def test_preview_validates_detail_then_uses_preview_endpoint(self):
        self.assertEqual(self.service.preview("tenant-a", "voice-1"), b"RIFF-test")
        self.assertEqual(self.client.calls, [("voice", "key:tenant-a"), ("preview", "key:tenant-a")])

    def test_tool_boundary_is_structural_and_fails_closed_for_client_tools(self):
        tools = self.service._tools({
            "callTemplate": {
                "selectedTools": [
                    {"toolName": "hangUp"},
                    {"toolName": "create_booking"},
                    {"toolName": "create_booking", "client": {}},
                    {"toolName": "custom", "definition": {"client": {}}},
                ]
            }
        })
        self.assertEqual(
            [tool.classification for tool in tools],
            ["provider_native", "serviglobal_supported", "unsupported_client_tool", "unsupported_client_tool"],
        )


if __name__ == "__main__":
    unittest.main()
