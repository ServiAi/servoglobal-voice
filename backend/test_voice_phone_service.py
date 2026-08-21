from __future__ import annotations

import unittest

from app.services.voice_phone_service import VoicePhoneValidationError, normalize_outbound_phone


class VoicePhoneServiceTests(unittest.TestCase):
    def test_normalizes_supported_destinations_to_e164(self):
        examples = {
            "CO": "+573211234567",
            "MX": "+522221234567",
            "AR": "+5491123456789",
            "PA": "+50761234567",
            "CL": "+56961234567",
            "EC": "+593991234567",
            "PE": "+51912345678",
            "US": "+12015550123",
        }

        for country, value in examples.items():
            with self.subTest(country=country):
                result = normalize_outbound_phone(value)
                self.assertEqual(result.e164, value)
                self.assertEqual(result.country, country)

    def test_uses_default_country_for_local_number(self):
        result = normalize_outbound_phone("3211234567", default_country="CO")
        self.assertEqual(result.e164, "+573211234567")

    def test_rejects_ambiguous_local_number_without_country(self):
        with self.assertRaises(VoicePhoneValidationError):
            normalize_outbound_phone("3211234567")

    def test_rejects_fixed_line_in_mobile_only_country(self):
        with self.assertRaises(VoicePhoneValidationError):
            normalize_outbound_phone("+5712345678")

    def test_rejects_country_not_enabled_for_tenant(self):
        with self.assertRaises(VoicePhoneValidationError):
            normalize_outbound_phone("+12015550123", allowed_countries={"CO"})


if __name__ == "__main__":
    unittest.main()
