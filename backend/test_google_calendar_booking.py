from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.core.config import settings
from app.models.analytics import Agent
from app.models.crm import CrmBooking, CrmCallContext, CrmLead
from app.models.integrations import TenantGoogleCalendar, TenantGoogleCalendarConnection
from app.schemas.crm import BookingCreateRequest
from app.services.booking_service import BookingService
from app.services.google_calendar_oauth_service import GoogleCalendarOAuthService


class GoogleCalendarBookingTests(Integration2ATestCase):
    def setUp(self):
        super().setUp()
        settings.VOICE_TOOL_SHARED_SECRET = "test_voice_tool_secret"
        settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID = "test_client_id"
        settings.GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET = "test_client_secret"
        settings.GOOGLE_CALENDAR_REDIRECT_URI = "https://example.com/callback"

        with SessionLocal() as db:
            service = GoogleCalendarOAuthService(db)
            self.connection = service.store_connection(
                tenant_id=self.tenant.id,
                user_id=self.user.id,
                google_account_email="google_booking@example.com",
                access_token="google_access_token",
                refresh_token="google_refresh_token",
                token_expires_at=datetime.now(UTC) + timedelta(hours=1),
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

        self.lead_id, self.contact_id = self.seed_lead(email="maria@example.com")

    @patch("app.services.google_calendar_service.GoogleCalendarService.create_event")
    def test_create_lead_booking_with_google_calendar(self, mock_create_event):
        mock_create_event.return_value = {
            "id": "g_event_12345",
            "htmlLink": "https://calendar.google.com/event?eid=12345",
            "hangoutLink": "https://meet.google.com/abc-defg-hij",
        }

        with SessionLocal() as db:
            service = BookingService(db)
            booking = service.create_lead_booking(
                tenant_id=self.tenant.id,
                lead_id=self.lead_id,
                body=BookingCreateRequest(
                    start="2026-09-15T15:00:00Z",
                    attendee_name="Maria Perez",
                    attendee_email="maria@example.com",
                    attendee_phone="+573001234567",
                    notes="Consulta de servicios",
                ),
            )

            self.assertEqual(booking.provider, "google_calendar")
            self.assertEqual(booking.status, "accepted")
            self.assertEqual(booking.google_calendar_event_id, "g_event_12345")
            self.assertEqual(booking.meeting_url, "https://meet.google.com/abc-defg-hij")

            # Check in DB
            stored = db.get(CrmBooking, booking.id)
            self.assertIsNotNone(stored)
            self.assertEqual(stored.provider_booking_id, "g_event_12345")

    @patch("app.services.google_calendar_service.GoogleCalendarService.create_event")
    def test_voice_booking_tool_end_to_end_with_google_calendar(self, mock_create_event):
        mock_create_event.return_value = {
            "id": "g_voice_event_999",
            "htmlLink": "https://calendar.google.com/event?eid=999",
            "hangoutLink": "https://meet.google.com/uvw-xyza-bcd",
        }

        self.seed_call_context(context_id="ctx_voice_google_1")

        with SessionLocal() as db:
            lead = db.get(CrmLead, self.lead_id)
            lead.context_id = "ctx_voice_google_1"
            agent = Agent(
                tenant_id=self.tenant.id,
                external_agent_id="agent_voice_google",
                name="Agente Google",
                status="active",
            )
            db.add(agent)
            db.commit()

        # 1. Test voice availability endpoint
        with patch("app.services.google_calendar_service.GoogleCalendarService.get_freebusy_intervals", return_value=[]):
            avail_res = self.client.post(
                "/api/v1/voice/tools/availability",
                headers={"X-Voice-Tool-Secret": "test_voice_tool_secret"},
                json={
                    "agent_id": "agent_voice_google",
                    "call_context_id": "ctx_voice_google_1",
                    "date": "2026-09-15",
                },
            )
            self.assertEqual(avail_res.status_code, 200)
            payload = avail_res.json()
            self.assertEqual(payload["date"], "2026-09-15")
            self.assertGreater(len(payload["available_slots"]), 0)

        # 2. Test voice booking endpoint
        book_res = self.client.post(
            "/api/v1/voice/tools/bookings",
            headers={"X-Voice-Tool-Secret": "test_voice_tool_secret"},
            json={
                "agent_id": "agent_voice_google",
                "call_context_id": "ctx_voice_google_1",
                "start": "2026-09-15T15:00:00Z",
                "attendee_name": "Maria Perez",
                "attendee_email": "maria@example.com",
                "attendee_phone": "+573001234567",
            },
        )
        self.assertEqual(book_res.status_code, 200)
        book_payload = book_res.json()
        self.assertEqual(book_payload["status"], "accepted")
        self.assertIn("booking_id", book_payload)

    @patch("app.services.google_calendar_service.GoogleCalendarService.delete_event")
    @patch("app.services.google_calendar_service.GoogleCalendarService.patch_event")
    @patch("app.services.google_calendar_service.GoogleCalendarService.create_event")
    def test_reschedule_and_cancel_google_booking(self, mock_create, mock_patch, mock_delete):
        mock_create.return_value = {"id": "g_evt_resched", "htmlLink": "https://calendar.google.com"}
        mock_patch.return_value = {"id": "g_evt_resched"}
        mock_delete.return_value = True

        with SessionLocal() as db:
            service = BookingService(db)
            booking = service.create_lead_booking(
                tenant_id=self.tenant.id,
                lead_id=self.lead_id,
                body=BookingCreateRequest(
                    start="2026-09-15T15:00:00Z",
                    attendee_name="Maria Perez",
                    attendee_email="maria@example.com",
                ),
            )

            # Reschedule
            resched = service.reschedule_lead_booking(
                tenant_id=self.tenant.id,
                booking_id=booking.id,
                new_start_time="2026-09-16T16:00:00Z",
            )
            self.assertEqual(resched["status"], "success")
            db.refresh(booking)
            self.assertEqual(booking.status, "scheduled")
            mock_patch.assert_called_once()

            # Cancel
            cancel_res = service.cancel_lead_booking(
                tenant_id=self.tenant.id,
                booking_id=booking.id,
            )
            self.assertEqual(cancel_res["status"], "success")
            db.refresh(booking)
            self.assertEqual(booking.status, "cancelled")
            mock_delete.assert_called_once()
