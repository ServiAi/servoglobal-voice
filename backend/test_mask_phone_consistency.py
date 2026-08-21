from __future__ import annotations

import unittest

from app.services.voice_call_service import VoiceCallService
from app.services.whatsapp_message_service import mask_phone as whatsapp_mask_phone


class MaskPhoneConsistencyTests(unittest.TestCase):
    def test_four_digit_input_is_fully_redacted_in_both_implementations(self) -> None:
        # A 4-digit value is short enough that "last 4 digits" would reveal
        # the whole number; both maskers must fully redact it.
        self.assertEqual(whatsapp_mask_phone("1234"), "***")
        self.assertEqual(VoiceCallService.mask_phone(None, "1234"), "***")

    def test_five_digit_input_reveals_only_last_four(self) -> None:
        self.assertEqual(whatsapp_mask_phone("12345"), "***2345")
        self.assertEqual(VoiceCallService.mask_phone(None, "12345"), "***2345")


if __name__ == "__main__":
    unittest.main()
