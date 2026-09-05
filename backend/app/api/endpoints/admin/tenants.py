from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.session import get_db
from app.models.identity import User
from app.schemas.billing import TenantPlanRequest
from app.schemas.onboarding import (
    AgentCreateRequest,
    AgentResponse,
    MembershipCreateRequest,
    MembershipResponse,
    TenantCreateRequest,
    TenantResponse,
    TenantUpdateRequest,
)
from app.services.auth0_provisioning_service import (
    Auth0ProvisioningError,
    Auth0ProvisioningService,
)
from app.services.onboarding_service import (
    OnboardingConsistencyError,
    OnboardingService,
    TenantDeletionBlockedError,
)
from app.services.tenant_usage_service import TenantUsageService
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
    GoogleCalendarConnectionResponse,
    IntegrationAvailabilityResponse,
    IntegrationCatalogStatusResponse,
    IntegrationAvailabilityUpdateRequest,
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
)
from app.schemas.crm import BookingCreateRequest, BookingResponse
from app.api.endpoints.integrations import _integration_catalog_statuses, _resend_response, _whatsapp_template_detail
from app.services.booking_config_service import BookingConfigService
from app.services.chatwoot_client import ChatwootClientError, sanitize_chatwoot_error
from app.services.chatwoot_config_service import ChatwootAccountConflictError, ChatwootConfigService
from app.services.booking_service import BookingService
from app.services.email_config_service import EmailConfigService
from app.services.email_send_service import EmailSendService
from app.services.email_template_service import EmailTemplateService
from app.services.voice_config_service import VoiceConfigService
from app.services.voice_agent_service import VoiceAgentService
from app.services.google_calendar_oauth_service import GoogleCalendarOAuthService
from app.services.integration_event_service import IntegrationEventService
from app.services.integration_service import IntegrationService
from app.services.whatsapp_config_service import WhatsAppConfigService
from app.services.whatsapp_message_service import WhatsAppMessageService
from app.services.whatsapp_template_service import WhatsAppTemplateService
from app.services.voice_config_service import VoiceConfigService
from app.services.voice_agent_service import VoiceAgentService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def get_current_internal_user(
    context: AuthContext = Depends(get_current_auth_context),
) -> User:
    if not context.user.is_internal:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal platform access required",
        )
    return context.user


def get_current_internal_db(
    user: User = Depends(get_current_internal_user),
    db: Session = Depends(get_db),
) -> Session:
    """Auth guard + DB session for admin endpoints."""
    return db


def get_auth0_provisioning_service() -> Auth0ProvisioningService:
    return Auth0ProvisioningService()


@router.post(
    "/tenants",
    response_model=dict[str, Any],
    status_code=status.HTTP_201_CREATED,
)
def create_tenant(
    payload: TenantCreateRequest,
    db: Session = Depends(get_current_internal_db),
    auth0_provisioning_service: Auth0ProvisioningService = Depends(
        get_auth0_provisioning_service
    ),
) -> dict:
    service = OnboardingService(db, auth0_provisioning_service)
    agents = [a.model_dump() for a in payload.agents]
    try:
        result = service.create_tenant(
            name=payload.name,
            slug=payload.slug,
            timezone=payload.timezone,
            status=payload.status,
            admin_name=payload.admin.name,
            admin_email=payload.admin.email,
            admin_role=payload.admin.role,
            agents=agents,
            plan=payload.plan,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except Auth0ProvisioningError as exc:
        status_code = (
            status.HTTP_409_CONFLICT
            if exc.status_code == status.HTTP_409_CONFLICT
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(
            status_code=status_code,
            detail=str(exc),
        ) from exc
    except OnboardingConsistencyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": str(exc),
                "auth0_user_id": exc.auth0_user_id,
                "compensation_attempted": exc.compensation_attempted,
                "compensation_succeeded": exc.compensation_succeeded,
            },
        ) from exc
    return result


