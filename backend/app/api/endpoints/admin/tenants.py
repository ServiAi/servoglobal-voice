from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.modules.identity.api.deps import get_current_auth_context, get_identity_provisioning_port
from app.modules.identity.public import (
    AuthContext,
    IdentityAdminFacade,
    IdentityProviderError,
    IdentityProvisioningPort,
    MembershipNotFoundError,
    OnboardingConsistencyError,
    PasswordResetFailedError,
    ProvisioningConflictError,
    TenantDeletionBlockedError,
)
from app.db.session import get_db
from app.modules.identity.public import UserView as User
from app.modules.scheduling.public import (
    BookingConfigRequest,
    BookingConfigResponse,
    CalComTestResponse,
    CreateBookingCommand,
    GoogleCalendarConnectionResponse,
    SchedulingFacade,
)
from app.schemas.billing import TenantPlanRequest
from app.schemas.crm import BookingCreateRequest, BookingResponse
from app.schemas.integrations import (
    VoiceAgentConfigRequest,
    VoiceAgentConfigResponse,
    VoiceProviderConfigRequest,
    VoiceProviderConfigResponse,
)
from app.schemas.onboarding import (
    AgentCreateRequest,
    MembershipCreateRequest,
    TenantCreateRequest,
    TenantUpdateRequest,
)
from app.services.tenant_usage_service import TenantUsageService
from app.services.voice_agent_service import VoiceAgentService
from app.services.voice_config_service import VoiceConfigService

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



