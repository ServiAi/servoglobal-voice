"""Per-tenant Integrations admin API (WhatsApp, Resend, Chatwoot, catalog) for internal platform users.

Same URLs as before the module migration (``/api/v1/admin/tenants/{tenant_id}/integrations/...``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.session import get_db
from app.modules.integrations.wiring import require_tenant
from typing import Any
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.modules.integrations.api.router import _integration_catalog_statuses, _resend_response, _whatsapp_template_detail
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
    IntegrationAvailabilityResponse,
    IntegrationAvailabilityUpdateRequest,
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
from app.modules.integrations.infrastructure.chatwoot.client import ChatwootClientError, sanitize_chatwoot_error
from app.modules.integrations.application.chatwoot.config_service import ChatwootAccountConflictError, ChatwootConfigService
from app.modules.integrations.application.email.config_service import EmailConfigService
from app.modules.integrations.application.email.send_service import EmailSendService
from app.modules.integrations.application.email.template_service import EmailTemplateService
from app.modules.integrations.application.event_service import IntegrationEventService
from app.modules.integrations.application.integration_service import IntegrationService
from app.modules.integrations.application.whatsapp.config_service import WhatsAppConfigService
from app.modules.integrations.application.whatsapp.message_service import WhatsAppMessageService
from app.modules.integrations.application.whatsapp.template_service import WhatsAppTemplateService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def get_current_internal_db(
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> Session:
    """Internal-platform-user guard + DB session."""
    if not context.user.is_internal:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Internal platform access required")
    return db


@router.get(
    "/tenants/{tenant_id}/integrations",
    response_model=list[ResendIntegrationConfigResponse],
)
def list_tenant_integrations_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    integration_service = IntegrationService(db)
    config_service = EmailConfigService(db)
    return [_resend_response(integration_service, tenant_id, config_service)]


@router.get(
    "/tenants/{tenant_id}/integrations/availability",
    response_model=list[IntegrationAvailabilityResponse],
)
def list_tenant_integration_availability_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return IntegrationService(db).list_availability(tenant_id)


@router.get(
    "/tenants/{tenant_id}/integrations/statuses",
    response_model=list[IntegrationCatalogStatusResponse],
)
def list_tenant_integration_catalog_statuses_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found") from None
    return _integration_catalog_statuses(
        db,
        tenant_id,
        {"resend", "whatsapp", "voice", "calcom", "google_calendar", "chatwoot"},
    )


@router.get(
    "/tenants/{tenant_id}/integrations/chatwoot/config",
    response_model=ChatwootConfigResponse,
)
def get_tenant_chatwoot_config_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ChatwootConfigService(db).get_response(tenant_id)


@router.post(
    "/tenants/{tenant_id}/integrations/chatwoot/config",
    response_model=ChatwootConfigResponse,
)
def configure_tenant_chatwoot_admin(
    tenant_id: str,
    body: ChatwootConfigRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
        return ChatwootConfigService(db).upsert_config(tenant_id, body)
    except ChatwootAccountConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/tenants/{tenant_id}/integrations/chatwoot/test",
    response_model=ChatwootTestResponse,
)
def test_tenant_chatwoot_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ChatwootConfigService(db).test_connection(tenant_id)


@router.post(
    "/tenants/{tenant_id}/integrations/chatwoot/provision",
    response_model=ChatwootConfigResponse,
)
def provision_tenant_chatwoot_admin(
    tenant_id: str,
    body: ChatwootProvisionRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        tenant = require_tenant(db, tenant_id)
        account_name = (body.account_name or tenant.name).strip()
        return ChatwootConfigService(db).provision_managed_account(tenant_id, account_name=account_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/tenants/{tenant_id}/integrations/chatwoot/disconnect",
    response_model=ChatwootConfigResponse,
)
def disconnect_tenant_chatwoot_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
        return ChatwootConfigService(db).disconnect(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get(
    "/tenants/{tenant_id}/integrations/chatwoot/inboxes",
    response_model=list[ChatwootInboxSummary],
)
async def list_tenant_chatwoot_inboxes_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
        return await ChatwootConfigService(db).list_inboxes(tenant_id)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.get(
    "/tenants/{tenant_id}/integrations/chatwoot/teams",
    response_model=list[ChatwootTeamSummary],
)
async def list_tenant_chatwoot_teams_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
        return await ChatwootConfigService(db).list_teams(tenant_id)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.post(
    "/tenants/{tenant_id}/integrations/chatwoot/inboxes",
    response_model=ChatwootInboxSummary,
)
async def create_tenant_chatwoot_inbox_admin(
    tenant_id: str,
    body: ChatwootInboxCreateRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
        return await ChatwootConfigService(db).create_inbox(tenant_id, name=body.name)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.post(
    "/tenants/{tenant_id}/integrations/chatwoot/teams",
    response_model=ChatwootTeamSummary,
)
async def create_tenant_chatwoot_team_admin(
    tenant_id: str,
    body: ChatwootTeamCreateRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
        return await ChatwootConfigService(db).create_team(tenant_id, name=body.name, description=body.description)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.get(
    "/tenants/{tenant_id}/integrations/chatwoot/agents",
    response_model=list[ChatwootAgentSummary],
)
async def list_tenant_chatwoot_agents_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
        return await ChatwootConfigService(db).list_agents(tenant_id)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.post(
    "/tenants/{tenant_id}/integrations/chatwoot/agents",
    response_model=ChatwootAgentSummary,
)
async def invite_tenant_chatwoot_agent_admin(
    tenant_id: str,
    body: ChatwootAgentInviteRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
        return await ChatwootConfigService(db).invite_agent(tenant_id, name=body.name, email=body.email, role=body.role)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.patch(
    "/tenants/{tenant_id}/integrations/chatwoot/inboxes/{inbox_id}",
    response_model=ChatwootInboxSummary,
)
async def update_tenant_chatwoot_inbox_admin(
    tenant_id: str,
    inbox_id: int,
    body: ChatwootInboxUpdateRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
        return await ChatwootConfigService(db).update_inbox(tenant_id, inbox_id, name=body.name)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.patch(
    "/tenants/{tenant_id}/integrations/chatwoot/teams/{team_id}",
    response_model=ChatwootTeamSummary,
)
async def update_tenant_chatwoot_team_admin(
    tenant_id: str,
    team_id: int,
    body: ChatwootTeamUpdateRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
        return await ChatwootConfigService(db).update_team(tenant_id, team_id, name=body.name, description=body.description)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.delete(
    "/tenants/{tenant_id}/integrations/chatwoot/teams/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_tenant_chatwoot_team_admin(
    tenant_id: str,
    team_id: int,
    db: Session = Depends(get_current_internal_db),
) -> None:
    try:
        require_tenant(db, tenant_id)
        await ChatwootConfigService(db).delete_team(tenant_id, team_id)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.patch(
    "/tenants/{tenant_id}/integrations/chatwoot/agents/{agent_id}",
    response_model=ChatwootAgentSummary,
)
async def update_tenant_chatwoot_agent_admin(
    tenant_id: str,
    agent_id: int,
    body: ChatwootAgentUpdateRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
        return await ChatwootConfigService(db).update_agent(tenant_id, agent_id, name=body.name, role=body.role)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.delete(
    "/tenants/{tenant_id}/integrations/chatwoot/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_tenant_chatwoot_agent_admin(
    tenant_id: str,
    agent_id: int,
    db: Session = Depends(get_current_internal_db),
) -> None:
    try:
        require_tenant(db, tenant_id)
        await ChatwootConfigService(db).delete_agent(tenant_id, agent_id)
    except (ValueError, ChatwootClientError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=sanitize_chatwoot_error(str(exc))) from exc


@router.patch(
    "/tenants/{tenant_id}/integrations/availability/{provider}",
    response_model=IntegrationAvailabilityResponse,
)
def update_tenant_integration_availability_admin(
    tenant_id: str,
    provider: str,
    body: IntegrationAvailabilityUpdateRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
        integration = IntegrationService(db).set_enabled(tenant_id, provider, body.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    IntegrationEventService(db).record_event(
        tenant_id=tenant_id,
        provider=provider,
        event_type="integration_availability_updated",
        status="success",
        resource_type="tenant_integration",
        resource_id=integration.id,
        metadata={"enabled": body.enabled},
    )
    return IntegrationAvailabilityResponse(provider=provider, enabled=body.enabled)


@router.post(
    "/tenants/{tenant_id}/integrations/resend/config",
    response_model=ResendIntegrationConfigResponse,
)
def configure_tenant_resend_admin(
    tenant_id: str,
    body: ResendIntegrationConfigRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

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


@router.post(
    "/tenants/{tenant_id}/integrations/resend/test",
    response_model=ResendTestEmailResponse,
)
def test_tenant_resend_admin(
    tenant_id: str,
    body: ResendTestEmailRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    try:
        result = EmailSendService(db).send_test_email(tenant_id=tenant_id, to_email=body.to_email)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error_message or "Resend test failed.")
    return ResendTestEmailResponse(status=result.status, provider_email_id=result.provider_email_id)


@router.get(
    "/tenants/{tenant_id}/integrations/whatsapp/config",
    response_model=WhatsAppConfigResponse,
)
def get_tenant_whatsapp_config_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return WhatsAppConfigService(db).get_response(tenant_id)


@router.post(
    "/tenants/{tenant_id}/integrations/whatsapp/config",
    response_model=WhatsAppConfigResponse,
)
def configure_tenant_whatsapp_admin(
    tenant_id: str,
    body: WhatsAppConfigRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
        return WhatsAppConfigService(db).upsert_config(tenant_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/tenants/{tenant_id}/integrations/whatsapp/test",
    response_model=WhatsAppTestResponse,
)
def test_tenant_whatsapp_admin(
    tenant_id: str,
    body: WhatsAppTestRequest | None = None,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    result = WhatsAppConfigService(db).test_connection(tenant_id)
    return result


@router.post(
    "/tenants/{tenant_id}/integrations/whatsapp/templates/sync",
    response_model=WhatsAppTemplateSyncResponse,
)
def sync_tenant_whatsapp_templates_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    try:
        result = WhatsAppConfigService(db).sync_templates(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error_message or "WhatsApp template sync failed.")
    return result


@router.post(
    "/tenants/{tenant_id}/integrations/whatsapp/test-message",
    response_model=WhatsAppTestMessageResponse,
)
def send_tenant_whatsapp_test_message_admin(
    tenant_id: str,
    body: WhatsAppTestMessageRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    try:
        result = WhatsAppMessageService(db).send_test_template_message(tenant_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error_message or "WhatsApp test message failed.")
    return result


@router.get(
    "/tenants/{tenant_id}/integrations/whatsapp/templates",
    response_model=list[WhatsAppTemplateResponse],
)
def list_tenant_whatsapp_templates_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    service = WhatsAppTemplateService(db)
    templates = service.list_templates(tenant_id)
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


@router.post(
    "/tenants/{tenant_id}/integrations/whatsapp/templates",
    response_model=WhatsAppTemplateDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_tenant_whatsapp_template_admin(
    tenant_id: str,
    body: WhatsAppTemplateCreateRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    service = WhatsAppTemplateService(db)
    try:
        template = service.create_draft(tenant_id, body, None)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _whatsapp_template_detail(service, template)


@router.get(
    "/tenants/{tenant_id}/integrations/whatsapp/templates/{template_id}",
    response_model=WhatsAppTemplateDetailResponse,
)
def get_tenant_whatsapp_template_admin(
    tenant_id: str,
    template_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    service = WhatsAppTemplateService(db)
    try:
        template = service.get_owned(tenant_id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _whatsapp_template_detail(service, template)


@router.patch(
    "/tenants/{tenant_id}/integrations/whatsapp/templates/{template_id}",
    response_model=WhatsAppTemplateDetailResponse,
)
def update_tenant_whatsapp_template_admin(
    tenant_id: str,
    template_id: str,
    body: WhatsAppTemplateUpdateRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    service = WhatsAppTemplateService(db)
    try:
        template = service.update_draft(tenant_id, template_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _whatsapp_template_detail(service, template)


@router.delete(
    "/tenants/{tenant_id}/integrations/whatsapp/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_tenant_whatsapp_template_admin(
    tenant_id: str,
    template_id: str,
    db: Session = Depends(get_current_internal_db),
) -> None:
    try:
        WhatsAppTemplateService(db).delete_draft(tenant_id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get(
    "/tenants/{tenant_id}/integrations/whatsapp/templates/{template_id}/preview",
    response_model=WhatsAppTemplatePreviewResponse,
)
def preview_tenant_whatsapp_template_admin(
    tenant_id: str,
    template_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        return WhatsAppTemplateService(db).preview(tenant_id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/tenants/{tenant_id}/integrations/whatsapp/templates/{template_id}/submit",
    response_model=WhatsAppTemplateSubmitResponse,
)
def submit_tenant_whatsapp_template_admin(
    tenant_id: str,
    template_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        result = WhatsAppConfigService(db).submit_template(tenant_id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error_message or "WhatsApp template submission failed."
        )
    return result


@router.post(
    "/tenants/{tenant_id}/integrations/whatsapp/templates/{template_id}/sync-status",
    response_model=WhatsAppTemplateSubmitResponse,
)
def sync_tenant_whatsapp_template_status_admin(
    tenant_id: str,
    template_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        result = WhatsAppConfigService(db).sync_template_status(tenant_id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.error_message or "WhatsApp template status sync failed.",
        )
    return result
