from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Mapping

from app.modules.identity.domain.contracts import (
    IdentityProvisioningPort,
    LegacyAgentView,
    ProvisionedUser,
)
from app.modules.identity.domain.errors import (
    FeatureDisabledError,
    IdentityProviderError,
    MembershipAlreadyExistsError,
    MembershipNotFoundError,
    OnboardingConsistencyError,
    PasswordResetFailedError,
    ProvisioningConflictError,
    TenantDeletionBlockedError,
    TenantFeatureTenantNotFoundError,
    TenantNotFoundError,
    UnknownTenantFeatureError,
)
from app.modules.identity.domain.features import (
    AGENT_BUILDER,
    CUSTOM_HTTP_TOOLS,
    LIVEKIT_SIP_OUTBOUND_V2,
    SUPPORTED_FEATURES,
    VOICE_EXPERIENCES,
    VOICE_RUNTIME_V2,
    WHATSAPP_BUSINESS_CALLING,
)

__all__ = [
    "AGENT_BUILDER", "AccessAudit", "AdminMembershipView", "AuthContext", "CUSTOM_HTTP_TOOLS",
    "FeatureDisabledError", "FeatureFlags", "FeatureGrantView", "IdentityAdminFacade", "IdentityFacade",
    "IdentityProviderError", "IdentityProvisioningPort", "LIVEKIT_SIP_OUTBOUND_V2", "LegacyAgentView",
    "MembershipAlreadyExistsError", "MembershipDirectory", "MembershipNotFoundError", "MembershipView",
    "OnboardingConsistencyError", "PasswordResetFailedError", "PasswordResetResult", "ProvisionedUser",
    "ProvisioningConflictError", "SUPPORTED_FEATURES", "TenantDeletionBlockedError", "TenantDirectory",
    "TenantFeatureTenantNotFoundError", "TenantLifecycle", "TenantNotFoundError", "TenantView",
    "UnknownTenantFeatureError", "UserView", "VOICE_EXPERIENCES", "VOICE_RUNTIME_V2",
    "WHATSAPP_BUSINESS_CALLING",
]
# Deliberately NOT exported: IdentityService, create_onboarding_service, wiring factories and the HTTP
# dependencies (get_current_auth_context, require_roles, ...). Those are Identity internals; HTTP routers import
# the dependencies from ``app.modules.identity.api.deps``.


def _view(model, view_type):
    return view_type(**{name: getattr(model, name) for name in view_type.__dataclass_fields__})


@dataclass(frozen=True)
class TenantView:
    id: str
    name: str
    slug: str
    timezone: str
    status: str


@dataclass(frozen=True)
class UserView:
    id: str
    email: str
    name: str | None
    is_internal: bool
    status: str


@dataclass(frozen=True)
class MembershipView:
    id: str | None
    tenant_id: str
    user_id: str
    role: str
    status: str


@dataclass(frozen=True)
class FeatureGrantView:
    feature_key: str
    enabled: bool
    limits: Mapping[str, object]
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "limits", MappingProxyType(dict(self.limits)))


@dataclass(frozen=True)
class AuthContext:
    user: UserView
    tenant: TenantView
    membership: MembershipView

    @property
    def tenant_id(self) -> str:
        return self.tenant.id

    @property
    def role(self) -> str:
        return self.membership.role


@dataclass(frozen=True)
class PasswordResetResult:
    success: bool
    detail: str
    ticket_url: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class AdminMembershipView:
    id: str
    tenant_id: str
    user_id: str
    role: str
    status: str
    user_email: str | None
    user_name: str | None
    password_reset_url: str | None = field(default=None, repr=False)


