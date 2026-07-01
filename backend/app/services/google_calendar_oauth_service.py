from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.integrations import TenantGoogleCalendarConnection
from app.schemas.integrations import GoogleCalendarConnectionResponse
from app.services.secret_manager_service import SecretManager

GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class GoogleCalendarOAuthService:
    def __init__(self, db: Session, secret_manager: SecretManager | None = None) -> None:
        self.db = db
        self.secret_manager = secret_manager or SecretManager()

    def build_auth_url(self, *, state: str) -> str:
        if not settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID or not settings.GOOGLE_CALENDAR_REDIRECT_URI:
            raise ValueError("Google Calendar OAuth is not configured.")
        params = {
            "client_id": settings.GOOGLE_CALENDAR_OAUTH_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_CALENDAR_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(GOOGLE_CALENDAR_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str) -> dict:
        raise ValueError("Google Calendar token exchange requires outbound OAuth setup.")

    def refresh_access_token(self, connection: TenantGoogleCalendarConnection) -> str:
        raise ValueError("Google Calendar token refresh is prepared for Sprint 2B.")

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
