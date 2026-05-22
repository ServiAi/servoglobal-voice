from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.session import get_db
from app.models.identity import User
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
from app.services.onboarding_service import OnboardingConsistencyError, OnboardingService


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
    tenants = service.list_tenants()
    return [
        {
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "timezone": t.timezone,
            "status": t.status,
        }
        for t in tenants
    ]


@router.get("/tenants/{tenant_id}", response_model=dict[str, Any])
def get_tenant(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> dict:
    service = OnboardingService(db)
    tenant = service.get_tenant(tenant_id)
    members = service.list_memberships(tenant_id)
    agents = service.list_agents(tenant_id)

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
        "is_ready_for_calls": len(agent_dicts) > 0,
    }


@router.patch("/tenants/{tenant_id}", response_model=dict[str, Any])
def update_tenant(
    tenant_id: str,
    payload: TenantUpdateRequest,
    db: Session = Depends(get_current_internal_db),
) -> dict:
    service = OnboardingService(db)
    tenant = service.update_tenant(
        tenant_id,
        name=payload.name,
        timezone=payload.timezone,
        status=payload.status,
    )
    members = service.list_memberships(tenant_id)
    agents = service.list_agents(tenant_id)

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
        "is_ready_for_calls": len(agent_dicts) > 0,
    }


@router.delete("/tenants/{tenant_id}", response_model=dict[str, Any])
def delete_tenant(
    tenant_id: str,
    db: Session = Depends(get_current_internal_db),
) -> dict:
    service = OnboardingService(db)
    try:
        return service.delete_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
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