@router.post(
    "/tenants",
    response_model=dict[str, Any],
    status_code=status.HTTP_201_CREATED,
)
def create_tenant(
    payload: TenantCreateRequest,
    db: Session = Depends(get_current_internal_db),
    provisioning: IdentityProvisioningPort = Depends(get_identity_provisioning_port),
) -> dict:
    service = IdentityAdminFacade(db, provisioning)
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
    except (IdentityProviderError, ProvisioningConflictError) as exc:
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
    service = IdentityAdminFacade(db)
    usage_service = TenantUsageService(db)
    tenants = service.list_tenants()
    return [
        {
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "timezone": t.timezone,
            "status": t.status,
            "usage": usage_service.get_usage_for_tenant_id(t.id).model_dump(mode="json"),
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
    service = IdentityAdminFacade(db)
    usage_service = TenantUsageService(db)
    tenant = service.get_tenant(tenant_id)
    members = service.list_memberships(tenant_id)
    agents = service.list_agents(tenant_id)
    usage = usage_service.get_usage_for_tenant_id(tenant_id)
    savings = usage_service.get_savings_comparison_for_tenant_id(tenant_id)

    member_dicts = [
        {
            "id": m.id,
            "tenant_id": m.tenant_id,
            "user_id": m.user_id,
            "role": m.role,
            "status": m.status,
            "user_email": m.user_email,
            "user_name": m.user_name,
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
    service = IdentityAdminFacade(db)
    usage_service = TenantUsageService(db)
    tenant = service.update_tenant(
        tenant_id,
        name=payload.name,
        timezone=payload.timezone,
        status=payload.status,
    )
    members = service.list_memberships(tenant_id)
    agents = service.list_agents(tenant_id)
    usage = usage_service.get_usage_for_tenant_id(tenant_id)
    savings = usage_service.get_savings_comparison_for_tenant_id(tenant_id)

    member_dicts = [
        {
            "id": m.id,
            "tenant_id": m.tenant_id,
            "user_id": m.user_id,
            "role": m.role,
            "status": m.status,
            "user_email": m.user_email,
            "user_name": m.user_name,
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
    service = IdentityAdminFacade(db)
    tenant = service.get_tenant(tenant_id)
    usage_service = TenantUsageService(db)
    usage = usage_service.get_usage_for_tenant_id(tenant_id)
    savings = usage_service.get_savings_comparison_for_tenant_id(tenant_id)
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
        tenant = IdentityAdminFacade(db).get_tenant(tenant_id)
        savings = usage_service.get_savings_comparison_for_tenant_id(tenant_id)
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
    provisioning: IdentityProvisioningPort = Depends(get_identity_provisioning_port),
) -> dict:
    service = IdentityAdminFacade(db, provisioning)
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
    except (IdentityProviderError, ProvisioningConflictError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get("/tenants/{tenant_id}/memberships", response_model=list[dict[str, Any]])
def list_tenant_memberships(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> list[dict]:
    service = IdentityAdminFacade(db)
    memberships = service.list_memberships(tenant_id)
    return [
        {
            "id": m.id,
            "tenant_id": m.tenant_id,
            "user_id": m.user_id,
            "role": m.role,
            "status": m.status,
            "user_email": m.user_email,
            "user_name": m.user_name,
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
    provisioning: IdentityProvisioningPort = Depends(get_identity_provisioning_port),
) -> dict:
    service = IdentityAdminFacade(db, provisioning)
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
        "user_email": membership.user_email,
        "user_name": membership.user_name,
        "password_reset_url": membership.password_reset_url,
    }


@router.post(
    "/tenants/{tenant_id}/memberships/{membership_id}/password-reset",
    response_model=dict[str, Any],
)
def send_membership_password_reset(
    tenant_id: str,
    membership_id: str,
    db: Session = Depends(get_current_internal_db),
    provisioning: IdentityProvisioningPort = Depends(get_identity_provisioning_port),
) -> dict:
    try:
        result = IdentityAdminFacade(db, provisioning).send_membership_password_reset(tenant_id, membership_id)
    except MembershipNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PasswordResetFailedError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {
        "success": result.success,
        "detail": result.detail,
        "password_reset_url": result.ticket_url,
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
    service = IdentityAdminFacade(db)
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
    service = IdentityAdminFacade(db)
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
    service = IdentityAdminFacade(db)
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


@router.get("/tenants/{tenant_id}/integrations/booking/config", response_model=BookingConfigResponse)
def get_tenant_booking_config_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        IdentityAdminFacade(db).get_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return SchedulingFacade(db).get_booking_config(tenant_id)


@router.post("/tenants/{tenant_id}/integrations/calcom/config", response_model=BookingConfigResponse)
def configure_tenant_calcom_admin(
    tenant_id: str,
    body: BookingConfigRequest,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        IdentityAdminFacade(db).get_tenant(tenant_id)
        return SchedulingFacade(db).configure_calcom(tenant_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/tenants/{tenant_id}/integrations/calcom/test", response_model=CalComTestResponse)
def test_tenant_calcom_admin(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        IdentityAdminFacade(db).get_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    try:
        result, error = SchedulingFacade(db).test_calcom(tenant_id)
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
        IdentityAdminFacade(db).get_tenant(tenant_id)
        return SchedulingFacade(db).get_available_slots(
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
        IdentityAdminFacade(db).get_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return SchedulingFacade(db).list_google_connections(tenant_id)


@router.delete("/tenants/{tenant_id}/integrations/google-calendar/connections/{connection_id}", response_model=dict[str, Any])
def delete_tenant_google_calendar_connection_admin(
    tenant_id: str,
    connection_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        IdentityAdminFacade(db).get_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    try:
        SchedulingFacade(db).delete_google_connection(tenant_id, connection_id)
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
        IdentityAdminFacade(db).get_tenant(tenant_id)
        return SchedulingFacade(db).create_booking(
            tenant_id=tenant_id, lead_id=lead_id, command=CreateBookingCommand(**body.model_dump())
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/tenants/{tenant_id}/crm/leads/{lead_id}/bookings", response_model=list[BookingResponse])
def list_tenant_lead_bookings_admin(
    tenant_id: str,
    lead_id: str,
    db: Session = Depends(get_current_internal_db),
) -> Any:
    try:
        IdentityAdminFacade(db).get_tenant(tenant_id)
        return SchedulingFacade(db).list_lead_bookings(tenant_id=tenant_id, lead_id=lead_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# --- Admin WhatsApp Config ---

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
        IdentityAdminFacade(db).get_tenant(tenant_id)
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
        IdentityAdminFacade(db).get_tenant(tenant_id)
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
        IdentityAdminFacade(db).get_tenant(tenant_id)
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
        IdentityAdminFacade(db).get_tenant(tenant_id)
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
        IdentityAdminFacade(db).get_tenant(tenant_id)
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
        IdentityAdminFacade(db).get_tenant(tenant_id)
        service = VoiceAgentService(db)
        agent = service.create_or_update_agent_config(tenant_id, body, agent_config_id)
        return service.response(agent)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
