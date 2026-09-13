from __future__ import annotations

import unittest

from _integrations_2a_test_base import Integration2ATestCase


class VoiceRegistryTests(Integration2ATestCase):
    def test_resolves_logical_ultravox_model_to_execution_id(self) -> None:
        from app.domain.voice_registry import resolve_execution_model_id

        self.assertEqual(
            resolve_execution_model_id("ultravox", "ultravox"),
            "fixie-ai/ultravox",
        )
        self.assertEqual(
            resolve_execution_model_id("ultravox", "ultravox-v0.7"),
            "fixie-ai/ultravox",
        )

    def test_execution_model_resolution_fails_closed(self) -> None:
        from unittest.mock import patch

        from app.domain import voice_registry

        with self.assertRaises(voice_registry.VoiceRegistryValidationError):
            voice_registry.resolve_execution_model_id("unknown", "ultravox")
        with self.assertRaises(voice_registry.VoiceRegistryValidationError):
            voice_registry.resolve_execution_model_id("ultravox", "unknown")

        planned = voice_registry.VoiceModel(
            id="ultravox:planned",
            provider_key="ultravox",
            key="planned",
            name="Planned",
            execution_model_id="provider/planned",
            model_type="realtime",
            implementation_status="planned",
        )
        with patch.dict(voice_registry._MODELS_BY_ID, {planned.id: planned}):
            with self.assertRaises(voice_registry.VoiceRegistryValidationError):
                voice_registry.resolve_execution_model_id("ultravox", "planned")

    def test_list_providers_shows_ultravox_active_and_rest_planned(self) -> None:
        response = self.client.get("/api/v1/voice/providers")
        self.assertEqual(response.status_code, 200, response.text)
        providers = {item["key"]: item for item in response.json()}
        self.assertIn("ultravox", providers)
        self.assertEqual(providers["ultravox"]["status"], "active")
        self.assertTrue(providers["ultravox"]["supports_byok"])
        planned = [p for p in providers.values() if p["key"] != "ultravox"]
        self.assertTrue(planned)
        self.assertTrue(all(p["status"] == "planned" for p in planned))

    def test_list_models_filters_by_type_and_provider(self) -> None:
        response = self.client.get("/api/v1/voice/models", params={"type": "realtime"})
        self.assertEqual(response.status_code, 200, response.text)
        models = response.json()
        self.assertEqual({model["id"] for model in models}, {"ultravox:ultravox", "ultravox:ultravox-v0.7"})
        self.assertTrue(all(model["execution_model_id"] == "fixie-ai/ultravox" for model in models))
        self.assertTrue(all(model["implementation_status"] == "available" for model in models))

        empty = self.client.get("/api/v1/voice/models", params={"type": "stt"})
        self.assertEqual(empty.json(), [])

        by_provider = self.client.get("/api/v1/voice/models", params={"provider": "openai"})
        self.assertEqual(by_provider.json(), [])

    def test_get_model_not_found(self) -> None:
        response = self.client.get("/api/v1/voice/models/openai:gpt-realtime")
        self.assertEqual(response.status_code, 404)

    def test_get_model_capabilities_matches_model(self) -> None:
        model_response = self.client.get("/api/v1/voice/models/ultravox:ultravox")
        capabilities_response = self.client.get(
            "/api/v1/voice/models/ultravox:ultravox/capabilities"
        )
        self.assertEqual(capabilities_response.status_code, 200, capabilities_response.text)
        self.assertEqual(capabilities_response.json(), model_response.json()["capabilities"])
        self.assertTrue(capabilities_response.json()["tools"])

    def test_registry_api_response_keeps_capabilities_boolean_and_external_providers_separate(self) -> None:
        response = self.client.get("/api/v1/voice/models", params={"provider": "ultravox"})
        self.assertEqual(response.status_code, 200, response.text)
        models = {model["id"]: model for model in response.json()}
        for model_id in ("ultravox:ultravox", "ultravox:ultravox-v0.7"):
            model = models[model_id]
            self.assertEqual(model["capabilities"]["provider_voice"], True)
            self.assertEqual(model["capabilities"]["provider_external_voice"], True)
            self.assertTrue(all(isinstance(v, bool) for v in model["capabilities"].values()))
            self.assertEqual(model["external_voice_providers"], ["elevenlabs"])
            self.assertNotIn("external_voice_providers", model["capabilities"])

    def test_capabilities_stay_boolean_only(self) -> None:
        from app.domain import voice_registry

        for model in voice_registry.list_models(provider_key="ultravox"):
            self.assertTrue(all(isinstance(value, bool) for value in model.capabilities.values()))
            self.assertIsInstance(model.external_voice_providers, tuple)
            self.assertTrue(all(isinstance(item, str) for item in model.external_voice_providers))

    def test_voice_compatibility_provider_mode_requires_matching_provider(self) -> None:
        from app.domain import voice_registry

        for model_key in ("ultravox", "ultravox-v0.7"):
            voice_registry.validate_voice_compatibility("ultravox", model_key, "provider", "ultravox")
            with self.assertRaises(voice_registry.VoiceRegistryValidationError):
                voice_registry.validate_voice_compatibility("ultravox", model_key, "provider", "elevenlabs")

    def test_voice_compatibility_provider_external_requires_supported_provider(self) -> None:
        from app.domain import voice_registry

        for model_key in ("ultravox", "ultravox-v0.7"):
            voice_registry.validate_voice_compatibility(
                "ultravox", model_key, "provider_external", "elevenlabs"
            )
            with self.assertRaises(voice_registry.VoiceRegistryValidationError):
                voice_registry.validate_voice_compatibility(
                    "ultravox", model_key, "provider_external", "cartesia"
                )
            with self.assertRaises(voice_registry.VoiceRegistryValidationError):
                voice_registry.validate_voice_compatibility(
                    "ultravox", model_key, "provider_external", "google"
                )

    def test_voice_compatibility_rejects_unknown_mode_and_model(self) -> None:
        from app.domain import voice_registry

        with self.assertRaises(voice_registry.VoiceRegistryValidationError):
            voice_registry.validate_voice_compatibility("ultravox", "ultravox", "native", "ultravox")
        with self.assertRaises(voice_registry.VoiceRegistryValidationError):
            voice_registry.validate_voice_compatibility("openai", "gpt-realtime", "provider", "openai")


if __name__ == "__main__":
    unittest.main()