class FeatureFlags:
    def __init__(self, db: object) -> None:
        self.db = db

    def is_enabled(self, tenant_id: str, feature_key: str) -> bool:
        from app.modules.identity.application.feature_service import (
            TenantFeatureService,
        )
        return TenantFeatureService(self.db).is_enabled(tenant_id, feature_key)

    def require_enabled(self, tenant_id: str, feature_key: str) -> FeatureGrantView:
        from app.modules.identity.application.feature_service import (
            TenantFeatureService,
        )
        grant = TenantFeatureService(self.db).require_enabled(tenant_id, feature_key)
        return _feature_view(grant)

    def list_features(self, tenant_id: str) -> tuple[FeatureGrantView, ...]:
        from app.modules.identity.application.feature_service import (
            TenantFeatureService,
        )
        return tuple(_feature_view(item) for item in TenantFeatureService(self.db).list_features(tenant_id))

    def set_feature(
        self, tenant_id: str, feature_key: str, enabled: bool,
        limits: Mapping[str, object], enabled_by_user_id: str | None,
    ) -> FeatureGrantView:
        from app.modules.identity.application.feature_service import (
            TenantFeatureService,
        )
        grant = TenantFeatureService(self.db).set_feature(
            tenant_id, feature_key, enabled, limits, enabled_by_user_id
        )
        return _feature_view(grant)


def _feature_view(grant) -> FeatureGrantView:
    return FeatureGrantView(
        feature_key=grant.feature_key,
        enabled=grant.enabled,
        limits=grant.limits_json,
        created_at=grant.created_at,
        updated_at=grant.updated_at,
    )


