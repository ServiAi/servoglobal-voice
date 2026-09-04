import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import re

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.integrations import TenantGoogleCalendarConnection
from app.schemas.integrations import GoogleCalendarConnectionResponse
from app.services.secret_manager_service import SecretManager


def sanitize_google_calendar_error(value: str) -> str:
    cleaned = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [redacted]", value or "", flags=re.IGNORECASE)
    cleaned = re.sub(r"(access_token|refresh_token|client_secret)[^,\s}]*", r"\1=[redacted]", cleaned, flags=re.IGNORECASE)
    return cleaned[:300]

GOOGLE_CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]


class GoogleCalendarOAuthService:
    def __init__(self, db: Session, secret_manager: SecretManager | None = None) -> None:
        self.db = db
        self.secret_manager = secret_manager or SecretManager()

    def generate_secure_state(self, tenant_id: str, user_id: str | None = None) -> str:
        payload = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "ts": int(time.time()),
            "nonce": secrets.token_hex(8),
        }
        raw_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8").rstrip("=")
        key = self.secret_manager._resolve_key().encode("utf-8")
        sig = hmac.new(key, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload_b64}.{sig}"

    def validate_and_decode_state(self, state: str, max_age_seconds: int = 900) -> dict:
        if not state:
            raise ValueError("OAuth state is required.")
        # Legacy fallback if state is just "tenant_id:user_id"
        if "." not in state and ":" in state:
            parts = state.split(":", 1)
            return {"tenant_id": parts[0], "user_id": parts[1] if len(parts) > 1 else None}

        parts = state.split(".", 1)
        if len(parts) != 2:
            raise ValueError("Malformed OAuth state parameter.")
        payload_b64, signature = parts
        key = self.secret_manager._resolve_key().encode("utf-8")
        expected_sig = hmac.new(key, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            raise ValueError("Invalid OAuth state signature.")

        padding = "=" * (-len(payload_b64) % 4)
        try:
            raw_bytes = base64.urlsafe_b64decode((payload_b64 + padding).encode("utf-8"))
            payload = json.loads(raw_bytes.decode("utf-8"))
        except Exception as exc:
            raise ValueError("Corrupted OAuth state payload.") from exc

        ts = payload.get("ts", 0)
        if time.time() - ts > max_age_seconds:
            raise ValueError("OAuth state has expired. Please try connecting again.")

        return {
            "tenant_id": payload.get("tenant_id"),
            "user_id": payload.get("user_id"),
        }

    def build_auth_url(self, *, state: str | None = None, tenant_id: str | None = None, user_id: str | None = None) -> str:
        if not settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID or not settings.GOOGLE_CALENDAR_REDIRECT_URI:
            raise ValueError("Google Calendar OAuth is not configured.")
        final_state = state or self.generate_secure_state(tenant_id=tenant_id or "", user_id=user_id)
        params = {
            "client_id": settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_CALENDAR_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(GOOGLE_CALENDAR_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": final_state,
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str) -> dict:
        if not settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID or not settings.GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET or not settings.GOOGLE_CALENDAR_REDIRECT_URI:
            raise ValueError("Google Calendar OAuth credentials are not configured.")
        data = {
            "code": code,
            "client_id": settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_CALENDAR_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        try:
            response = httpx.post("https://oauth2.googleapis.com/token", data=data, timeout=15.0)
        except Exception as exc:
            raise ValueError(f"Failed to connect to Google OAuth server: {sanitize_google_calendar_error(str(exc))}") from exc

        if response.status_code != 200:
            raise ValueError(f"Google token exchange failed: {sanitize_google_calendar_error(response.text)}")

        return response.json()

    def refresh_access_token(self, connection: TenantGoogleCalendarConnection) -> str:
        if not connection.refresh_token_encrypted:
            raise ValueError("No refresh token available for this Google Calendar connection.")
        if not settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID or not settings.GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET:
            raise ValueError("Google Calendar OAuth credentials are not configured.")

        refresh_token = self.secret_manager.decrypt_secret(connection.refresh_token_encrypted)
        data = {
            "client_id": settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        try:
            response = httpx.post("https://oauth2.googleapis.com/token", data=data, timeout=15.0)
        except Exception as exc:
            raise ValueError(f"Failed to refresh Google token: {sanitize_google_calendar_error(str(exc))}") from exc

        if response.status_code != 200:
            connection.status = "error"
            connection.last_error_message = sanitize_google_calendar_error(response.text)
            self.db.commit()
            raise ValueError(f"Google token refresh failed: {connection.last_error_message}")

        payload = response.json()
        new_access_token = payload.get("access_token")
        if not new_access_token:
            raise ValueError("Google OAuth refresh response did not contain access_token.")

        expires_in = payload.get("expires_in", 3600)
        connection.access_token_encrypted = self.secret_manager.encrypt_secret(new_access_token)
        connection.token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        if "refresh_token" in payload and payload["refresh_token"]:
            connection.refresh_token_encrypted = self.secret_manager.encrypt_secret(payload["refresh_token"])
        connection.last_error_message = None
        connection.status = "connected"
        self.db.commit()
        self.db.refresh(connection)
        return new_access_token

    def get_valid_access_token(self, connection: TenantGoogleCalendarConnection) -> str:
        now = datetime.now(UTC)
        token_expires = connection.token_expires_at
        if token_expires is not None and token_expires.tzinfo is None:
            token_expires = token_expires.replace(tzinfo=UTC)

        needs_refresh = (
            token_expires is None
            or token_expires <= now + timedelta(minutes=5)
        )
        if needs_refresh and connection.refresh_token_encrypted:
            try:
                return self.refresh_access_token(connection)
            except Exception:
                if token_expires and token_expires > now and connection.access_token_encrypted:
                    return self.secret_manager.decrypt_secret(connection.access_token_encrypted)
                raise
        if not connection.access_token_encrypted:
            raise ValueError("No access token available for this Google Calendar connection.")
        return self.secret_manager.decrypt_secret(connection.access_token_encrypted)

    def fetch_user_email(self, access_token: str) -> str | None:
        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            resp = httpx.get("https://www.googleapis.com/oauth2/v2/userinfo", headers=headers, timeout=10.0)
            if resp.status_code == 200:
                return resp.json().get("email")
        except Exception:
            pass
        return None

    def store_connection(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        google_account_email: str | None,
        calendar_id: str = "primary",
        calendar_summary: str | None = None,
        access_token: str,
        refresh_token: str,
        token_expires_at: datetime | None = None,
        scopes: list[str] | None = None,
    ) -> TenantGoogleCalendarConnection:
        connection = TenantGoogleCalendarConnection(
            tenant_id=tenant_id,
            user_id=user_id,
            status="connected",
            google_account_email=google_account_email,
            calendar_id=calendar_id,
            calendar_summary=calendar_summary,
            access_token_encrypted=self.secret_manager.encrypt_secret(access_token),
            refresh_token_encrypted=self.secret_manager.encrypt_secret(refresh_token),
            token_expires_at=token_expires_at,
            scopes_json=scopes or GOOGLE_CALENDAR_SCOPES,
        )
        self.db.add(connection)
        self.db.commit()
        self.db.refresh(connection)
        return connection

    def list_connections(self, tenant_id: str) -> list[TenantGoogleCalendarConnection]:
        return list(
            self.db.scalars(
                select(TenantGoogleCalendarConnection)
                .where(TenantGoogleCalendarConnection.tenant_id == tenant_id)
                .order_by(TenantGoogleCalendarConnection.created_at.desc())
            ).all()
        )

    def disconnect_connection(self, tenant_id: str, connection_id: str) -> TenantGoogleCalendarConnection:
        connection = self.db.scalar(
            select(TenantGoogleCalendarConnection).where(
                TenantGoogleCalendarConnection.tenant_id == tenant_id,
                TenantGoogleCalendarConnection.id == connection_id,
            )
        )
        if connection is None:
            raise ValueError("Google Calendar connection not found.")
        connection.status = "disconnected"
        self.db.commit()
        self.db.refresh(connection)
        return connection

    def response(self, connection: TenantGoogleCalendarConnection) -> GoogleCalendarConnectionResponse:
        return GoogleCalendarConnectionResponse(
            id=connection.id,
            status=connection.status,
            google_account_email=connection.google_account_email,
            calendar_id=connection.calendar_id,
            calendar_summary=connection.calendar_summary,
            scopes=list(connection.scopes_json or []),
            last_sync_at=connection.last_sync_at,
            last_error_message=connection.last_error_message,
            has_tokens=bool(connection.access_token_encrypted and connection.refresh_token_encrypted),
        )
