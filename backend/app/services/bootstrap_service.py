from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.identity import Tenant, TenantMembership, User


ACTIVE = "active"


@dataclass(frozen=True)
class BootstrapResult:
    tenant_id: str
    user_id: str
    membership_id: str
    created_tenant: bool
    created_user: bool
    created_membership: bool


class BootstrapConfigurationError(ValueError):
    pass


class IdentityBootstrapService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def run_initial_bootstrap(self) -> BootstrapResult:
        if not settings.BOOTSTRAP_USER_AUTH0_SUB or not settings.BOOTSTRAP_USER_EMAIL:
            raise BootstrapConfigurationError(
                "BOOTSTRAP_USER_AUTH0_SUB and BOOTSTRAP_USER_EMAIL are required"
            )

        tenant, created_tenant = self._get_or_create_tenant()
        user, created_user = self._get_or_create_user()
        membership, created_membership = self._get_or_create_membership(tenant, user)
        self.db.commit()
        return BootstrapResult(
            tenant_id=tenant.id,
            user_id=user.id,
            membership_id=membership.id,
            created_tenant=created_tenant,
            created_user=created_user,
            created_membership=created_membership,
        )

    def _get_or_create_tenant(self) -> tuple[Tenant, bool]:
        tenant = self.db.scalar(
            select(Tenant).where(Tenant.slug == settings.BOOTSTRAP_TENANT_SLUG)
        )
        if tenant is not None:
            tenant.name = settings.BOOTSTRAP_TENANT_NAME
            tenant.timezone = settings.BOOTSTRAP_TENANT_TIMEZONE
            tenant.status = ACTIVE
            return tenant, False

        tenant = Tenant(
            name=settings.BOOTSTRAP_TENANT_NAME,
            slug=settings.BOOTSTRAP_TENANT_SLUG,
            timezone=settings.BOOTSTRAP_TENANT_TIMEZONE,
            status=ACTIVE,
        )
        self.db.add(tenant)
        self.db.flush()
        return tenant, True

    def _get_or_create_user(self) -> tuple[User, bool]:
        user = self.db.scalar(
            select(User).where(User.external_auth_id == settings.BOOTSTRAP_USER_AUTH0_SUB)
        )
        if user is not None:
            user.email = settings.BOOTSTRAP_USER_EMAIL
            user.name = settings.BOOTSTRAP_USER_NAME or user.name
            user.status = ACTIVE
            return user, False

        user = User(
            external_auth_id=settings.BOOTSTRAP_USER_AUTH0_SUB,
            email=settings.BOOTSTRAP_USER_EMAIL,
            name=settings.BOOTSTRAP_USER_NAME or None,
            is_internal=True,
            status=ACTIVE,
        )
        self.db.add(user)
        self.db.flush()
        return user, True

    def _get_or_create_membership(
        self, tenant: Tenant, user: User
    ) -> tuple[TenantMembership, bool]:
        membership = self.db.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant.id,
                TenantMembership.user_id == user.id,
            )
        )
        if membership is not None:
            membership.role = settings.BOOTSTRAP_USER_ROLE
            membership.status = ACTIVE
            return membership, False

        membership = TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=settings.BOOTSTRAP_USER_ROLE,
            status=ACTIVE,
        )
        self.db.add(membership)
        self.db.flush()
        return membership, True
