from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.crm import CrmBooking
from app.models.integrations import TenantGoogleCalendar, TenantGoogleCalendarConnection
from app.services.google_calendar_oauth_service import GoogleCalendarOAuthService
from app.services.scheduling_availability_service import SchedulingAvailabilityService


class SchedulingAvailabilityTests(Integration2ATestCase):
    def setUp(self):
        super().setUp()
        with SessionLocal() as db:
            service = GoogleCalendarOAuthService(db)
            self.connection = service.store_connection(
                tenant_id=self.tenant.id,
                user_id=self.user.id,
                google_account_email="schedule@example.com",
                access_token="token",
                refresh_token="refresh",
            )
            self.cal = TenantGoogleCalendar(
                tenant_id=self.tenant.id,
                connection_id=self.connection.id,
                google_calendar_id="primary",
                summary="Primary Calendar",
                is_primary=True,
                is_blocking=True,
                is_booking_destination=True,
            )
            db.add(self.cal)
            db.commit()

    def test_availability_calculates_slots_and_excludes_freebusy(self):
        with SessionLocal() as db:
            mock_g_service = MagicMock()
            # Busy interval from 10:00 to 11:00 UTC (05:00 to 06:00 America/Bogota)
            # Working hours: 08:00 to 18:00 America/Bogota (13:00 to 23:00 UTC)
            # Let's mock a busy period at 10:00 to 11:00 America/Bogota (15:00 to 16:00 UTC)
            mock_g_service.get_freebusy_intervals.return_value = [
                {
                    "start": datetime(2026, 9, 15, 15, 0, tzinfo=UTC),
                    "end": datetime(2026, 9, 15, 16, 0, tzinfo=UTC),
                }
            ]

            service = SchedulingAvailabilityService(db, google_calendar_service=mock_g_service)
            result = service.get_available_slots(
                tenant_id=self.tenant.id,
                date_input="2026-09-15",
                reference_datetime="2026-09-14 12:00:00",
                timezone_str="America/Bogota",
                slot_duration_minutes=30,
            )

            self.assertEqual(result["date"], "2026-09-15")
            slots = result["available_slots"]
            times = [s["time"] for s in slots]

            # 09:00, 09:30 should be available
            self.assertIn("09:00", times)
            self.assertIn("09:30", times)

            # 10:00 and 10:30 fall inside 15:00-16:00 UTC (10:00-11:00 local) -> MUST BE EXCLUDED
            self.assertNotIn("10:00", times)
            self.assertNotIn("10:30", times)

            # 11:00 should be available
            self.assertIn("11:00", times)

    def test_availability_jornada_filter(self):
        with SessionLocal() as db:
            mock_g_service = MagicMock()
            mock_g_service.get_freebusy_intervals.return_value = []

            service = SchedulingAvailabilityService(db, google_calendar_service=mock_g_service)
            result_manana = service.get_available_slots(
                tenant_id=self.tenant.id,
                date_input="2026-09-15",
                jornada="manana",
                reference_datetime="2026-09-14 12:00:00",
                timezone_str="America/Bogota",
            )
            times_manana = [s["time"] for s in result_manana["available_slots"]]
            for t in times_manana:
                self.assertLessEqual(t, "11:30")
                self.assertGreaterEqual(t, "09:00")

    def test_availability_excludes_existing_crm_bookings(self):
        with SessionLocal() as db:
            # Add existing booking in DB from 14:00 to 14:30 America/Bogota (19:00 to 19:30 UTC)
            existing_booking = CrmBooking(
                tenant_id=self.tenant.id,
                provider="google_calendar",
                status="accepted",
                start_at=datetime(2026, 9, 15, 19, 0, tzinfo=UTC),
                end_at=datetime(2026, 9, 15, 19, 30, tzinfo=UTC),
                timezone="America/Bogota",
                duration_minutes=30,
                attendee_name="Cliente Existente",
                attendee_email="cliente@example.com",
                calendar_mode="crm_google_insert",
            )
            db.add(existing_booking)
            db.commit()

            mock_g_service = MagicMock()
            mock_g_service.get_freebusy_intervals.return_value = []

            service = SchedulingAvailabilityService(db, google_calendar_service=mock_g_service)
            result = service.get_available_slots(
                tenant_id=self.tenant.id,
                date_input="2026-09-15",
                reference_datetime="2026-09-14 12:00:00",
                timezone_str="America/Bogota",
            )
            times = [s["time"] for s in result["available_slots"]]
            self.assertNotIn("14:00", times)
            self.assertIn("14:30", times)
