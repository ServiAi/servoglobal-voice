from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.core.config import settings
from app.models.integrations import TenantGoogleCalendar, TenantGoogleCalendarConnection
from app.services.google_calendar_oauth_service import GoogleCalendarOAuthService
from app.services.google_calendar_service import GoogleCalendarService


class GoogleCalendarSyncTests(Integration2ATestCase):
    def setUp(self):
        super().setUp()
        settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID = "test_client_id"
        settings.GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET = "test_client_secret"
        settings.GOOGLE_CALENDAR_REDIRECT_URI = "https://example.com/callback"

        with SessionLocal() as db:
            service = GoogleCalendarOAuthService(db)
            self.connection = service.store_connection(
                tenant_id=self.tenant.id,
                user_id=self.user.id,
                google_account_email="test@example.com",
                access_token="test_token",
                refresh_token="test_refresh",
                token_expires_at=datetime.now(UTC) + timedelta(hours=1),
            )

    @patch("httpx.get")
    def test_sync_calendars_creates_and_updates_database(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "id": "primary",
                    "summary": "Calendario Personal",
                    "description": "Citas personales y trabajo",
                    "timeZone": "America/Bogota",
                    "primary": True,
                    "accessRole": "owner",
                },
                {
                    "id": "team_ops@group.calendar.google.com",
                    "summary": "Operaciones y Guardias",
                    "description": "Turnos rotativos",
                    "timeZone": "America/Bogota",
                    "primary": False,
                    "accessRole": "reader",
                },
            ]
        }
        mock_get.return_value = mock_resp

        with SessionLocal() as db:
            service = GoogleCalendarService(db)
            conn = db.get(TenantGoogleCalendarConnection, self.connection.id)
            cals = service.sync_calendars(conn)

            self.assertEqual(len(cals), 2)
            primary_cal = next(c for c in cals if c.google_calendar_id == "primary")
            self.assertTrue(primary_cal.is_primary)
            self.assertTrue(primary_cal.is_blocking)
            self.assertTrue(primary_cal.is_booking_destination)

            ops_cal = next(c for c in cals if c.google_calendar_id == "team_ops@group.calendar.google.com")
            self.assertFalse(ops_cal.is_primary)
            self.assertTrue(ops_cal.is_blocking)
            self.assertFalse(ops_cal.is_booking_destination)

    @patch("httpx.get")
    def test_sync_and_list_endpoints(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {"id": "primary", "summary": "Principal", "primary": True, "accessRole": "owner"}
            ]
        }
        mock_get.return_value = mock_resp

        # Trigger sync endpoint
        sync_res = self.client.post(f"/api/v1/integrations/google-calendar/connections/{self.connection.id}/sync")
        self.assertEqual(sync_res.status_code, 200)
        sync_payload = sync_res.json()
        self.assertEqual(sync_payload["synced_count"], 1)
        cal_id = sync_payload["calendars"][0]["id"]

        # List endpoint
        list_res = self.client.get("/api/v1/integrations/google-calendar/calendars")
        self.assertEqual(list_res.status_code, 200)
        list_payload = list_res.json()
        self.assertEqual(len(list_payload), 1)
        self.assertEqual(list_payload[0]["google_calendar_id"], "primary")

        # Patch endpoint to toggle blocking
        patch_res = self.client.patch(
            f"/api/v1/integrations/google-calendar/calendars/{cal_id}",
            json={"is_blocking": False},
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertFalse(patch_res.json()["is_blocking"])
