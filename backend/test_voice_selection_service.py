from __future__ import annotations

import unittest

from app.schemas.agents import AgentVoiceConfig
from app.services.voice_selection_service import VoiceSelectionError, VoiceSelectionService


class VoiceSelectionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = VoiceSelectionService()

    # -- registry compatibility (delegates to voice_registry.validate_voice_compatibility) --

    def test_accepts_provider_voice_matching_realtime_provider(self) -> None:
        voice = AgentVoiceConfig(mode="provider", provider="ultravox", voice_id="Mark")
        self.service.validate("ultravox", "ultravox", voice)  # no exception

    def test_accepts_provider_external_elevenlabs_for_ultravox(self) -> None:
        voice = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="x",
            settings={"model": "eleven_turbo_v2_5"},
        )
        self.service.validate("ultravox", "ultravox-v0.7", voice)  # no exception

    def test_rejects_provider_voice_from_a_different_provider(self) -> None:
        voice = AgentVoiceConfig(mode="provider", provider="elevenlabs", voice_id="x")
        with self.assertRaises(VoiceSelectionError):
            self.service.validate("ultravox", "ultravox", voice)

    def test_rejects_unsupported_external_provider(self) -> None:
        voice = AgentVoiceConfig(mode="provider_external", provider="cartesia", voice_id="x")
        with self.assertRaises(VoiceSelectionError):
            self.service.validate("ultravox", "ultravox", voice)

    # -- settings shape rules (provider-specific business logic; NOT on AgentVoiceConfig) --

    def test_provider_mode_rejects_any_settings(self) -> None:
        voice = AgentVoiceConfig(mode="provider", provider="ultravox", voice_id="Mark", settings={"speed": 1})
        with self.assertRaises(VoiceSelectionError):
            self.service.validate("ultravox", "ultravox", voice)

    def test_elevenlabs_valid_settings_are_accepted(self) -> None:
        voice = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="x",
            settings={"model": "eleven_turbo_v2_5", "speed": 1.0, "stability": 0.8,
                      "similarity_boost": 0.8, "use_speaker_boost": True},
        )
        self.service.validate("ultravox", "ultravox", voice)  # no exception

    def test_elevenlabs_unknown_setting_is_rejected(self) -> None:
        voice = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="x",
            settings={"model": "eleven_turbo_v2_5", "pitch": 1},
        )
        with self.assertRaises(VoiceSelectionError):
            self.service.validate("ultravox", "ultravox", voice)

    def test_elevenlabs_speed_out_of_range_is_rejected(self) -> None:
        for value in (0.5, 1.5):
            voice = AgentVoiceConfig(
                mode="provider_external", provider="elevenlabs", voice_id="x",
                settings={"model": "eleven_turbo_v2_5", "speed": value},
            )
            with self.assertRaises(VoiceSelectionError, msg=value):
                self.service.validate("ultravox", "ultravox", voice)

    def test_elevenlabs_speed_within_range_is_accepted(self) -> None:
        for value in (0.7, 1.0, 1.2):
            voice = AgentVoiceConfig(
                mode="provider_external", provider="elevenlabs", voice_id="x",
                settings={"model": "eleven_turbo_v2_5", "speed": value},
            )
            self.service.validate("ultravox", "ultravox", voice)

    def test_elevenlabs_stability_and_similarity_boost_wrong_type_is_rejected(self) -> None:
        for key, value in (("stability", "high"), ("similarity_boost", "0.8")):
            voice = AgentVoiceConfig(
                mode="provider_external", provider="elevenlabs", voice_id="x",
                settings={"model": "eleven_turbo_v2_5", key: value},
            )
            with self.assertRaises(VoiceSelectionError, msg=key):
                self.service.validate("ultravox", "ultravox", voice)

    def test_elevenlabs_bool_is_not_accepted_as_a_number(self) -> None:
        voice = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="x",
            settings={"model": "eleven_turbo_v2_5", "speed": True},
        )
        with self.assertRaises(VoiceSelectionError):
            self.service.validate("ultravox", "ultravox", voice)

    def test_elevenlabs_use_speaker_boost_must_be_boolean(self) -> None:
        voice = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="x",
            settings={"model": "eleven_turbo_v2_5", "use_speaker_boost": "yes"},
        )
        with self.assertRaises(VoiceSelectionError):
            self.service.validate("ultravox", "ultravox", voice)

    def test_elevenlabs_model_must_be_non_empty_string_within_length(self) -> None:
        for value in ("", "   ", "x" * 81):
            voice = AgentVoiceConfig(
                mode="provider_external", provider="elevenlabs", voice_id="x", settings={"model": value}
            )
            with self.assertRaises(VoiceSelectionError, msg=repr(value)):
                self.service.validate("ultravox", "ultravox", voice)

    def test_elevenlabs_model_is_required(self) -> None:
        voice = AgentVoiceConfig(mode="provider_external", provider="elevenlabs", voice_id="ABC123", settings={})
        with self.assertRaisesRegex(VoiceSelectionError, "model"):
            self.service.validate("ultravox", "ultravox", voice)

    def test_elevenlabs_voice_id_must_not_be_whitespace(self) -> None:
        voice = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="   ",
            settings={"model": "eleven_turbo_v2_5"},
        )
        with self.assertRaisesRegex(VoiceSelectionError, "Voice ID"):
            self.service.validate("ultravox", "ultravox", voice)

    def test_elevenlabs_model_is_not_restricted_to_a_closed_allowlist(self) -> None:
        # V1 explicitly avoids a hardcoded ElevenLabs model enum: any
        # reasonable string is accepted here, real validation happens via
        # the explicit "Probar voz" preview action in a later phase.
        voice = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="x",
            settings={"model": "future_model_x"},
        )
        self.service.validate("ultravox", "ultravox", voice)

    # -- no I/O --

    def test_validate_performs_no_network_or_db_io(self) -> None:
        # A VoiceSelectionService instance has no db/http client attributes at
        # all in Phase A -- validate() only touches the in-memory registry
        # and the AgentVoiceConfig it was given.
        self.assertEqual(vars(self.service), {})


if __name__ == "__main__":
    unittest.main()
