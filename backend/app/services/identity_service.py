from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.identity import AccessAuditLog, Tenant, TenantMembership, User
from app.services.auth0_service import AuthenticatedIdentity


ACTIVE = "active"


class IdentityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve_user(self, identity: AuthenticatedIdentity) -> User:
        user = self.db.scalar(
            select(User).where(User.external_auth_id == identity.external_auth_id)
        )
        if user is None:
            if not settings.AUTH0_AUTO_CREATE_USERS:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Authenticated user is not registered internally",
                )
            user = User(
                external_auth_id=identity.external_auth_id,
                email=identity.email,
                name=identity.name,
                is_internal=False,
                status=ACTIVE,
                last_login_at=datetime.now(UTC),
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            return user

        if user.status != ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authenticated user is not active",
            )

        user.email = identity.email
        user.name = identity.name or user.name
        user.last_login_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(user)
        return user

    def resolve_active_membership(self, user: User) -> TenantMembership:
        membership = self.db.scalar(
            select(TenantMembership)
            .options(joinedload(TenantMembership.tenant))
            .where(
                TenantMembership.user_id == user.id,
                TenantMembership.status == ACTIVE,
            )
            .join(Tenant)
            .where(Tenant.status == ACTIVE)
            .order_by(TenantMembership.created_at.asc())
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authenticated user has no active tenant membership",
            )
        return membership

    def audit_access(
        self,
        *,
        user_id: str | None,
        tenant_id: str | None,
        action: str,
        resource: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.db.add(
            AccessAuditLog(
                user_id=user_id,
                tenant_id=tenant_id,
                action=action,
                resource=resource,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        self.db.commit()
