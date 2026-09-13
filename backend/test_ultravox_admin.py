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
        self.tts_keys_response: dict = {}

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

    def preview_external_voice(self, api_key: str, *, payload):
        self.calls.append(("external_voice_preview", api_key))
        self.last_external_voice_payload = payload
        return b"RIFF-external-preview"

    def get_tts_api_keys(self, api_key: str):
        self.calls.append(("tts_api_keys", api_key))
        return self.tts_keys_response


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

    # -- Phase D: external voice preview + BYOK preflight --

    def test_preview_external_voice_builds_elevenlabs_definition_and_calls_client(self):
        from app.schemas.agents import AgentVoiceConfig

        voice = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="ABC123",
            settings={"model": "eleven_turbo_v2_5", "speed": 1.0},
        )
        result = self.service.preview_external_voice("tenant-a", voice)
        self.assertEqual(result, b"RIFF-external-preview")
        self.assertEqual(self.client.calls, [("external_voice_preview", "key:tenant-a")])
        self.assertEqual(self.client.last_external_voice_payload, {
            "name": "ServiGlobal External Voice Preview",
            "definition": {"elevenLabs": {"voiceId": "ABC123", "model": "eleven_turbo_v2_5", "speed": 1.0}},
        })

    def test_preview_external_voice_rejects_provider_mode(self):
        from app.schemas.agents import AgentVoiceConfig

        voice = AgentVoiceConfig(mode="provider", provider="ultravox", voice_id="Mark")
        with self.assertRaises(ValueError):
            self.service.preview_external_voice("tenant-a", voice)
        self.assertEqual(self.client.calls, [])

    def test_preview_external_voice_rejects_non_elevenlabs_provider(self):
        from app.schemas.agents import AgentVoiceConfig

        voice = AgentVoiceConfig(mode="provider_external", provider="cartesia", voice_id="x")
        with self.assertRaises(ValueError):
            self.service.preview_external_voice("tenant-a", voice)
        self.assertEqual(self.client.calls, [])

    def test_preview_external_voice_rejects_invalid_settings_before_calling_ultravox(self):
        from app.schemas.agents import AgentVoiceConfig

        voice = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="x", settings={"pitch": 1}
        )
        with self.assertRaises(ValueError) as ctx:
            self.service.preview_external_voice("tenant-a", voice)
        self.assertEqual(str(ctx.exception), "voice_settings_invalid")
        self.assertEqual(self.client.calls, [])

    def test_validate_external_voice_credentials_passes_when_elevenlabs_key_present(self):
        self.client.tts_keys_response = {"elevenLabs": {"prefix": "abc"}}
        self.service.validate_external_voice_credentials("tenant-a", "elevenlabs")  # no exception
        self.assertEqual(self.client.calls, [("tts_api_keys", "key:tenant-a")])

    def test_validate_external_voice_credentials_fails_when_elevenlabs_key_absent(self):
        self.client.tts_keys_response = {}
        with self.assertRaises(ValueError) as ctx:
            self.service.validate_external_voice_credentials("tenant-a", "elevenlabs")
        self.assertEqual(str(ctx.exception), "external_tts_credentials_unavailable")

    def test_validate_external_voice_credentials_fails_when_only_a_different_provider_is_configured(self):
        self.client.tts_keys_response = {"cartesia": {"prefix": "abc"}}
        with self.assertRaises(ValueError) as ctx:
            self.service.validate_external_voice_credentials("tenant-a", "elevenlabs")
        self.assertEqual(str(ctx.exception), "external_tts_credentials_unavailable")

    def test_validate_external_voice_credentials_rejects_unsupported_provider(self):
        with self.assertRaises(ValueError):
            self.service.validate_external_voice_credentials("tenant-a", "cartesia")
        self.assertEqual(self.client.calls, [])

    def test_elevenlabs_mapper_matches_the_runtime_phase_c_field_mapping(self):
        # Documents field-for-field parity with build_elevenlabs_external_voice
        # in voice-runtime/src/serviglobal_voice_runtime/providers.py. Backend
        # and voice-runtime are separate deploys/packages with no shared code,
        # so this hardcodes the same mapping table rather than importing
        # across that boundary.
        from app.schemas.agents import AgentVoiceConfig
        from app.services.ultravox_admin_service import build_elevenlabs_external_voice

        voice = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="ABC123",
            settings={
                "model": "eleven_turbo_v2_5", "speed": 1.0, "stability": 0.8,
                "similarity_boost": 0.75, "use_speaker_boost": True,
            },
        )
        self.assertEqual(build_elevenlabs_external_voice(voice), {
            "elevenLabs": {
                "voiceId": "ABC123",
                "model": "eleven_turbo_v2_5",
                "speed": 1.0,
                "stability": 0.8,
                "similarityBoost": 0.75,
                "useSpeakerBoost": True,
            }
        })

    def test_elevenlabs_mapper_only_forwards_the_known_settings_keys(self):
        # Defense in depth: even if an unvalidated voice reached the mapper,
        # it can never leak an unknown settings key through to Ultravox.
        from app.schemas.agents import AgentVoiceConfig
        from app.services.ultravox_admin_service import build_elevenlabs_external_voice

        voice = AgentVoiceConfig(mode="provider_external", provider="elevenlabs", voice_id="ABC123")
        self.assertEqual(build_elevenlabs_external_voice(voice), {"elevenLabs": {"voiceId": "ABC123"}})

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
