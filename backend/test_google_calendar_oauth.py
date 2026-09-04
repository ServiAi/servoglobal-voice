from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.core.config import settings
from app.models.integrations import TenantGoogleCalendarConnection
from app.services.google_calendar_oauth_service import GoogleCalendarOAuthService


class GoogleCalendarOAuthTests(Integration2ATestCase):
    def setUp(self):
        super().setUp()
        settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID = "test_client_id"
        settings.GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET = "test_client_secret"
        settings.GOOGLE_CALENDAR_REDIRECT_URI = "https://example.com/callback"

    def test_secure_state_generation_and_validation(self):
        with SessionLocal() as db:
            service = GoogleCalendarOAuthService(db)
            state = service.generate_secure_state(tenant_id=self.tenant.id, user_id=self.user.id)
            decoded = service.validate_and_decode_state(state)

            self.assertEqual(decoded["tenant_id"], self.tenant.id)
            self.assertEqual(decoded["user_id"], self.user.id)

    def test_state_tampering_is_rejected(self):
        with SessionLocal() as db:
            service = GoogleCalendarOAuthService(db)
            state = service.generate_secure_state(tenant_id=self.tenant.id, user_id=self.user.id)
            payload, sig = state.split(".", 1)
            tampered_state = f"{payload}.tampered_signature"

            with self.assertRaisesRegex(ValueError, "Invalid OAuth state signature"):
                service.validate_and_decode_state(tampered_state)

    def test_expired_state_is_rejected(self):
        with SessionLocal() as db:
            service = GoogleCalendarOAuthService(db)
            state = service.generate_secure_state(tenant_id=self.tenant.id, user_id=self.user.id)
            time.sleep(0.01)
            with self.assertRaisesRegex(ValueError, "expired"):
                service.validate_and_decode_state(state, max_age_seconds=0)

    @patch("httpx.post")
    def test_token_exchange_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "mock_access_123",
            "refresh_token": "mock_refresh_456",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_post.return_value = mock_response

        with SessionLocal() as db:
            service = GoogleCalendarOAuthService(db)
            tokens = service.exchange_code_for_tokens("test_code_abc")

            self.assertEqual(tokens["access_token"], "mock_access_123")
            self.assertEqual(tokens["refresh_token"], "mock_refresh_456")

    @patch("httpx.post")
    def test_token_refresh_updates_connection(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_refreshed_access",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        with SessionLocal() as db:
            service = GoogleCalendarOAuthService(db)
            conn = service.store_connection(
                tenant_id=self.tenant.id,
                user_id=self.user.id,
                google_account_email="tenant@example.com",
                access_token="old_access",
                refresh_token="my_refresh_token",
                token_expires_at=datetime.now(UTC) - timedelta(minutes=10),
            )

            new_token = service.refresh_access_token(conn)
            self.assertEqual(new_token, "new_refreshed_access")

            db.refresh(conn)
            expires_at = conn.token_expires_at
            if expires_at is not None and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            self.assertGreater(expires_at, datetime.now(UTC))
            plain_access = service.secret_manager.decrypt_secret(conn.access_token_encrypted)
            self.assertEqual(plain_access, "new_refreshed_access")

    @patch("httpx.get")
    @patch("httpx.post")
    def test_oauth_callback_endpoint(self, mock_post, mock_get):
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "access_token": "cb_access_token",
            "refresh_token": "cb_refresh_token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_post_resp

        mock_userinfo = MagicMock()
        mock_userinfo.status_code = 200
        mock_userinfo.json.return_value = {"email": "oauth_user@example.com"}

        mock_cal_list = MagicMock()
        mock_cal_list.status_code = 200
        mock_cal_list.json.return_value = {
            "items": [
                {"id": "primary", "summary": "Principal", "primary": True, "accessRole": "owner"}
            ]
        }

        def side_effect(url, *args, **kwargs):
            if "userinfo" in url:
                return mock_userinfo
            return mock_cal_list

        mock_get.side_effect = side_effect

        with SessionLocal() as db:
            service = GoogleCalendarOAuthService(db)
            state = service.generate_secure_state(tenant_id=self.tenant.id, user_id=self.user.id)

        response = self.client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "connected")
        self.assertEqual(payload["google_account_email"], "oauth_user@example.com")
        self.assertTrue(payload["has_tokens"])
