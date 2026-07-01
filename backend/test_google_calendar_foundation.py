from __future__ import annotations

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.integrations import TenantGoogleCalendarConnection
from app.services.google_calendar_oauth_service import GoogleCalendarOAuthService
from app.services.google_calendar_service import GoogleCalendarService


class GoogleCalendarFoundationTests(Integration2ATestCase):
    def test_google_calendar_tokens_are_encrypted_and_not_exposed(self):
        with SessionLocal() as db:
            service = GoogleCalendarOAuthService(db)
            connection = service.store_connection(
                tenant_id=self.tenant.id,
                user_id=self.user.id,
                google_account_email="calendar@example.com",
                access_token="access_secret",
                refresh_token="refresh_secret",
            )
            payload = service.response(connection).model_dump()

            stored = db.scalar(
                select(TenantGoogleCalendarConnection).where(TenantGoogleCalendarConnection.id == connection.id)
            )

        self.assertTrue(payload["has_tokens"])
        self.assertNotIn("access_token", payload)
        self.assertNotIn("refresh_token", payload)
        self.assertNotIn("access_secret", stored.access_token_encrypted)
        self.assertNotIn("refresh_secret", stored.refresh_token_encrypted)

    def test_google_calendar_disconnect_returns_updated_connection(self):
        with SessionLocal() as db:
            connection = GoogleCalendarOAuthService(db).store_connection(
                tenant_id=self.tenant.id,
                user_id=self.user.id,
                google_account_email="calendar@example.com",
                access_token="access_secret",
                refresh_token="refresh_secret",
            )

        response = self.client.post(f"/api/v1/integrations/google-calendar/disconnect?connection_id={connection.id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], connection.id)
        self.assertEqual(payload["status"], "disconnected")
        self.assertTrue(payload["has_tokens"])

    def test_google_events_insert_is_explicitly_disabled_in_foundation(self):
        service = GoogleCalendarService()

        with self.assertRaisesRegex(ValueError, "not enabled"):
            service.create_event(connection=None, payload={})
