from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.api.deps import require_enabled_integration
from app.db.session import get_db
from app.modules.integrations.api.schemas import (
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
)
from app.modules.integrations.application.chatwoot.config_service import (
    ChatwootAccountConflictError,
    ChatwootConfigService,
)
from app.modules.integrations.application.email.config_service import EmailConfigService
from app.modules.integrations.application.email.send_service import EmailSendService
from app.modules.integrations.application.email.template_service import (
    EmailTemplateService,
)
from app.modules.integrations.api.translate import template_create_command, template_update_command
from app.modules.integrations.application.dto import (
    ChatwootConfigCommand,
    WhatsAppConfigCommand,
    WhatsAppTestMessageCommand,
)
from app.modules.integrations.application.event_service import IntegrationEventService
from app.modules.integrations.application.integration_service import IntegrationService
from app.modules.integrations.application.whatsapp.config_service import (
    WhatsAppConfigService,
)
from app.modules.integrations.application.whatsapp.message_service import (
    WhatsAppMessageService,
)
from app.modules.integrations.application.whatsapp.template_service import (
    WhatsAppTemplateService,
)
from app.modules.integrations.domain.catalog import catalog_status
from app.modules.integrations.infrastructure.chatwoot.client import (
    ChatwootClientError,
    sanitize_chatwoot_error,
)
from app.modules.integrations.infrastructure.models import (
    TenantEmailTemplate,
    TenantWhatsAppTemplate,
)
from app.modules.integrations.wiring import foreign_catalog_inputs

router = APIRouter(prefix="/api/v1/integrations", tags=["Integrations"])

_READ_ROLES = ["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"]
_WRITE_ROLES = ["platform_admin", "tenant_admin"]


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
        statuses["resend"] = catalog_status(
            configured=bool(integration or config),
            provider_status=config.status if config else integration.status if integration else None,
            has_error=bool(config.last_error_message if config else integration.last_error_message if integration else None),
        )

    if "whatsapp" in selected:
        config = WhatsAppConfigService(db).get_config(tenant_id)
        statuses["whatsapp"] = catalog_status(
            configured=config is not None,
            provider_status=config.status if config else None,
            has_error=bool(config and config.last_error_message),
        )

    foreign = foreign_catalog_inputs(db, tenant_id, selected)
    for provider, facts in foreign.items():
        statuses[provider] = catalog_status(
            configured=facts.configured, provider_status=facts.provider_status, has_error=facts.has_error
        )

    if "chatwoot" in selected:
        config = ChatwootConfigService(db).get_config(tenant_id)
        statuses["chatwoot"] = catalog_status(
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
        return WhatsAppConfigService(db).upsert_config(context.tenant.id, WhatsAppConfigCommand(**body.model_dump()))
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
        result = WhatsAppMessageService(db).send_test_template_message(context.tenant.id, WhatsAppTestMessageCommand(**body.model_dump()))
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
        template = service.create_draft(context.tenant.id, template_create_command(body), context.user.id)
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
        template = service.update_draft(context.tenant.id, template_id, template_update_command(body))
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
        return ChatwootConfigService(db).upsert_config(context.tenant.id, ChatwootConfigCommand(**body.model_dump()))
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
