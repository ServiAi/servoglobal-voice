from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.db.session import get_db
from app.models.integrations import TenantEmailTemplate, TenantGoogleCalendarConnection, TenantWhatsAppTemplate
from app.schemas.integrations import (
    BookingConfigRequest,
    BookingConfigResponse,
    CalComTestResponse,
    ChatwootAgentInviteRequest,
    ChatwootAgentSummary,
    ChatwootAgentUpdateRequest,
    ChatwootConfigRequest,
    ChatwootConfigResponse,
    ChatwootInboxCreateRequest,
    ChatwootInboxSummary,
    ChatwootInboxUpdateRequest,
    ChatwootProvisionRequest,
    ChatwootTeamCreateRequest,
    ChatwootTeamSummary,
    ChatwootTeamUpdateRequest,
    ChatwootTestResponse,
    EmailTemplateItem,
    EmailTemplateUpsertRequest,
    GoogleCalendarConnectionResponse,
    GoogleCalendarConnectUrlResponse,
    GoogleCalendarSyncResponse,
    TenantGoogleCalendarResponse,
    TenantGoogleCalendarUpdateRequest,
    SchedulingResourceCalendarAssignRequest,
    SchedulingResourceCalendarResponse,
    SchedulingResourceCreateRequest,
    SchedulingResourceResponse,
    IntegrationAvailabilityResponse,
    IntegrationCatalogStatusResponse,
    ResendIntegrationConfigRequest,
    ResendIntegrationConfigResponse,
    ResendTestEmailRequest,
    ResendTestEmailResponse,
    WhatsAppConfigRequest,
    WhatsAppConfigResponse,
    WhatsAppTemplateCreateRequest,
    WhatsAppTemplateDetailResponse,
    WhatsAppTemplatePreviewResponse,
    WhatsAppTemplateResponse,
    WhatsAppTemplateSubmitResponse,
    WhatsAppTemplateSyncResponse,
    WhatsAppTemplateUpdateRequest,
    WhatsAppTestMessageRequest,
    WhatsAppTestMessageResponse,
    WhatsAppTestRequest,
    WhatsAppTestResponse,
    VoiceProviderConfigRequest,
    VoiceProviderConfigResponse,
    VoiceAgentConfigRequest,
    VoiceAgentConfigResponse,
    VoiceCallActionRequest,
    VoiceCallActionResponse,
    VoiceCallResponse,
)
from app.core.config import settings
from app.services.booking_config_service import BookingConfigService
from app.services.booking_service import BookingService
from app.services.chatwoot_client import ChatwootClientError, sanitize_chatwoot_error
from app.services.chatwoot_config_service import ChatwootAccountConflictError, ChatwootConfigService
from app.services.email_config_service import EmailConfigService
from app.services.email_send_service import EmailSendService
from app.services.email_template_service import EmailTemplateService
from app.services.google_calendar_oauth_service import GoogleCalendarOAuthService
from app.services.google_calendar_service import GoogleCalendarService
from app.services.scheduling_resource_service import SchedulingResourceService
from app.services.voice_config_service import VoiceConfigService
from app.services.voice_agent_service import VoiceAgentService
from app.services.integration_event_service import IntegrationEventService
from app.services.integration_service import IntegrationService
from app.services.whatsapp_config_service import WhatsAppConfigService
from app.services.whatsapp_message_service import WhatsAppMessageService
from app.services.whatsapp_template_service import WhatsAppTemplateService

router = APIRouter(prefix="/api/v1/integrations", tags=["Integrations"])

_READ_ROLES = ["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"]
_WRITE_ROLES = ["platform_admin", "tenant_admin"]


def require_enabled_integration(provider: str, roles: list[str]):
    role_dependency = require_roles(roles)

    def dependency(
        context: AuthContext = Depends(role_dependency),
        db: Session = Depends(get_db),
    ) -> AuthContext:
        if not IntegrationService(db).is_enabled(context.tenant.id, provider):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration is not enabled for this tenant.")
        return context

    return dependency


