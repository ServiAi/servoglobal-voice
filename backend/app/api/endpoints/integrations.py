from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.db.session import get_db
from app.models.integrations import TenantEmailTemplate, TenantWhatsAppTemplate
from app.schemas.integrations import (
    BookingConfigRequest,
    BookingConfigResponse,
    CalComTestResponse,
    EmailTemplateItem,
    EmailTemplateUpsertRequest,
    GoogleCalendarConnectionResponse,
    GoogleCalendarConnectUrlResponse,
    IntegrationAvailabilityResponse,
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
from app.services.booking_config_service import BookingConfigService
from app.services.booking_service import BookingService
from app.services.email_config_service import EmailConfigService
from app.services.email_send_service import EmailSendService
from app.services.email_template_service import EmailTemplateService
from app.services.google_calendar_oauth_service import GoogleCalendarOAuthService
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
        url = GoogleCalendarOAuthService(db).build_auth_url(state=f"{context.tenant.id}:{context.user.id}")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return GoogleCalendarConnectUrlResponse(url=url)


@router.get("/google-calendar/callback")
def google_calendar_callback() -> Any:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Google Calendar OAuth callback is prepared but not enabled yet.")


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
