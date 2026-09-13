from __future__ import annotations

import unittest
from unittest.mock import Mock

from app.services.ultravox_admin_service import UltravoxAdminService
from app.services.voice_provider_admin import (
    VoiceProviderNotAvailableError, get_provider_admin_service,
)


class VoiceProviderAdminDispatchTests(unittest.TestCase):
    def test_ultravox_resolves_to_its_adapter(self) -> None:
        service = get_provider_admin_service(Mock(), "ultravox")
        self.assertIsInstance(service, UltravoxAdminService)

    def test_planned_provider_without_an_adapter_is_rejected(self) -> None:
        with self.assertRaises(VoiceProviderNotAvailableError):
            get_provider_admin_service(Mock(), "elevenlabs")

    def test_unknown_provider_key_is_rejected(self) -> None:
        with self.assertRaises(VoiceProviderNotAvailableError):
            get_provider_admin_service(Mock(), "not-a-real-provider")


if __name__ == "__main__":
    unittest.main()
