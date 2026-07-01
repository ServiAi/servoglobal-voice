from __future__ import annotations

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
    GoogleCalendarConnectionResponse,
    ResendIntegrationConfigRequest,
    ResendIntegrationConfigResponse,
    ResendTestEmailRequest,
    ResendTestEmailResponse,
)
from app.schemas.crm import BookingCreateRequest, BookingResponse
from app.api.endpoints.integrations import _resend_response
from app.services.booking_config_service import BookingConfigService
from app.services.booking_service import BookingService
from app.services.email_config_service import EmailConfigService
from app.services.email_send_service import EmailSendService
from app.services.email_template_service import EmailTemplateService
from app.services.google_calendar_oauth_service import GoogleCalendarOAuthService
from app.services.integration_event_service import IntegrationEventService
from app.services.integration_service import IntegrationService


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
) -> dict:
    service = OnboardingService(db)
    try:
        membership = service.add_membership(
            tenant_id,
            email=payload.email,
            role=payload.role,
        )
    except ValueError as exc:
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
    }


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
    result, error = BookingConfigService(db).test_connection(tenant_id)
    if result != "active":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error or "Cal.com test failed.")
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
