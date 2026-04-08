import unittest

from app.services.date_resolution_service import resolve_temporal_expression


REFERENCE_DATETIME = "2026-04-08 13:44:07"


class TemporalResolutionTests(unittest.TestCase):
    def assert_resolution(self, expression: str, expected_date: str, expected_day: str):
        result = resolve_temporal_expression(expression, REFERENCE_DATETIME)
        self.assertEqual(result.date, expected_date)
        self.assertEqual(result.day_name, expected_day)

    def test_relative_keywords(self):
        self.assert_resolution("hoy", "2026-04-08", "miercoles")
        self.assert_resolution("mañana", "2026-04-09", "jueves")
        self.assert_resolution("pasado mañana", "2026-04-10", "viernes")

    def test_plain_weekdays(self):
        self.assert_resolution("viernes", "2026-04-10", "viernes")
        self.assert_resolution("el viernes", "2026-04-10", "viernes")
        self.assert_resolution("domingo", "2026-04-12", "domingo")

    def test_weekdays_with_qualifiers(self):
        self.assert_resolution("este viernes", "2026-04-10", "viernes")
        self.assert_resolution("proximo sabado", "2026-04-11", "sabado")
        self.assert_resolution("próximo sábado", "2026-04-11", "sabado")


if __name__ == "__main__":
    unittest.main()
