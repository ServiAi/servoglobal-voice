from __future__ import annotations

import json
import unittest

from serviglobal_voice_runtime.config import Settings
from serviglobal_voice_runtime.contracts import RuntimeSessionSpecV1
from serviglobal_voice_runtime.providers import RealtimeProviderFactory, UnsupportedRuntimeProviderError, language_hint, ultravox_options
from serviglobal_voice_runtime.worker import parse_session_id


def settings() -> Settings:
    return Settings(
        CONTROL_PLANE_BASE_URL="http://control-plane",
        VOICE_RUNTIME_SERVICE_SECRET="x" * 32,
        LIVEKIT_URL="wss://example.livekit.cloud",
        LIVEKIT_API_KEY="key",
        LIVEKIT_API_SECRET="secret",
        ULTRAVOX_API_KEY="ultravox-key",
    )


def spec(**runtime_settings) -> RuntimeSessionSpecV1:
    return RuntimeSessionSpecV1.model_validate({
        "spec_version": "1", "session_id": "session-1", "tenant_id": "tenant-1", "agent_id": "agent-1", "agent_version_id": "version-1",
        "identity": {"name": "Sandra", "description": None},
        "instructions": {"role": "Advisor", "objective": "Help", "system_prompt": "Published prompt", "greeting": "Hola", "closing": "Adios"},
        "behavior": {"response_style": "balanced", "interruptions": "balanced", "turn_detection": "automatic", "confirmation_strategy": "important_data", "agent_first": True},
        "language": "es-CO", "timezone": "America/Bogota",
        "runtime": {"pipeline_type": "realtime", "realtime": {"provider": "ultravox", "model": "fixie-ai/ultravox", "settings": runtime_settings}},
        "context": {},
    })


class RuntimeTests(unittest.TestCase):
    def test_metadata_contains_only_session_id(self) -> None:
        self.assertEqual(parse_session_id(json.dumps({"session_id": "session-1"})), "session-1")
        with self.assertRaises(ValueError):
            parse_session_id(json.dumps({"session_id": "session-1", "prompt": "secret"}))

    def test_ultravox_mapping(self) -> None:
        options = ultravox_options(spec(voice="Mark", temperature=0.3), "key")
        self.assertEqual(options["voice"], "Mark")
        self.assertEqual(options["language_hint"], "es")
        self.assertEqual(options["first_speaker"], "FIRST_SPEAKER_AGENT")
        self.assertIn("Published prompt", options["system_prompt"])
        self.assertIn("Hola", options["system_prompt"])

    def test_language_mapping(self) -> None:
        self.assertEqual(language_hint("es-CO"), "es")

    def test_invalid_temperature_and_unknown_provider_fail_closed(self) -> None:
        with self.assertRaises(UnsupportedRuntimeProviderError):
            ultravox_options(spec(temperature=1.1), "key")
        with self.assertRaises(UnsupportedRuntimeProviderError):
            RealtimeProviderFactory(settings()).resolve("openai")

    def test_contract_rejects_secret_context(self) -> None:
        data = spec().model_dump()
        data["context"] = {"nested": {"api_key": "must-not-pass"}}
        with self.assertRaises(ValueError):
            RuntimeSessionSpecV1.model_validate(data)


if __name__ == "__main__":
    unittest.main()
