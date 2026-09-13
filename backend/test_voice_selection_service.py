from __future__ import annotations

import unittest

from app.schemas.agents import AgentVoiceConfig
from app.services.voice_selection_service import VoiceSelectionError, VoiceSelectionService


class VoiceSelectionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = VoiceSelectionService()

    def test_accepts_provider_voice_matching_realtime_provider(self) -> None:
        voice = AgentVoiceConfig(mode="provider", provider="ultravox", voice_id="Mark")
        self.service.validate("ultravox", "ultravox", voice)  # no exception

    def test_accepts_provider_external_elevenlabs_for_ultravox(self) -> None:
        voice = AgentVoiceConfig(mode="provider_external", provider="elevenlabs", voice_id="x")
        self.service.validate("ultravox", "ultravox-v0.7", voice)  # no exception

    def test_rejects_provider_voice_from_a_different_provider(self) -> None:
        voice = AgentVoiceConfig(mode="provider", provider="elevenlabs", voice_id="x")
        with self.assertRaises(VoiceSelectionError):
            self.service.validate("ultravox", "ultravox", voice)

    def test_rejects_unsupported_external_provider(self) -> None:
        voice = AgentVoiceConfig(mode="provider_external", provider="cartesia", voice_id="x")
        with self.assertRaises(VoiceSelectionError):
            self.service.validate("ultravox", "ultravox", voice)

    def test_validate_performs_no_network_or_db_io(self) -> None:
        # A VoiceSelectionService instance has no db/http client attributes at
        # all in Phase A -- validate() only touches the in-memory registry.
        self.assertEqual(vars(self.service), {})


if __name__ == "__main__":
    unittest.main()
