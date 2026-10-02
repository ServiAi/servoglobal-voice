"""Cal.com / Google Calendar / scheduling-resource endpoints of the integrations
UI. Same URLs (``/api/v1/integrations/...``), roles and payloads as before; they
live here because the operations belong to Scheduling. Handlers never touch ORM
rows: the application layer hands back contract objects."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.modules.integrations.public import IntegrationsFacade
from app.modules.scheduling.application.google_admin import GoogleCalendarAdmin
from app.modules.scheduling.domain.contracts import (
    BookingConfigRequest,
    BookingConfigResponse,
    CalComTestResponse,
    GoogleCalendarConnectionResponse,
    GoogleCalendarConnectUrlResponse,
    GoogleCalendarSyncResponse,
    SchedulingResourceCalendarAssignRequest,
    SchedulingResourceCalendarResponse,
    SchedulingResourceCreateRequest,
    SchedulingResourceResponse,
    TenantGoogleCalendarResponse,
    TenantGoogleCalendarUpdateRequest,
)
from app.modules.scheduling.domain.errors import GoogleConnectionNotFoundError
from app.modules.scheduling.public import SchedulingFacade

router = APIRouter(prefix="/api/v1/integrations", tags=["Integrations"])

_READ_ROLES = ["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"]
_WRITE_ROLES = ["platform_admin", "tenant_admin"]


def _require_enabled(provider: str, roles: list[str]):
    role_dependency = require_roles(roles)

    def dependency(
        context: AuthContext = Depends(role_dependency),
        db: Session = Depends(get_db),
    ) -> AuthContext:
        if not IntegrationsFacade(db).is_enabled(context.tenant.id, provider):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration is not enabled for this tenant.")
        return context

    return dependency


# --------------------------------------------------------------------------
# Cal.com
# --------------------------------------------------------------------------
@router.get("/booking/config", response_model=BookingConfigResponse)
def get_booking_config(
    context: AuthContext = Depends(_require_enabled("calcom", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return SchedulingFacade(db).get_booking_config(context.tenant.id)


@router.post("/calcom/config", response_model=BookingConfigResponse)
def configure_calcom(
    body: BookingConfigRequest,
    context: AuthContext = Depends(_require_enabled("calcom", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return SchedulingFacade(db).configure_calcom(context.tenant.id, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/calcom/test", response_model=CalComTestResponse)
def test_calcom(
    context: AuthContext = Depends(_require_enabled("calcom", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        result, error = SchedulingFacade(db).test_calcom(context.tenant.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result != "active":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error or "Cal.com test failed.")
    return CalComTestResponse(status=result)


@router.get("/calcom/slots")
def get_calcom_slots(
    date: str,
    jornada: str | None = None,
    reference_datetime: str | None = None,
    context: AuthContext = Depends(_require_enabled("calcom", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return SchedulingFacade(db).get_available_slots(
            tenant_id=context.tenant.id,
            date_input=date,
            jornada=jornada,
            reference_datetime=reference_datetime,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# --------------------------------------------------------------------------
# Google Calendar
# --------------------------------------------------------------------------
@router.get("/google-calendar/connect-url", response_model=GoogleCalendarConnectUrlResponse)
def google_calendar_connect_url(
    context: AuthContext = Depends(_require_enabled("google_calendar", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        url = GoogleCalendarAdmin(db).connect_url(tenant_id=context.tenant.id, user_id=context.user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return GoogleCalendarConnectUrlResponse(url=url)


@router.get("/google-calendar/callback", response_model=GoogleCalendarConnectionResponse)
def google_calendar_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    redirect: bool | None = None,
    db: Session = Depends(get_db),
) -> Any:
    # Determine whether to redirect: if redirect param is True, or if browser navigation (accept text/html)
    accept = request.headers.get("accept", "")
    should_redirect = redirect if redirect is not None else ("text/html" in accept)
    frontend_base = (
        settings.GOOGLE_CALENDAR_FRONTEND_REDIRECT_URL.rstrip("/")
        if settings.GOOGLE_CALENDAR_FRONTEND_REDIRECT_URL
        else "https://www.serviglobal-ia.com/es/integrations/google-calendar"
    )

    if error:
        if should_redirect:
            return RedirectResponse(url=f"{frontend_base}?status=error&detail={error}", status_code=302)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Google OAuth error: {error}")
    if not code or not state:
        if should_redirect:
            return RedirectResponse(url=f"{frontend_base}?status=error&detail=Missing+code+or+state", status_code=302)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code or state parameter.")

    try:
        connection = GoogleCalendarAdmin(db).complete_oauth(code=code, state=state)
    except ValueError as exc:
        if should_redirect:
            return RedirectResponse(url=f"{frontend_base}?status=error&detail={str(exc)}", status_code=302)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    if should_redirect:
        return RedirectResponse(url=f"{frontend_base}?status=connected", status_code=302)

    return connection


@router.get("/google-calendar/connections", response_model=list[GoogleCalendarConnectionResponse])
def list_google_calendar_connections(
    context: AuthContext = Depends(_require_enabled("google_calendar", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return GoogleCalendarAdmin(db).list_connections(context.tenant.id)


@router.post("/google-calendar/disconnect", response_model=GoogleCalendarConnectionResponse)
def disconnect_google_calendar(
    connection_id: str,
    context: AuthContext = Depends(_require_enabled("google_calendar", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return GoogleCalendarAdmin(db).disconnect(context.tenant.id, connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/google-calendar/connections/{connection_id}", response_model=dict[str, Any])
def delete_google_calendar_connection(
    connection_id: str,
    context: AuthContext = Depends(_require_enabled("google_calendar", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        GoogleCalendarAdmin(db).delete(context.tenant.id, connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"deleted": True, "connection_id": connection_id}


@router.post("/google-calendar/connections/{connection_id}/sync", response_model=GoogleCalendarSyncResponse)
def sync_google_calendar_connection(
    connection_id: str,
    context: AuthContext = Depends(_require_enabled("google_calendar", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return GoogleCalendarAdmin(db).sync(context.tenant.id, connection_id)
    except GoogleConnectionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/google-calendar/calendars", response_model=list[TenantGoogleCalendarResponse])
def list_google_calendars(
    connection_id: str | None = None,
    context: AuthContext = Depends(_require_enabled("google_calendar", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return GoogleCalendarAdmin(db).list_calendars(context.tenant.id, connection_id)


@router.patch("/google-calendar/calendars/{calendar_id}", response_model=TenantGoogleCalendarResponse)
def update_google_calendar(
    calendar_id: str,
    body: TenantGoogleCalendarUpdateRequest,
    context: AuthContext = Depends(_require_enabled("google_calendar", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return GoogleCalendarAdmin(db).update_calendar(context.tenant.id, calendar_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# --------------------------------------------------------------------------
# Scheduling resources (integrations flavour)
# --------------------------------------------------------------------------
@router.post("/scheduling/resources", response_model=SchedulingResourceResponse)
def create_scheduling_resource(
    body: SchedulingResourceCreateRequest,
    context: AuthContext = Depends(_require_enabled("google_calendar", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return GoogleCalendarAdmin(db).create_resource(context.tenant.id, body)


@router.get("/scheduling/resources", response_model=list[SchedulingResourceResponse])
def list_scheduling_resources(
    team: str | None = None,
    context: AuthContext = Depends(_require_enabled("google_calendar", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return GoogleCalendarAdmin(db).list_resources(context.tenant.id, team)


@router.post("/scheduling/resources/{resource_id}/calendars", response_model=SchedulingResourceCalendarResponse)
def assign_calendar_to_resource(
    resource_id: str,
    body: SchedulingResourceCalendarAssignRequest,
    context: AuthContext = Depends(_require_enabled("google_calendar", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return GoogleCalendarAdmin(db).assign_calendar(context.tenant.id, resource_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