@router.get("/tenants", response_model=list[dict[str, Any]])
def list_tenants(
    db: Session = Depends(get_current_internal_db),
) -> list[dict]:
    service = OnboardingService(db)
    usage_service = TenantUsageService(db)
    tenants = service.list_tenants()
    return [
        {
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "timezone": t.timezone,
            "status": t.status,
            "usage": usage_service.get_usage(t).model_dump(mode="json"),
        }
        for t in tenants
    ]

@router.get("/tenants/usage-summary", response_model=list[dict[str, Any]])
def list_tenants_usage_summary(
    db: Session = Depends(get_current_internal_db),
) -> list[dict]:
    return [
        item.model_dump(mode="json")
        for item in TenantUsageService(db).list_usage_summary()
    ]


@router.get("/usage-alerts", response_model=list[dict[str, Any]])
def list_usage_alerts(
    db: Session = Depends(get_current_internal_db),
) -> list[dict]:
    return [
        item.model_dump(mode="json")
        for item in TenantUsageService(db).list_usage_alerts()
    ]


@router.get("/tenants/{tenant_id}", response_model=dict[str, Any])
def get_tenant(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> dict:
    service = OnboardingService(db)
    usage_service = TenantUsageService(db)
    tenant = service.get_tenant(tenant_id)
    members = service.list_memberships(tenant_id)
    agents = service.list_agents(tenant_id)
    usage = usage_service.get_usage(tenant)
    savings = usage_service.get_savings_comparison(tenant)

    member_dicts = [
        {
            "id": m.id,
            "tenant_id": m.tenant_id,
            "user_id": m.user_id,
            "role": m.role,
            "status": m.status,
            "user_email": m.user.email if m.user else None,
            "user_name": m.user.name if m.user else None,
        }
        for m in members
    ]

    agent_dicts = [
        {
            "id": a.id,
            "tenant_id": a.tenant_id,
            "name": a.name,
            "external_provider": a.external_provider,
            "external_agent_id": a.external_agent_id,
            "channel_type": a.channel_type,
            "status": a.status,
        }
        for a in agents
    ]

    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "timezone": tenant.timezone,
        "status": tenant.status,
        "memberships": member_dicts,
        "agents": agent_dicts,
        "usage": usage.model_dump(mode="json"),
        "savings_comparison": savings.model_dump(mode="json"),
        "is_ready_for_calls": len(agent_dicts) > 0,
    }


@router.patch("/tenants/{tenant_id}", response_model=dict[str, Any])
def update_tenant(
    tenant_id: str,
    payload: TenantUpdateRequest,
    db: Session = Depends(get_current_internal_db),
) -> dict:
    service = OnboardingService(db)
    usage_service = TenantUsageService(db)
    tenant = service.update_tenant(
        tenant_id,
        name=payload.name,
        timezone=payload.timezone,
        status=payload.status,
    )
    members = service.list_memberships(tenant_id)
    agents = service.list_agents(tenant_id)
    usage = usage_service.get_usage(tenant)
    savings = usage_service.get_savings_comparison(tenant)

    member_dicts = [
        {
            "id": m.id,
            "tenant_id": m.tenant_id,
            "user_id": m.user_id,
            "role": m.role,
            "status": m.status,
            "user_email": m.user.email if m.user else None,
            "user_name": m.user.name if m.user else None,
        }
        for m in members
    ]

    agent_dicts = [
        {
            "id": a.id,
            "tenant_id": a.tenant_id,
            "name": a.name,
            "external_provider": a.external_provider,
            "external_agent_id": a.external_agent_id,
            "channel_type": a.channel_type,
            "status": a.status,
        }
        for a in agents
    ]

    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "timezone": tenant.timezone,
        "status": tenant.status,
        "memberships": member_dicts,
        "agents": agent_dicts,
        "usage": usage.model_dump(mode="json"),
        "savings_comparison": savings.model_dump(mode="json"),
        "is_ready_for_calls": len(agent_dicts) > 0,
    }