class MembershipDirectory:
    """Tenant scoped membership queries; never returns ORM instances."""

    def __init__(self, db: object) -> None:
        self.db = db

    def is_active_member(self, tenant_id: str, user_id: str) -> bool:
        return self.get(tenant_id, user_id=user_id, active_only=True) is not None

    def get(self, tenant_id: str, *, user_id: str | None = None,
            membership_id: str | None = None, active_only: bool = False) -> MembershipView | None:
        from sqlalchemy import select

        from app.modules.identity.infrastructure.models import TenantMembership
        query = select(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
        if membership_id is not None:
            query = query.where(TenantMembership.id == membership_id)
        if user_id is not None:
            query = query.where(TenantMembership.user_id == user_id)
        if active_only:
            query = query.where(TenantMembership.status == "active")
        membership = self.db.scalar(query)
        return _view(membership, MembershipView) if membership is not None else None

    def list(self, tenant_id: str) -> tuple[MembershipView, ...]:
        from sqlalchemy import select

        from app.modules.identity.infrastructure.models import TenantMembership
        memberships = self.db.scalars(
            select(TenantMembership)
            .where(TenantMembership.tenant_id == tenant_id)
            .order_by(TenantMembership.created_at.desc())
        ).all()
        return tuple(_view(item, MembershipView) for item in memberships)


class TenantDirectory:
    def __init__(self, db: object) -> None:
        self.db = db

    def get(self, tenant_id: str) -> TenantView | None:
        from app.modules.identity.infrastructure.models import Tenant
        tenant = self.db.get(Tenant, tenant_id)
        return _view(tenant, TenantView) if tenant is not None else None

    def get_by_slug(self, slug: str) -> TenantView | None:
        from sqlalchemy import select

        from app.modules.identity.infrastructure.models import Tenant
        tenant = self.db.scalar(select(Tenant).where(Tenant.slug == slug))
        return _view(tenant, TenantView) if tenant is not None else None

    def require(self, tenant_id: str) -> TenantView:
        tenant = self.get(tenant_id)
        if tenant is None:
            raise LookupError(f"Tenant '{tenant_id}' not found")
        return tenant

    def exists(self, tenant_id: str) -> bool:
        from sqlalchemy import select

        from app.modules.identity.infrastructure.models import Tenant
        return self.db.scalar(select(Tenant.id).where(Tenant.id == tenant_id)) is not None

    def bootstrap(self) -> TenantView:
        from app.modules.identity.application.authentication_service import (
            IdentityService,
        )
        return _view(IdentityService(self.db).bootstrap_tenant(), TenantView)


class TenantLifecycle:
    def __init__(self, db: object) -> None:
        self.db = db

    def set_usage_suspension(
        self, tenant_id: str, suspended: bool, *, commit: bool = True
    ) -> TenantView:
        from app.modules.identity.application.tenant_service import TenantService
        return TenantService(self.db).set_usage_suspension(tenant_id, suspended, commit=commit)


class AccessAudit:
    def __init__(self, db: object) -> None:
        self.db = db

    def record(self, **entry: str | None) -> None:
        from app.modules.identity.application.audit_service import AuditService
        AuditService(self.db).record(**entry)


class IdentityFacade:
    """Lazy entry points for identity operations used by other modules."""

    def __init__(self, db: object) -> None:
        self.db = db

    def membership_directory(self) -> MembershipDirectory:
        return MembershipDirectory(self.db)

    def tenant_directory(self) -> TenantDirectory:
        return TenantDirectory(self.db)


class IdentityAdminFacade:
    def __init__(self, db: object, provisioning: IdentityProvisioningPort | None = None) -> None:
        self.db = db
        self._provisioning = provisioning

    def _service(self):
        from app.modules.identity.wiring import create_onboarding_service
        return create_onboarding_service(self.db, self._provisioning)

    @staticmethod
    def _membership_view(membership) -> AdminMembershipView:
        user = membership.user
        return AdminMembershipView(
            id=membership.id,
            tenant_id=membership.tenant_id,
            user_id=membership.user_id,
            role=membership.role,
            status=membership.status,
            user_email=user.email if user else None,
            user_name=user.name if user else None,
            password_reset_url=getattr(membership, "password_reset_url", None),
        )

    def create_tenant(self, **values: object) -> Mapping[str, object]:
        return self._service().create_tenant(**values)

    def list_tenants(self) -> tuple[TenantView, ...]:
        return tuple(_view(item, TenantView) for item in self._service().list_tenants())

    def get_tenant(self, tenant_id: str) -> TenantView:
        return _view(self._service().get_tenant(tenant_id), TenantView)

    def update_tenant(self, tenant_id: str, **values: object) -> TenantView:
        return _view(self._service().update_tenant(tenant_id, **values), TenantView)

    def delete_tenant(self, tenant_id: str) -> Mapping[str, object]:
        return self._service().delete_tenant(tenant_id)

    def list_memberships(self, tenant_id: str) -> tuple[AdminMembershipView, ...]:
        return tuple(self._membership_view(item) for item in self._service().list_memberships(tenant_id))

    def get_membership(self, tenant_id: str, membership_id: str) -> AdminMembershipView | None:
        membership = self._service().get_membership(tenant_id, membership_id)
        return self._membership_view(membership) if membership is not None else None

    def add_membership(self, tenant_id: str, *, email: str, role: str = "tenant_analyst") -> AdminMembershipView:
        return self._membership_view(self._service().add_membership(tenant_id, email=email, role=role))

    def delete_membership(self, tenant_id: str, membership_id: str) -> Mapping[str, object]:
        return self._service().delete_membership(tenant_id, membership_id)

    def add_agent(self, tenant_id: str, **values: object) -> LegacyAgentView:
        return self._service().add_agent(tenant_id, **values)

    def list_agents(self, tenant_id: str) -> tuple[LegacyAgentView, ...]:
        return self._service().list_agents(tenant_id)

    def send_membership_password_reset(self, tenant_id: str, membership_id: str) -> PasswordResetResult:
        """Raises ``MembershipNotFoundError`` or ``PasswordResetFailedError``; never exposes provider details."""
        outcome = self._service().send_membership_password_reset(tenant_id, membership_id)
        return PasswordResetResult(
            success=True,
            detail=f"Correo para configurar contraseña enviado a {outcome.email}",
            ticket_url=outcome.ticket_url,
        )
