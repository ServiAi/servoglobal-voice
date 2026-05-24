from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import re

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.identity import AccessAuditLog, Tenant, TenantMembership, User
from app.services.auth0_service import AuthenticatedIdentity


ACTIVE = "active"
FALLBACK_EMAIL_DOMAIN = "auth0.local"


def _fallback_email(external_auth_id: str) -> str:
    compact_sub = re.sub(r"[^a-zA-Z0-9]+", "-", external_auth_id).strip("-").lower()
    digest = sha256(external_auth_id.encode("utf-8")).hexdigest()[:12]
    local_part = compact_sub[:40] or "auth0-user"
    return f"{local_part}-{digest}@{FALLBACK_EMAIL_DOMAIN}"


class IdentityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve_user(self, identity: AuthenticatedIdentity) -> User:
        # Step 1: Try exact match by external_auth_id (highest priority)
        user = self.db.scalar(
            select(User).where(User.external_auth_id == identity.external_auth_id)
        )
        if user is not None:
            if identity.email_verified is False:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Email not verified. Please verify your email before logging in.",
                )
            self._update_user_from_identity(user, identity)
            return user

        # Step 2: If no external_auth_id match, try to resolve by email
        if identity.email:
            user = self._resolve_user_by_email_strict(identity)
            if user is not None:
                return user

        # Step 3: No match found — either create new or reject
        if not settings.AUTH0_AUTO_CREATE_USERS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authenticated user is not registered internally",
            )

        email = identity.email or _fallback_email(identity.external_auth_id)
        user = User(
            external_auth_id=identity.external_auth_id,
            email=email,
            name=identity.name,
            is_internal=False,
            status=ACTIVE,
            last_login_at=datetime.now(UTC),
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def _resolve_user_by_email_strict(self, identity: AuthenticatedIdentity) -> User | None:
        """Resolve a user by email with strict ambiguity detection.

        Rules:
        1. If exactly one active user exists with this email:
           - If it already has external_auth_id, return it (already linked)
           - If external_auth_id is NULL, link it (first login)
        2. If multiple active users share this email, raise 409 explicitly.
        3. If no user exists, return None (caller will create new or reject).
        """
        # Find ALL active users with this email
        matching_users = self.db.scalars(
            select(User).where(User.email == identity.email)
        ).all()

        if len(matching_users) == 0:
            return None

        if len(matching_users) > 1:
            # AMBIGUITY: multiple active users with same email
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Multiple active users found with email '{identity.email}'. "
                    "Manual resolution required to merge or disambiguate accounts."
                ),
            )

        # Exactly one match
        user = matching_users[0]

        if user.status != ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authenticated user is not active",
            )

        if identity.email_verified is False:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified. Please verify your email before logging in.",
            )

        # If already linked to a different sub, return as-is (don't overwrite)
        if user.external_auth_id is not None:
            return user

        # Link the Auth0 sub to this pre-provisioned user
        user.external_auth_id = identity.external_auth_id
        user.name = identity.name or user.name
        user.last_login_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(user)
        return user

    def _update_user_from_identity(self, user: User, identity: AuthenticatedIdentity) -> None:
        """Update user fields from Auth0 identity after a successful match."""
        if user.status != ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authenticated user is not active",
            )

        if identity.email:
            user.email = identity.email
        user.name = identity.name or user.name
        user.last_login_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(user)

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

    def bootstrap_tenant(self) -> Tenant:
        tenant = self.db.scalar(
            select(Tenant).where(Tenant.slug == settings.BOOTSTRAP_TENANT_SLUG)
        )
        if tenant is None:
            tenant = Tenant(
                name=settings.BOOTSTRAP_TENANT_NAME,
                slug=settings.BOOTSTRAP_TENANT_SLUG,
                timezone=settings.BOOTSTRAP_TENANT_TIMEZONE,
                status=ACTIVE,
            )
            self.db.add(tenant)
            self.db.commit()
            self.db.refresh(tenant)
        return tenant

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