@router.get("/tenants/{tenant_id}/usage", response_model=dict[str, Any])
def get_tenant_usage(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> dict:
    service = OnboardingService(db)
    tenant = service.get_tenant(tenant_id)
    usage_service = TenantUsageService(db)
    usage = usage_service.get_usage(tenant)
    savings = usage_service.get_savings_comparison(tenant)
    return {
        "usage": usage.model_dump(mode="json"),
        "savings_comparison": savings.model_dump(mode="json"),
        "alerts": [
            alert.model_dump(mode="json")
            for alert in usage_service.list_usage_alerts(tenant_id)
        ],
    }


@router.patch("/tenants/{tenant_id}/plan", response_model=dict[str, Any])
def update_tenant_plan(
    tenant_id: str,
    payload: TenantPlanRequest,
    db: Session = Depends(get_current_internal_db),
) -> dict:
    usage_service = TenantUsageService(db)
    try:
        usage = usage_service.update_plan(tenant_id, payload)
        tenant = OnboardingService(db).get_tenant(tenant_id)
        savings = usage_service.get_savings_comparison(tenant)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return {
        "usage": usage.model_dump(mode="json"),
        "savings_comparison": savings.model_dump(mode="json"),
    }


@router.delete("/tenants/{tenant_id}", response_model=dict[str, Any])
def delete_tenant(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
    auth0_provisioning_service: Auth0ProvisioningService = Depends(
        get_auth0_provisioning_service
    ),
) -> dict:
    service = OnboardingService(db, auth0_provisioning_service)
    try:
        return service.delete_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except TenantDeletionBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except Auth0ProvisioningError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get("/tenants/{tenant_id}/memberships", response_model=list[dict[str, Any]])
def list_tenant_memberships(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> list[dict]:
    service = OnboardingService(db)
    memberships = service.list_memberships(tenant_id)
    return [
        {
            "id": m.id,
            "tenant_id": m.tenant_id,
            "user_id": m.user_id,
            "role": m.role,
            "status": m.status,
            "user_email": m.user.email if m.user else None,
            "user_name": m.user.name if m.user else None,
        }
        for m in memberships
    ]


@router.post(
    "/tenants/{tenant_id}/memberships",
    response_model=dict[str, Any],
    status_code=status.HTTP_201_CREATED,
)
def add_tenant_membership(
    tenant_id: str,
    payload: MembershipCreateRequest,
    db: Session = Depends(get_current_internal_db),
    auth0_provisioning_service: Auth0ProvisioningService = Depends(
        get_auth0_provisioning_service
    ),
) -> dict:
    service = OnboardingService(db, auth0_provisioning_service)
    try:
        membership = service.add_membership(
            tenant_id,
            email=payload.email,
            role=payload.role,
        )
    except ValueError as exc:
        if f"Tenant '{tenant_id}' not found" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return {
        "id": membership.id,
        "tenant_id": membership.tenant_id,
        "user_id": membership.user_id,
        "role": membership.role,
        "status": membership.status,
        "user_email": membership.user.email if membership.user else None,
        "user_name": membership.user.name if membership.user else None,
        "password_reset_url": getattr(membership, "password_reset_url", None),
    }


@router.post(
    "/tenants/{tenant_id}/memberships/{membership_id}/password-reset",
    response_model=dict[str, Any],
)
def send_membership_password_reset(
    tenant_id: str,
    membership_id: str,
    db: Session = Depends(get_current_internal_db),
    auth0_provisioning_service: Auth0ProvisioningService = Depends(
        get_auth0_provisioning_service
    ),
) -> dict:
    service = OnboardingService(db, auth0_provisioning_service)
    membership = service.get_membership(tenant_id, membership_id)
    if not membership or not membership.user or not membership.user.email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership or user not found",
        )

    email = membership.user.email
    # Ensure user is provisioned in Auth0
    if membership.user.external_auth_id is None:
        try:
            provisioned = auth0_provisioning_service.provision_tenant_admin(
                email=email,
                name=membership.user.name or email.split("@")[0],
            )
            membership.user.external_auth_id = provisioned.user_id
            db.commit()
        except Auth0ProvisioningError as exc:
            if exc.status_code != 409:
                logger.warning("Auth0 provisioning error on password reset: %s", exc)

    error_detail: str | None = None
    try:
        auth0_provisioning_service.trigger_password_reset_email(email=email)
    except Auth0ProvisioningError as exc:
        error_detail = str(exc)
        logger.warning("trigger_password_reset_email failed: %s", exc)

    ticket_url = None
    try:
        ticket_url = auth0_provisioning_service.create_password_change_ticket(email=email)
    except Exception as exc:
        logger.warning("create_password_change_ticket failed: %s", exc)

    if error_detail and not ticket_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo enviar el correo de contraseña: {error_detail}",
        )

    return {
        "success": True,
        "detail": f"Correo para configurar contraseña enviado a {email}",
        "password_reset_url": ticket_url,
    }