def _resend_response(
    integration_service: IntegrationService,
    tenant_id: str,
    config_service: EmailConfigService,
) -> ResendIntegrationConfigResponse:
    integration = integration_service.get_integration(tenant_id, "resend")
    config = config_service.get_config(tenant_id, "resend")
    return ResendIntegrationConfigResponse(
        provider="resend",
        status=(config.status if config else integration.status if integration else "inactive"),
        sender_name=config.sender_name if config else None,
        sender_email=config.sender_email if config else None,
        reply_to=config.reply_to if config else None,
        default_domain=config.default_domain if config else None,
        has_secret=integration_service.has_secret(integration),
        last_health_check_at=config.last_health_check_at if config else None,
        last_error_message=(config.last_error_message if config else integration.last_error_message if integration else None),
    )


def _catalog_status(*, configured: bool, provider_status: str | None, has_error: bool) -> str:
    if has_error or provider_status in {"error", "failed"}:
        return "error"
    if not configured:
        return "not_configured"
    if provider_status in {"active", "connected"}:
        return "active"
    return "configured"


@router.get("", response_model=list[ResendIntegrationConfigResponse])
def list_integrations(
    context: AuthContext = Depends(require_roles(_READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    integration_service = IntegrationService(db)
    return (
        [_resend_response(integration_service, context.tenant.id, EmailConfigService(db))]
        if integration_service.is_enabled(context.tenant.id, "resend")
        else []
    )


@router.get("/availability", response_model=list[IntegrationAvailabilityResponse])
def list_integration_availability(
    context: AuthContext = Depends(require_roles(_READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return IntegrationService(db).list_availability(context.tenant.id)


def _integration_catalog_statuses(
    db: Session,
    tenant_id: str,
    providers: set[str] | None = None,
) -> list[IntegrationCatalogStatusResponse]:
    integration_service = IntegrationService(db)
    selected = providers if providers is not None else {
        item["provider"]
        for item in integration_service.list_availability(tenant_id)
        if item["enabled"]
    }
    statuses: dict[str, str] = {}

    if "resend" in selected:
        integration = integration_service.get_integration(tenant_id, "resend")
        config = EmailConfigService(db).get_config(tenant_id, "resend")
        statuses["resend"] = _catalog_status(
            configured=bool(integration or config),
            provider_status=config.status if config else integration.status if integration else None,
            has_error=bool(config.last_error_message if config else integration.last_error_message if integration else None),
        )

    if "whatsapp" in selected:
        config = WhatsAppConfigService(db).get_config(tenant_id)
        statuses["whatsapp"] = _catalog_status(
            configured=config is not None,
            provider_status=config.status if config else None,
            has_error=bool(config and config.last_error_message),
        )

    if "voice" in selected:
        config = VoiceConfigService(db).get_provider_config(tenant_id)
        statuses["voice"] = _catalog_status(
            configured=config is not None,
            provider_status=config.status if config else None,
            has_error=bool(config and config.last_error_message),
        )

    if "calcom" in selected:
        config = BookingConfigService(db).get_config(tenant_id)
        statuses["calcom"] = _catalog_status(
            configured=config is not None,
            provider_status=config.status if config else None,
            has_error=bool(config and config.last_error_message),
        )

    if "google_calendar" in selected:
        connections = GoogleCalendarOAuthService(db).list_connections(tenant_id)
        statuses["google_calendar"] = _catalog_status(
            configured=bool(connections),
            provider_status="connected" if any(item.status == "connected" for item in connections) else None,
            has_error=any(bool(item.last_error_message) or item.status in {"error", "failed"} for item in connections),
        )

    if "chatwoot" in selected:
        config = ChatwootConfigService(db).get_config(tenant_id)
        statuses["chatwoot"] = _catalog_status(
            configured=config is not None,
            provider_status=config.status if config else None,
            has_error=bool(config and config.last_error_message),
        )

    return [
        IntegrationCatalogStatusResponse(provider=provider, status=statuses.get(provider, "not_configured"))
        for provider in integration_service.supported_providers
        if provider in selected
    ]


@router.get("/statuses", response_model=list[IntegrationCatalogStatusResponse])
def list_integration_catalog_statuses(
    context: AuthContext = Depends(require_roles(_READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return _integration_catalog_statuses(db, context.tenant.id)


@router.get("/booking/config", response_model=BookingConfigResponse)
def get_booking_config(
    context: AuthContext = Depends(require_enabled_integration("calcom", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return BookingConfigService(db).get_config_response(context.tenant.id)


@router.post("/calcom/config", response_model=BookingConfigResponse)
def configure_calcom(
    body: BookingConfigRequest,
    context: AuthContext = Depends(require_enabled_integration("calcom", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        config = BookingConfigService(db).upsert_calcom_config(context.tenant.id, body)
        IntegrationEventService(db).record_event(
            tenant_id=context.tenant.id,
            provider="calcom",
            event_type="config_updated",
            status="success",
            resource_type="config",
            resource_id=config.id,
            metadata={"has_secret": bool(config.cal_api_key_encrypted), "calendar_mode": config.calendar_mode},
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return BookingConfigService(db).get_config_response(context.tenant.id)


@router.post("/calcom/test", response_model=CalComTestResponse)
def test_calcom(
    context: AuthContext = Depends(require_enabled_integration("calcom", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        result, error = BookingConfigService(db).test_connection(context.tenant.id)
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
    context: AuthContext = Depends(require_enabled_integration("calcom", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return BookingService(db).get_available_slots_for_tenant(
            tenant_id=context.tenant.id,
            date_input=date,
            jornada=jornada,
            reference_datetime=reference_datetime,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/google-calendar/connect-url", response_model=GoogleCalendarConnectUrlResponse)
def google_calendar_connect_url(
    context: AuthContext = Depends(require_enabled_integration("google_calendar", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        url = GoogleCalendarOAuthService(db).build_auth_url(tenant_id=context.tenant.id, user_id=context.user.id)
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

    oauth_service = GoogleCalendarOAuthService(db)
    try:
        state_data = oauth_service.validate_and_decode_state(state)
        tenant_id = state_data.get("tenant_id")
        user_id = state_data.get("user_id")
        if not tenant_id:
            raise ValueError("State does not contain tenant_id.")

        tokens = oauth_service.exchange_code_for_tokens(code)
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token") or ""
        expires_in = tokens.get("expires_in", 3600)
        from datetime import UTC, datetime, timedelta
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

        email = oauth_service.fetch_user_email(access_token)

        connection = oauth_service.store_connection(
            tenant_id=tenant_id,
            user_id=user_id,
            google_account_email=email,
            calendar_id="primary",
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=expires_at,
        )

        calendar_service = GoogleCalendarService(db, oauth_service)
        try:
            calendar_service.sync_calendars(connection)
        except Exception:
            pass

    except ValueError as exc:
        if should_redirect:
            return RedirectResponse(url=f"{frontend_base}?status=error&detail={str(exc)}", status_code=302)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    if should_redirect:
        return RedirectResponse(url=f"{frontend_base}?status=connected", status_code=302)

    return oauth_service.response(connection)


@router.get("/google-calendar/connections", response_model=list[GoogleCalendarConnectionResponse])
def list_google_calendar_connections(
    context: AuthContext = Depends(require_enabled_integration("google_calendar", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = GoogleCalendarOAuthService(db)
    return [service.response(connection) for connection in service.list_connections(context.tenant.id)]


@router.post("/google-calendar/disconnect", response_model=GoogleCalendarConnectionResponse)
def disconnect_google_calendar(
    connection_id: str,
    context: AuthContext = Depends(require_enabled_integration("google_calendar", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = GoogleCalendarOAuthService(db)
    try:
        connection = service.disconnect_connection(context.tenant.id, connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return service.response(connection)


@router.delete("/google-calendar/connections/{connection_id}", response_model=dict[str, Any])
def delete_google_calendar_connection(
    connection_id: str,
    context: AuthContext = Depends(require_enabled_integration("google_calendar", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = GoogleCalendarOAuthService(db)
    try:
        service.delete_connection(context.tenant.id, connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"deleted": True, "connection_id": connection_id}


@router.post("/google-calendar/connections/{connection_id}/sync", response_model=GoogleCalendarSyncResponse)
def sync_google_calendar_connection(
    connection_id: str,
    context: AuthContext = Depends(require_enabled_integration("google_calendar", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    connection = db.scalar(
        select(TenantGoogleCalendarConnection).where(
            TenantGoogleCalendarConnection.tenant_id == context.tenant.id,
            TenantGoogleCalendarConnection.id == connection_id,
        )
    )
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google Calendar connection not found.")

    cal_service = GoogleCalendarService(db)
    try:
        calendars = cal_service.sync_calendars(connection)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return GoogleCalendarSyncResponse(
        connection_id=connection.id,
        synced_count=len(calendars),
        calendars=[
            TenantGoogleCalendarResponse(
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
            for c in calendars
        ],
    )


@router.get("/google-calendar/calendars", response_model=list[TenantGoogleCalendarResponse])
def list_google_calendars(
    connection_id: str | None = None,
    context: AuthContext = Depends(require_enabled_integration("google_calendar", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    cal_service = GoogleCalendarService(db)
    calendars = cal_service.list_tenant_calendars(context.tenant.id, connection_id=connection_id)
    return [
        TenantGoogleCalendarResponse(
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
        for c in calendars
    ]


@router.patch("/google-calendar/calendars/{calendar_id}", response_model=TenantGoogleCalendarResponse)
def update_google_calendar(
    calendar_id: str,
    body: TenantGoogleCalendarUpdateRequest,
    context: AuthContext = Depends(require_enabled_integration("google_calendar", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    cal_service = GoogleCalendarService(db)
    try:
        cal = cal_service.update_calendar_settings(
            tenant_id=context.tenant.id,
            calendar_id=calendar_id,
            is_blocking=body.is_blocking,
            is_booking_destination=body.is_booking_destination,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return TenantGoogleCalendarResponse(
        id=cal.id,
        tenant_id=cal.tenant_id,
        connection_id=cal.connection_id,
        google_calendar_id=cal.google_calendar_id,
        summary=cal.summary,
        description=cal.description,
        time_zone=cal.time_zone,
        is_primary=cal.is_primary,
        is_blocking=cal.is_blocking,
        is_booking_destination=cal.is_booking_destination,
        access_role=cal.access_role,
        created_at=cal.created_at,
        updated_at=cal.updated_at,
    )


@router.post("/scheduling/resources", response_model=SchedulingResourceResponse)
def create_scheduling_resource(
    body: SchedulingResourceCreateRequest,
    context: AuthContext = Depends(require_enabled_integration("google_calendar", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    resource_service = SchedulingResourceService(db)
    resource = resource_service.create_resource(
        tenant_id=context.tenant.id,
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
    return SchedulingResourceResponse(
        id=resource.id,
        tenant_id=resource.tenant_id,
        name=resource.name,
        resource_type=resource.resource_type,
        team=resource.team,
        email=resource.email,
        phone=resource.phone,
        priority=resource.priority,
        is_active=resource.is_active,
        timezone=resource.timezone,
        capacity=resource.capacity,
        total_assigned_count=resource.total_assigned_count,
        last_assigned_at=resource.last_assigned_at,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
        calendars=[],
    )


@router.get("/scheduling/resources", response_model=list[SchedulingResourceResponse])
def list_scheduling_resources(
    team: str | None = None,
    context: AuthContext = Depends(require_enabled_integration("google_calendar", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    resource_service = SchedulingResourceService(db)
    resources = resource_service.list_resources(tenant_id=context.tenant.id, team=team)
    return [
        SchedulingResourceResponse(
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
            calendars=[
                SchedulingResourceCalendarResponse(
                    id=c.id,
                    resource_id=c.resource_id,
                    calendar_id=c.calendar_id,
                    is_blocking=c.is_blocking,
                    is_destination=c.is_destination,
                    created_at=c.created_at,
                )
                for c in (r.resource_calendars or [])
            ],
        )
        for r in resources
    ]


@router.post("/scheduling/resources/{resource_id}/calendars", response_model=SchedulingResourceCalendarResponse)
def assign_calendar_to_resource(
    resource_id: str,
    body: SchedulingResourceCalendarAssignRequest,
    context: AuthContext = Depends(require_enabled_integration("google_calendar", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    resource_service = SchedulingResourceService(db)
    try:
        mapping = resource_service.assign_calendar_to_resource(
            tenant_id=context.tenant.id,
            resource_id=resource_id,
            calendar_id=body.calendar_id,
            is_blocking=body.is_blocking,
            is_destination=body.is_destination,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return SchedulingResourceCalendarResponse(
        id=mapping.id,
        resource_id=mapping.resource_id,
        calendar_id=mapping.calendar_id,
        is_blocking=mapping.is_blocking,
        is_destination=mapping.is_destination,
        created_at=mapping.created_at,
    )


@router.post("/resend/config", response_model=ResendIntegrationConfigResponse)
def configure_resend(
    body: ResendIntegrationConfigRequest,
    context: AuthContext = Depends(require_enabled_integration("resend", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    integration_service = IntegrationService(db)
    config_service = EmailConfigService(db)
    existing = integration_service.get_integration(tenant_id, "resend")
    if not body.resend_api_key and not integration_service.has_secret(existing):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Resend API key is required for the first configuration.",
        )
    try:
        config = config_service.upsert_resend_config(
            tenant_id=tenant_id,
            sender_name=body.sender_name,
            sender_email=body.sender_email,
            reply_to=body.reply_to,
            default_domain=body.default_domain,
            status="active",
        )
        integration = integration_service.upsert_resend(
            tenant_id=tenant_id,
            display_name="Resend",
            config={
                "sender_name": config.sender_name,
                "sender_email": config.sender_email,
                "reply_to": config.reply_to,
                "default_domain": config.default_domain,
            },
            api_key=body.resend_api_key,
        )
        EmailTemplateService(db).ensure_default_templates(tenant_id)
        IntegrationEventService(db).record_event(
            tenant_id=tenant_id,
            provider="resend",
            event_type="config_updated",
            status="success",
            resource_type="config",
            resource_id=integration.id,
            metadata={"has_secret": integration_service.has_secret(integration)},
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _resend_response(integration_service, tenant_id, config_service)


@router.post("/resend/test", response_model=ResendTestEmailResponse)
def test_resend(
    body: ResendTestEmailRequest,
    context: AuthContext = Depends(require_enabled_integration("resend", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        result = EmailSendService(db).send_test_email(tenant_id=context.tenant.id, to_email=body.to_email)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error_message or "Resend test failed.")
    return ResendTestEmailResponse(status=result.status, provider_email_id=result.provider_email_id)


@router.get("/whatsapp/config", response_model=WhatsAppConfigResponse)
def get_whatsapp_config(
    context: AuthContext = Depends(require_enabled_integration("whatsapp", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return WhatsAppConfigService(db).get_response(context.tenant.id)


@router.post("/whatsapp/config", response_model=WhatsAppConfigResponse)
def configure_whatsapp(
    body: WhatsAppConfigRequest,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return WhatsAppConfigService(db).upsert_config(context.tenant.id, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/whatsapp/test", response_model=WhatsAppTestResponse)
def test_whatsapp(
    body: WhatsAppTestRequest | None = None,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    result = WhatsAppConfigService(db).test_connection(context.tenant.id)
    return result


@router.post("/whatsapp/templates/sync", response_model=WhatsAppTemplateSyncResponse)
def sync_whatsapp_templates(
    context: AuthContext = Depends(require_enabled_integration("whatsapp", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        result = WhatsAppConfigService(db).sync_templates(context.tenant.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error_message or "WhatsApp template sync failed.")
    return result


@router.post("/whatsapp/test-message", response_model=WhatsAppTestMessageResponse)
def send_whatsapp_test_message(
    body: WhatsAppTestMessageRequest,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        result = WhatsAppMessageService(db).send_test_template_message(context.tenant.id, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error_message or "WhatsApp test message failed.")
    return result


@router.get("/whatsapp/templates", response_model=list[WhatsAppTemplateResponse])
def list_whatsapp_templates(
    context: AuthContext = Depends(require_enabled_integration("whatsapp", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = WhatsAppTemplateService(db)
    templates = service.list_templates(context.tenant.id)
    return [
        WhatsAppTemplateResponse(
            id=template.id,
            template_key=template.template_key,
            provider_template_name=template.provider_template_name,
            name=template.name,
            category=template.category,
            language=template.language,
            body=template.body,
            variables=service.variables_payload(template),
            status=template.status,
        )
        for template in templates
    ]


def _whatsapp_template_detail(
    service: WhatsAppTemplateService, template: TenantWhatsAppTemplate
) -> WhatsAppTemplateDetailResponse:
    return WhatsAppTemplateDetailResponse(
        id=template.id,
        template_key=template.template_key,
        provider_template_name=template.provider_template_name,
        name=template.name,
        category=template.category,
        language=template.language,
        body=template.body,
        variables=service.variables_payload(template),
        status=template.status,
        meta_status=template.meta_status,
        provider_template_id=template.provider_template_id,
        source=template.source,
        parameter_format=template.parameter_format,
        header_text=(template.header_json or {}).get("text"),
        footer_text=template.footer_text,
        buttons=template.buttons_json or [],
        rejection_reason=template.rejection_reason,
        last_synced_at=template.last_synced_at,
    )


@router.post("/whatsapp/templates", response_model=WhatsAppTemplateDetailResponse, status_code=status.HTTP_201_CREATED)
def create_whatsapp_template(
    body: WhatsAppTemplateCreateRequest,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = WhatsAppTemplateService(db)
    try:
        template = service.create_draft(context.tenant.id, body, context.user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _whatsapp_template_detail(service, template)


@router.get("/whatsapp/templates/{template_id}", response_model=WhatsAppTemplateDetailResponse)
def get_whatsapp_template(
    template_id: str,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = WhatsAppTemplateService(db)
    try:
        template = service.get_owned(context.tenant.id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _whatsapp_template_detail(service, template)


@router.patch("/whatsapp/templates/{template_id}", response_model=WhatsAppTemplateDetailResponse)
def update_whatsapp_template(
    template_id: str,
    body: WhatsAppTemplateUpdateRequest,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = WhatsAppTemplateService(db)
    try:
        template = service.update_draft(context.tenant.id, template_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _whatsapp_template_detail(service, template)


@router.delete("/whatsapp/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_whatsapp_template(
    template_id: str,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> None:
    try:
        WhatsAppTemplateService(db).delete_draft(context.tenant.id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/whatsapp/templates/{template_id}/preview", response_model=WhatsAppTemplatePreviewResponse)
def preview_whatsapp_template(
    template_id: str,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return WhatsAppTemplateService(db).preview(context.tenant.id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/whatsapp/templates/{template_id}/submit", response_model=WhatsAppTemplateSubmitResponse)
def submit_whatsapp_template(
    template_id: str,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        result = WhatsAppConfigService(db).submit_template(context.tenant.id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error_message or "WhatsApp template submission failed."
        )
    return result


@router.post("/whatsapp/templates/{template_id}/sync-status", response_model=WhatsAppTemplateSubmitResponse)
def sync_whatsapp_template_status(
    template_id: str,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        result = WhatsAppConfigService(db).sync_template_status(context.tenant.id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.error_message or "WhatsApp template status sync failed.",
        )
    return result


@router.get("/resend/templates", response_model=list[EmailTemplateItem])
def list_resend_templates(
    context: AuthContext = Depends(require_enabled_integration("resend", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    templates = EmailTemplateService(db).ensure_default_templates(context.tenant.id)
    return [EmailTemplateItem.model_validate(template, from_attributes=True) for template in templates]


@router.post("/resend/templates", response_model=EmailTemplateItem)
def upsert_resend_template(
    body: EmailTemplateUpsertRequest,
    context: AuthContext = Depends(require_enabled_integration("resend", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    template = db.scalar(
        select(TenantEmailTemplate).where(
            TenantEmailTemplate.tenant_id == tenant_id,
            TenantEmailTemplate.template_key == body.template_key,
        )
    )
    if template is None:
        template = TenantEmailTemplate(tenant_id=tenant_id, template_key=body.template_key)
        db.add(template)
    template.name = body.name
    template.subject = body.subject
    template.html_body = body.html_body
    template.text_body = body.text_body
    template.category = body.category
    template.status = body.status
    template.is_marketing = False
    template.variables_schema = {"allowed": ["contact_name", "message"]}
    db.commit()
    db.refresh(template)
    return EmailTemplateItem.model_validate(template, from_attributes=True)


# --- Voice Integration Config ---

@router.get("/voice/config", response_model=VoiceProviderConfigResponse)
def get_voice_config(
    context: AuthContext = Depends(require_enabled_integration("voice", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return VoiceConfigService(db).get_config_response(context.tenant.id)


@router.post("/voice/config", response_model=VoiceProviderConfigResponse)
def configure_voice(
    body: VoiceProviderConfigRequest,
    context: AuthContext = Depends(require_enabled_integration("voice", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        config = VoiceConfigService(db).upsert_provider_config(context.tenant.id, body)
        return VoiceConfigService(db).get_config_response(context.tenant.id, config.provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/voice/test")
def test_voice(
    provider: str = "ultravox",
    context: AuthContext = Depends(require_enabled_integration("voice", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        result, error = VoiceConfigService(db).test_connection(context.tenant.id, provider)
        if result != "active":
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error or "Voice test failed.")
        return {"status": result}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# --- Voice Agent Config ---

@router.get("/voice/agents", response_model=list[VoiceAgentConfigResponse])
def list_voice_agents(
    context: AuthContext = Depends(require_enabled_integration("voice", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceAgentService(db)
    agents = service.list_agent_configs(context.tenant.id)
    return [service.response(agent) for agent in agents]


@router.post("/voice/agents", response_model=VoiceAgentConfigResponse)
def create_voice_agent(
    body: VoiceAgentConfigRequest,
    context: AuthContext = Depends(require_enabled_integration("voice", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        service = VoiceAgentService(db)
        agent = service.create_or_update_agent_config(context.tenant.id, body)
        return service.response(agent)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.put("/voice/agents/{agent_config_id}", response_model=VoiceAgentConfigResponse)
def update_voice_agent(
    agent_config_id: str,
    body: VoiceAgentConfigRequest,
    context: AuthContext = Depends(require_enabled_integration("voice", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        service = VoiceAgentService(db)
        agent = service.create_or_update_agent_config(context.tenant.id, body, agent_config_id)
        return service.response(agent)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# --- Chatwoot Integration Config ---

@router.get("/chatwoot/config", response_model=ChatwootConfigResponse)
def get_chatwoot_config(
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return ChatwootConfigService(db).get_response(context.tenant.id)


@router.post("/chatwoot/config", response_model=ChatwootConfigResponse)
def configure_chatwoot(
    body: ChatwootConfigRequest,
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return ChatwootConfigService(db).upsert_config(context.tenant.id, body)
    except ChatwootAccountConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/chatwoot/test", response_model=ChatwootTestResponse)
def test_chatwoot(
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return ChatwootConfigService(db).test_connection(context.tenant.id)


@router.post("/chatwoot/provision", response_model=ChatwootConfigResponse)
def provision_chatwoot(
    body: ChatwootProvisionRequest,
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    account_name = (body.account_name or context.tenant.name).strip()
    try:
        return ChatwootConfigService(db).provision_managed_account(context.tenant.id, account_name=account_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/chatwoot/disconnect", response_model=ChatwootConfigResponse)
def disconnect_chatwoot(
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return ChatwootConfigService(db).disconnect(context.tenant.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/chatwoot/inboxes", response_model=list[ChatwootInboxSummary])
async def list_chatwoot_inboxes(
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return await ChatwootConfigService(db).list_inboxes(context.tenant.id)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.get("/chatwoot/teams", response_model=list[ChatwootTeamSummary])
async def list_chatwoot_teams(
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return await ChatwootConfigService(db).list_teams(context.tenant.id)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.post("/chatwoot/inboxes", response_model=ChatwootInboxSummary)
async def create_chatwoot_inbox(
    body: ChatwootInboxCreateRequest,
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return await ChatwootConfigService(db).create_inbox(context.tenant.id, name=body.name)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.get("/chatwoot/agents", response_model=list[ChatwootAgentSummary])
async def list_chatwoot_agents(
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return await ChatwootConfigService(db).list_agents(context.tenant.id)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.post("/chatwoot/teams", response_model=ChatwootTeamSummary)
async def create_chatwoot_team(
    body: ChatwootTeamCreateRequest,
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return await ChatwootConfigService(db).create_team(context.tenant.id, name=body.name, description=body.description)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.post("/chatwoot/agents", response_model=ChatwootAgentSummary)
async def invite_chatwoot_agent(
    body: ChatwootAgentInviteRequest,
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return await ChatwootConfigService(db).invite_agent(context.tenant.id, name=body.name, email=body.email, role=body.role)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.patch("/chatwoot/inboxes/{inbox_id}", response_model=ChatwootInboxSummary)
async def update_chatwoot_inbox(
    inbox_id: int,
    body: ChatwootInboxUpdateRequest,
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return await ChatwootConfigService(db).update_inbox(context.tenant.id, inbox_id, name=body.name)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.patch("/chatwoot/teams/{team_id}", response_model=ChatwootTeamSummary)
async def update_chatwoot_team(
    team_id: int,
    body: ChatwootTeamUpdateRequest,
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return await ChatwootConfigService(db).update_team(context.tenant.id, team_id, name=body.name, description=body.description)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.delete("/chatwoot/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chatwoot_team(
    team_id: int,
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> None:
    try:
        await ChatwootConfigService(db).delete_team(context.tenant.id, team_id)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.patch("/chatwoot/agents/{agent_id}", response_model=ChatwootAgentSummary)
async def update_chatwoot_agent(
    agent_id: int,
    body: ChatwootAgentUpdateRequest,
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return await ChatwootConfigService(db).update_agent(context.tenant.id, agent_id, name=body.name, role=body.role)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.delete("/chatwoot/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chatwoot_agent(
    agent_id: int,
    context: AuthContext = Depends(require_enabled_integration("chatwoot", _WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> None:
    try:
        await ChatwootConfigService(db).delete_agent(context.tenant.id, agent_id)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc
