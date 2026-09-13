from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.agents import AgentVoiceConfig


class AgentVoiceConfigSchemaTests(unittest.TestCase):
    """AgentVoiceConfig validates shape only: mode/provider/voice_id types,
    settings is a plain mapping, and no secret-like setting keys. Any
    provider-specific business rule (which settings a given mode/provider
    allows, their ranges) lives in VoiceSelectionService -- see
    test_voice_selection_service.py, not this file."""

    def test_mode_provider_is_valid(self) -> None:
        voice = AgentVoiceConfig(mode="provider", provider="ultravox", voice_id="Mark")
        self.assertEqual(voice.mode, "provider")
        self.assertEqual(voice.settings, {})

    def test_mode_provider_external_is_valid(self) -> None:
        voice = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="21m00Tcm4TlvDq8ikWAM",
            settings={"model": "eleven_turbo_v2_5", "speed": 1.0},
        )
        self.assertEqual(voice.mode, "provider_external")

    def test_mode_native_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            AgentVoiceConfig(mode="native", provider="ultravox", voice_id="Mark")

    def test_mode_tts_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            AgentVoiceConfig(mode="tts", provider="elevenlabs", voice_id="x")

    def test_import_agent_shape_without_settings_key_still_parses(self) -> None:
        # Exact shape UltravoxAdminService.import_agent() persists today.
        voice = AgentVoiceConfig.model_validate({
            "mode": "provider", "provider": "ultravox", "voice_id": "Mark",
        })
        self.assertEqual(voice.settings, {})

    def test_settings_must_be_a_mapping(self) -> None:
        with self.assertRaises(ValidationError):
            AgentVoiceConfig(mode="provider", provider="ultravox", voice_id="Mark", settings=["not", "a", "dict"])
        with self.assertRaises(ValidationError):
            AgentVoiceConfig(mode="provider", provider="ultravox", voice_id="Mark", settings="not a dict")

    def test_settings_default_does_not_share_state_across_instances(self) -> None:
        first = AgentVoiceConfig(mode="provider", provider="ultravox", voice_id="Mark")
        second = AgentVoiceConfig(mode="provider", provider="ultravox", voice_id="Jessica")
        self.assertIsNot(first.settings, second.settings)
        # Mutating one instance's default-constructed settings must never
        # leak into another instance (the classic mutable-default bug).
        first.settings["leaked"] = True
        self.assertEqual(second.settings, {})

    def test_secret_like_setting_key_is_rejected(self) -> None:
        for key in ("api_key", "apikey", "secret", "token", "password", "authorization", "header"):
            with self.assertRaises(ValidationError, msg=key):
                AgentVoiceConfig(
                    mode="provider_external", provider="elevenlabs", voice_id="x", settings={key: "leak"}
                )

    def test_schema_does_not_reject_settings_that_only_a_provider_rule_would(self) -> None:
        # Proves the shape-only boundary: AgentVoiceConfig has no opinion on
        # which keys/ranges are valid for a given (mode, provider) -- that
        # is VoiceSelectionService's job, not this schema's.
        AgentVoiceConfig(mode="provider", provider="ultravox", voice_id="Mark", settings={"speed": 999})
        AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="x", settings={"totally_unknown_key": 1}
        )


if __name__ == "__main__":
    unittest.main()