@router.delete(
    "/tenants/{tenant_id}/memberships/{membership_id}",
    response_model=dict[str, Any],
)
def delete_tenant_membership(
    tenant_id: str,
    membership_id: str,
    db: Session = Depends(get_current_internal_db),
) -> dict:
    service = OnboardingService(db)
    try:
        return service.delete_membership(tenant_id, membership_id)
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/tenants/{tenant_id}/agents", response_model=list[dict[str, Any]])
def list_tenant_agents(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> list[dict]:
    service = OnboardingService(db)
    agents = service.list_agents(tenant_id)
    return [
        {
            "id": a.id,
            "tenant_id": a.tenant_id,
            "name": a.name,
            "external_provider": a.external_provider,
            "external_agent_id": a.external_agent_id,
            "channel_type": a.channel_type,
            "status": a.status,
        }
        for a in agents
    ]


@router.post(
    "/tenants/{tenant_id}/agents",
    response_model=dict[str, Any],
    status_code=status.HTTP_201_CREATED,
)
def add_tenant_agent(
    tenant_id: str,
    payload: AgentCreateRequest,
    db: Session = Depends(get_current_internal_db),
) -> dict:
    service = OnboardingService(db)
    try:
        agent = service.add_agent(
            tenant_id,
            name=payload.name,
            external_provider=payload.external_provider,
            external_agent_id=payload.external_agent_id,
            channel_type=payload.channel_type,
            status=payload.status,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return {
        "id": agent.id,
        "tenant_id": agent.tenant_id,
        "name": agent.name,
        "external_provider": agent.external_provider,
        "external_agent_id": agent.external_agent_id,
        "channel_type": agent.channel_type,
        "status": agent.status,
    }


@router.get(
    "/tenants/{tenant_id}/integrations",
    response_model=list[ResendIntegrationConfigResponse],
)
def list_tenant_integrations_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        tenant = OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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


@router.get("/tenants/{tenant_id}/integrations/booking/config", response_model=BookingConfigResponse)
def get_tenant_booking_config_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return BookingConfigService(db).get_config_response(tenant_id)


@router.post("/tenants/{tenant_id}/integrations/calcom/config", response_model=BookingConfigResponse)
def configure_tenant_calcom_admin(
    tenant_id: str,
    body: BookingConfigRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
        config = BookingConfigService(db).upsert_calcom_config(tenant_id, body)
        IntegrationEventService(db).record_event(
            tenant_id=tenant_id,
            provider="calcom",
            event_type="config_updated",
            status="success",
            resource_type="config",
            resource_id=config.id,
            metadata={"has_secret": bool(config.cal_api_key_encrypted), "calendar_mode": config.calendar_mode},
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return BookingConfigService(db).get_config_response(tenant_id)


@router.post("/tenants/{tenant_id}/integrations/calcom/test", response_model=CalComTestResponse)
def test_tenant_calcom_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    try:
        result, error = BookingConfigService(db).test_connection(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result != "active":
        return CalComTestResponse(status=result, error_message=error or "Cal.com test failed.")
    return CalComTestResponse(status=result)


@router.get("/tenants/{tenant_id}/integrations/calcom/slots")
def get_tenant_calcom_slots_admin(
    tenant_id: str,
    date: str,
    jornada: str | None = None,
    reference_datetime: str | None = None,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
        return BookingService(db).get_available_slots_for_tenant(
            tenant_id=tenant_id,
            date_input=date,
            jornada=jornada,
            reference_datetime=reference_datetime,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/tenants/{tenant_id}/integrations/google-calendar/connections", response_model=list[GoogleCalendarConnectionResponse])
def list_tenant_google_calendar_connections_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    service = GoogleCalendarOAuthService(db)
    return [service.response(connection) for connection in service.list_connections(tenant_id)]


@router.delete("/tenants/{tenant_id}/integrations/google-calendar/connections/{connection_id}", response_model=dict[str, Any])
def delete_tenant_google_calendar_connection_admin(
    tenant_id: str,
    connection_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    service = GoogleCalendarOAuthService(db)
    try:
        service.delete_connection(tenant_id, connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"deleted": True, "connection_id": connection_id, "tenant_id": tenant_id}


@router.post("/tenants/{tenant_id}/crm/leads/{lead_id}/bookings", response_model=BookingResponse)
def create_tenant_lead_booking_admin(
    tenant_id: str,
    lead_id: str,
    body: BookingCreateRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
        return BookingService(db).create_lead_booking(tenant_id=tenant_id, lead_id=lead_id, body=body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/tenants/{tenant_id}/crm/leads/{lead_id}/bookings", response_model=list[BookingResponse])
def list_tenant_lead_bookings_admin(
    tenant_id: str,
    lead_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
        return BookingService(db).list_lead_bookings(tenant_id=tenant_id, lead_id=lead_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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


# --- Admin WhatsApp Config ---

@router.get(
    "/tenants/{tenant_id}/integrations/whatsapp/config",
    response_model=WhatsAppConfigResponse,
)
def get_tenant_whatsapp_config_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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
        OnboardingService(db).get_tenant(tenant_id)
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


# --- Admin Voice Config ---

@router.get(
    "/tenants/{tenant_id}/integrations/voice/config",
    response_model=VoiceProviderConfigResponse,
)
def get_tenant_voice_config_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return VoiceConfigService(db).get_config_response(tenant_id)


@router.post(
    "/tenants/{tenant_id}/integrations/voice/config",
    response_model=VoiceProviderConfigResponse,
)
def configure_tenant_voice_admin(
    tenant_id: str,
    body: VoiceProviderConfigRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
        config = VoiceConfigService(db).upsert_provider_config(tenant_id, body)
        return VoiceConfigService(db).get_config_response(tenant_id, config.provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/tenants/{tenant_id}/integrations/voice/test",
)
def test_tenant_voice_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    try:
        result, error = VoiceConfigService(db).test_connection(tenant_id)
        if result != "active":
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error or "Voice test failed.")
        return {"status": result}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# --- Admin Voice Agent ---

@router.get(
    "/tenants/{tenant_id}/integrations/voice/agents",
    response_model=list[VoiceAgentConfigResponse],
)
def list_tenant_voice_agents_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    service = VoiceAgentService(db)
    agents = service.list_agent_configs(tenant_id)
    return [service.response(agent) for agent in agents]


@router.post(
    "/tenants/{tenant_id}/integrations/voice/agents",
    response_model=VoiceAgentConfigResponse,
)
def create_tenant_voice_agent_admin(
    tenant_id: str,
    body: VoiceAgentConfigRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
        service = VoiceAgentService(db)
        agent = service.create_or_update_agent_config(tenant_id, body)
        return service.response(agent)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.put(
    "/tenants/{tenant_id}/integrations/voice/agents/{agent_config_id}",
    response_model=VoiceAgentConfigResponse,
)
def update_tenant_voice_agent_admin(
    tenant_id: str,
    agent_config_id: str,
    body: VoiceAgentConfigRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
        service = VoiceAgentService(db)
        agent = service.create_or_update_agent_config(tenant_id, body, agent_config_id)
        return service.response(agent)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
