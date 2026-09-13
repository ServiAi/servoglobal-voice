from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.agents import AgentVoiceConfig


class AgentVoiceConfigSchemaTests(unittest.TestCase):
    def test_mode_provider_is_valid(self) -> None:
        voice = AgentVoiceConfig(mode="provider", provider="ultravox", voice_id="Mark")
        self.assertEqual(voice.mode, "provider")
        self.assertEqual(voice.settings, {})

    def test_mode_provider_external_is_valid(self) -> None:
        voice = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="21m00Tcm4TlvDq8ikWAM",
            settings={"model": "eleven_turbo_v2_5", "speed": 1.0, "stability": 0.8,
                      "similarity_boost": 0.8, "use_speaker_boost": True},
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

    def test_provider_mode_rejects_any_settings(self) -> None:
        with self.assertRaises(ValidationError):
            AgentVoiceConfig(mode="provider", provider="ultravox", voice_id="Mark", settings={"speed": 1.0})

    def test_unknown_elevenlabs_setting_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            AgentVoiceConfig(
                mode="provider_external", provider="elevenlabs", voice_id="x", settings={"pitch": 1}
            )

    def test_secret_like_setting_key_is_rejected(self) -> None:
        for key in ("api_key", "apikey", "secret", "token", "password", "authorization", "header"):
            with self.assertRaises(ValidationError, msg=key):
                AgentVoiceConfig(
                    mode="provider_external", provider="elevenlabs", voice_id="x", settings={key: "leak"}
                )

    def test_speed_out_of_range_is_rejected(self) -> None:
        for value in (0.5, 1.5):
            with self.assertRaises(ValidationError, msg=value):
                AgentVoiceConfig(
                    mode="provider_external", provider="elevenlabs", voice_id="x", settings={"speed": value}
                )

    def test_speed_within_range_is_accepted(self) -> None:
        for value in (0.7, 1.0, 1.2):
            AgentVoiceConfig(
                mode="provider_external", provider="elevenlabs", voice_id="x", settings={"speed": value}
            )

    def test_stability_and_similarity_boost_wrong_type_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            AgentVoiceConfig(
                mode="provider_external", provider="elevenlabs", voice_id="x",
                settings={"stability": "high"},
            )
        with self.assertRaises(ValidationError):
            AgentVoiceConfig(
                mode="provider_external", provider="elevenlabs", voice_id="x",
                settings={"similarity_boost": "0.8"},
            )

    def test_bool_is_not_accepted_as_a_number(self) -> None:
        with self.assertRaises(ValidationError):
            AgentVoiceConfig(
                mode="provider_external", provider="elevenlabs", voice_id="x", settings={"speed": True}
            )

    def test_use_speaker_boost_must_be_boolean(self) -> None:
        with self.assertRaises(ValidationError):
            AgentVoiceConfig(
                mode="provider_external", provider="elevenlabs", voice_id="x",
                settings={"use_speaker_boost": "yes"},
            )

    def test_model_must_be_non_empty_string_within_length(self) -> None:
        with self.assertRaises(ValidationError):
            AgentVoiceConfig(
                mode="provider_external", provider="elevenlabs", voice_id="x", settings={"model": ""}
            )
        with self.assertRaises(ValidationError):
            AgentVoiceConfig(
                mode="provider_external", provider="elevenlabs", voice_id="x",
                settings={"model": "x" * 81},
            )

    def test_model_is_not_restricted_to_a_closed_allowlist(self) -> None:
        # V1 explicitly avoids a hardcoded ElevenLabs model enum: any
        # reasonable string is accepted here, real validation happens via
        # the explicit "Probar voz" preview action in a later phase.
        AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="x",
            settings={"model": "some_future_elevenlabs_model"},
        )


if __name__ == "__main__":
    unittest.main()
