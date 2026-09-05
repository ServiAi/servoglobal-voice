from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.core.config import settings
from app.models.crm import CrmBooking
from app.models.integrations import (
    TenantGoogleCalendar,
    TenantGoogleCalendarConnection,
    TenantSchedulingResource,
    TenantSchedulingResourceCalendar,
)
from app.schemas.crm import BookingCreateRequest
from app.services.booking_service import BookingService
from app.services.google_calendar_oauth_service import GoogleCalendarOAuthService
from app.services.scheduling_resource_service import SchedulingResourceService


class SchedulingResourcesTests(Integration2ATestCase):
    def setUp(self):
        super().setUp()
        settings.VOICE_TOOL_SHARED_SECRET = "test_voice_tool_secret"
        settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID = "test_client_id"
        settings.GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET = "test_client_secret"
        settings.GOOGLE_CALENDAR_REDIRECT_URI = "https://example.com/callback"

        with SessionLocal() as db:
            oauth_svc = GoogleCalendarOAuthService(db)
            self.connection = oauth_svc.store_connection(
                tenant_id=self.tenant.id,
                user_id=self.user.id,
                google_account_email="roundrobin_test@example.com",
                access_token="google_access_token",
                refresh_token="google_refresh_token",
                token_expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            self.cal_alice = TenantGoogleCalendar(
                tenant_id=self.tenant.id,
                connection_id=self.connection.id,
                google_calendar_id="alice@example.com",
                summary="Alice Calendar",
                is_primary=True,
                is_blocking=True,
                is_booking_destination=True,
            )
            self.cal_bob = TenantGoogleCalendar(
                tenant_id=self.tenant.id,
                connection_id=self.connection.id,
                google_calendar_id="bob@example.com",
                summary="Bob Calendar",
                is_primary=False,
                is_blocking=True,
                is_booking_destination=True,
            )
            db.add_all([self.cal_alice, self.cal_bob])
            db.commit()

        self.lead_id, self.contact_id = self.seed_lead(email="lead_rr@example.com")

    def test_resource_creation_and_calendar_assignment(self):
        with SessionLocal() as db:
            svc = SchedulingResourceService(db)
            resource = svc.create_resource(
                tenant_id=self.tenant.id,
                name="Dr. Alice Smith",
                resource_type="doctor",
                team="medical",
                email="alice@example.com",
                priority=10,
            )
            self.assertIsNotNone(resource.id)
            self.assertEqual(resource.name, "Dr. Alice Smith")
            self.assertEqual(resource.team, "medical")

            mapping = svc.assign_calendar_to_resource(
                tenant_id=self.tenant.id,
                resource_id=resource.id,
                calendar_id=self.cal_alice.id,
                is_blocking=True,
                is_destination=True,
            )
            self.assertIsNotNone(mapping.id)
            self.assertTrue(mapping.is_blocking)
            self.assertTrue(mapping.is_destination)

            resources = svc.list_resources(tenant_id=self.tenant.id)
            self.assertEqual(len(resources), 1)
            self.assertEqual(len(resources[0].resource_calendars), 1)
            self.assertEqual(resources[0].resource_calendars[0].calendar_id, self.cal_alice.id)

    def test_round_robin_selection_order(self):
        with SessionLocal() as db:
            svc = SchedulingResourceService(db)
            r_alice = svc.create_resource(
                tenant_id=self.tenant.id,
                name="Alice Agent",
                team="sales",
                priority=1,
            )
            r_bob = svc.create_resource(
                tenant_id=self.tenant.id,
                name="Bob Agent",
                team="sales",
                priority=1,
            )
            svc.assign_calendar_to_resource(
                tenant_id=self.tenant.id,
                resource_id=r_alice.id,
                calendar_id=self.cal_alice.id,
            )
            svc.assign_calendar_to_resource(
                tenant_id=self.tenant.id,
                resource_id=r_bob.id,
                calendar_id=self.cal_bob.id,
            )

            chosen1, cal_id1 = svc.select_resource_round_robin(tenant_id=self.tenant.id, team_name="sales")
            self.assertIsNotNone(chosen1)
            self.assertEqual(chosen1.id, r_alice.id)
            self.assertEqual(cal_id1, "alice@example.com")

            chosen1.last_assigned_at = datetime.now(UTC)
            chosen1.total_assigned_count = 1
            db.commit()

            chosen2, cal_id2 = svc.select_resource_round_robin(tenant_id=self.tenant.id, team_name="sales")
            self.assertIsNotNone(chosen2)
            self.assertEqual(chosen2.id, r_bob.id)
            self.assertEqual(cal_id2, "bob@example.com")

            chosen2.last_assigned_at = datetime.now(UTC) + timedelta(seconds=10)
            chosen2.total_assigned_count = 1
            db.commit()

            chosen3, _ = svc.select_resource_round_robin(tenant_id=self.tenant.id, team_name="sales")
            self.assertIsNotNone(chosen3)
            self.assertEqual(chosen3.id, r_alice.id)

    @patch("app.services.google_calendar_service.GoogleCalendarService.create_event")
    def test_booking_service_uses_round_robin_resource(self, mock_create_event):
        mock_create_event.return_value = {
            "id": "g_event_rr_1",
            "htmlLink": "https://calendar.google.com/event?eid=rr1",
            "hangoutLink": "https://meet.google.com/rr1-meet",
        }

        with SessionLocal() as db:
            svc = SchedulingResourceService(db)
            r_alice = svc.create_resource(
                tenant_id=self.tenant.id,
                name="Alice Specialist",
                team="advisors",
                email="alice@example.com",
            )
            svc.assign_calendar_to_resource(
                tenant_id=self.tenant.id,
                resource_id=r_alice.id,
                calendar_id=self.cal_alice.id,
                is_blocking=True,
                is_destination=True,
            )

            booking_svc = BookingService(db)
            booking = booking_svc.create_lead_booking(
                tenant_id=self.tenant.id,
                lead_id=self.lead_id,
                body=BookingCreateRequest(
                    start="2026-09-18T15:00:00Z",
                    attendee_name="Lead Customer",
                    attendee_email="customer@example.com",
                    attendee_phone="+573001234567",
                    notes="Round robin consultation",
                ),
            )

            self.assertIsNotNone(booking)
            self.assertEqual(booking.status, "accepted")
            self.assertEqual(booking.host_name, "Alice Specialist")

            mock_create_event.assert_called_once()
            call_kwargs = mock_create_event.call_args.kwargs
            self.assertEqual(call_kwargs.get("calendar_id"), "alice@example.com")

            db.refresh(r_alice)
            self.assertEqual(r_alice.total_assigned_count, 1)
            self.assertIsNotNone(r_alice.last_assigned_at)
