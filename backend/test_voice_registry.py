from __future__ import annotations

import unittest

from _integrations_2a_test_base import Integration2ATestCase


class VoiceRegistryTests(Integration2ATestCase):
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
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["id"], "ultravox:ultravox")
        self.assertEqual(models[0]["implementation_status"], "available")

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


if __name__ == "__main__":
    unittest.main()
