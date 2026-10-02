"""Google Calendar connection / calendar / resource administration for the
integrations UI. Returns contract objects, never ORM rows, so the HTTP layer
has nothing to navigate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.scheduling.application.resource_service import SchedulingResourceService
from app.modules.scheduling.domain.contracts import (
    GoogleCalendarConnectionResponse,
    GoogleCalendarSyncResponse,
    SchedulingResourceCalendarAssignRequest,
    SchedulingResourceCalendarResponse,
    SchedulingResourceCreateRequest,
    SchedulingResourceResponse,
    TenantGoogleCalendarResponse,
    TenantGoogleCalendarUpdateRequest,
)
from app.modules.scheduling.domain.errors import GoogleConnectionNotFoundError
from app.modules.scheduling.infrastructure.google.calendar import GoogleCalendarService
from app.modules.scheduling.infrastructure.google.oauth import GoogleCalendarOAuthService
from app.modules.scheduling.infrastructure.models import (
    TenantGoogleCalendar,
    TenantGoogleCalendarConnection,
    TenantSchedulingResource,
    TenantSchedulingResourceCalendar,
)


def calendar_response(c: TenantGoogleCalendar) -> TenantGoogleCalendarResponse:
    return TenantGoogleCalendarResponse(
        id=c.id,
        tenant_id=c.tenant_id,
        connection_id=c.connection_id,
        google_calendar_id=c.google_calendar_id,
        summary=c.summary,
        description=c.description,
        time_zone=c.time_zone,
        is_primary=c.is_primary,
        is_blocking=c.is_blocking,
        is_booking_destination=c.is_booking_destination,
        access_role=c.access_role,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def resource_calendar_response(m: TenantSchedulingResourceCalendar) -> SchedulingResourceCalendarResponse:
    return SchedulingResourceCalendarResponse(
        id=m.id,
        resource_id=m.resource_id,
        calendar_id=m.calendar_id,
        is_blocking=m.is_blocking,
        is_destination=m.is_destination,
        created_at=m.created_at,
    )


def resource_response(r: TenantSchedulingResource, *, with_calendars: bool = True) -> SchedulingResourceResponse:
    return SchedulingResourceResponse(
        id=r.id,
        tenant_id=r.tenant_id,
        name=r.name,
        resource_type=r.resource_type,
        team=r.team,
        email=r.email,
        phone=r.phone,
        priority=r.priority,
        is_active=r.is_active,
        timezone=r.timezone,
        capacity=r.capacity,
        total_assigned_count=r.total_assigned_count,
        last_assigned_at=r.last_assigned_at,
        created_at=r.created_at,
        updated_at=r.updated_at,
        calendars=[resource_calendar_response(c) for c in (r.resource_calendars or [])] if with_calendars else [],
    )


class GoogleCalendarAdmin:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- OAuth ---------------------------------------------------------------
    def connect_url(self, *, tenant_id: str, user_id: str) -> str:
        return GoogleCalendarOAuthService(self.db).build_auth_url(tenant_id=tenant_id, user_id=user_id)

    def complete_oauth(self, *, code: str, state: str) -> GoogleCalendarConnectionResponse:
        """Exchange the code, store the connection and sync its calendars
        (a sync failure never fails the connect). Raises ValueError."""
        oauth = GoogleCalendarOAuthService(self.db)
        state_data = oauth.validate_and_decode_state(state)
        tenant_id = state_data.get("tenant_id")
        user_id = state_data.get("user_id")
        if not tenant_id:
            raise ValueError("State does not contain tenant_id.")

        tokens = oauth.exchange_code_for_tokens(code)
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token") or ""
        expires_at = datetime.now(UTC) + timedelta(seconds=tokens.get("expires_in", 3600))
        email = oauth.fetch_user_email(access_token)

        connection = oauth.store_connection(
            tenant_id=tenant_id,
            user_id=user_id,
            google_account_email=email,
            calendar_id="primary",
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=expires_at,
        )
        try:
            GoogleCalendarService(self.db, oauth).sync_calendars(connection)
        except Exception:
            pass
        return oauth.response(connection)

    # -- Connections ---------------------------------------------------------
    def list_connections(self, tenant_id: str) -> list[GoogleCalendarConnectionResponse]:
        oauth = GoogleCalendarOAuthService(self.db)
        return [oauth.response(c) for c in oauth.list_connections(tenant_id)]

    def disconnect(self, tenant_id: str, connection_id: str) -> GoogleCalendarConnectionResponse:
        oauth = GoogleCalendarOAuthService(self.db)
        return oauth.response(oauth.disconnect_connection(tenant_id, connection_id))

    def delete(self, tenant_id: str, connection_id: str) -> None:
        GoogleCalendarOAuthService(self.db).delete_connection(tenant_id, connection_id)

    def sync(self, tenant_id: str, connection_id: str) -> GoogleCalendarSyncResponse:
        connection = self.db.scalar(
            select(TenantGoogleCalendarConnection).where(
                TenantGoogleCalendarConnection.tenant_id == tenant_id,
                TenantGoogleCalendarConnection.id == connection_id,
            )
        )
        if not connection:
            raise GoogleConnectionNotFoundError()
        calendars = GoogleCalendarService(self.db).sync_calendars(connection)
        return GoogleCalendarSyncResponse(
            connection_id=connection.id,
            synced_count=len(calendars),
            calendars=[calendar_response(c) for c in calendars],
        )

    # -- Calendars -----------------------------------------------------------
    def list_calendars(self, tenant_id: str, connection_id: str | None) -> list[TenantGoogleCalendarResponse]:
        calendars = GoogleCalendarService(self.db).list_tenant_calendars(tenant_id, connection_id=connection_id)
        return [calendar_response(c) for c in calendars]

    def update_calendar(
        self, tenant_id: str, calendar_id: str, body: TenantGoogleCalendarUpdateRequest
    ) -> TenantGoogleCalendarResponse:
        cal = GoogleCalendarService(self.db).update_calendar_settings(
            tenant_id=tenant_id,
            calendar_id=calendar_id,
            is_blocking=body.is_blocking,
            is_booking_destination=body.is_booking_destination,
        )
        return calendar_response(cal)

    # -- Resources -----------------------------------------------------------
    def create_resource(self, tenant_id: str, body: SchedulingResourceCreateRequest) -> SchedulingResourceResponse:
        resource = SchedulingResourceService(self.db).create_resource(
            tenant_id=tenant_id,
            name=body.name,
            resource_type=body.resource_type,
            team=body.team,
            email=body.email,
            phone=body.phone,
            priority=body.priority,
            timezone=body.timezone,
            capacity=body.capacity,
            working_hours_json=body.working_hours,
        )
        return resource_response(resource, with_calendars=False)

    def list_resources(self, tenant_id: str, team: str | None) -> list[SchedulingResourceResponse]:
        return [
            resource_response(r)
            for r in SchedulingResourceService(self.db).list_resources(tenant_id=tenant_id, team=team)
        ]

    def assign_calendar(
        self, tenant_id: str, resource_id: str, body: SchedulingResourceCalendarAssignRequest
    ) -> SchedulingResourceCalendarResponse:
        mapping = SchedulingResourceService(self.db).assign_calendar_to_resource(
            tenant_id=tenant_id,
            resource_id=resource_id,
            calendar_id=body.calendar_id,
            is_blocking=body.is_blocking,
            is_destination=body.is_destination,
        )
        return resource_calendar_response(mapping)
