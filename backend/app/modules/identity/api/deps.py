from collections.abc import Callable, Collection
from typing import TypeVar

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.identity.application.authentication_service import IdentityService
from app.modules.identity.domain.contracts import ExternalIdentity
from app.modules.identity.domain.roles import PLATFORM_ADMIN
from app.modules.identity.infrastructure.auth0.verifier import auth0_verifier
from app.modules.identity.public import (
    AuthContext,
    MembershipView,
    TenantDirectory,
    TenantView,
    UserView,
)

bearer_scheme = HTTPBearer(auto_error=False)
T = TypeVar("T")


def get_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> ExternalIdentity:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth0_verifier.verify(credentials.credentials)


def get_current_auth_context(
    identity: ExternalIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> AuthContext:
    identity_service = IdentityService(db)
    user = identity_service.resolve_user(identity)
    user_view = UserView(
        id=user.id,
        email=user.email,
        name=user.name,
        is_internal=user.is_internal,
        status=user.status,
    )
    if user.is_internal:
        tenant = TenantDirectory(db).bootstrap()
        membership = MembershipView(
            id=None,
            tenant_id=tenant.id,
            user_id=user.id,
            role=PLATFORM_ADMIN,
            status="active",
        )
        return AuthContext(user=user_view, tenant=tenant, membership=membership)

    membership_model = identity_service.resolve_active_membership(user)
    tenant_model = membership_model.tenant
    tenant = TenantView(
        id=tenant_model.id,
        name=tenant_model.name,
        slug=tenant_model.slug,
        timezone=tenant_model.timezone,
        status=tenant_model.status,
    )
    membership = MembershipView(
        id=membership_model.id,
        tenant_id=membership_model.tenant_id,
        user_id=membership_model.user_id,
        role=membership_model.role,
        status=membership_model.status,
    )
    return AuthContext(user=user_view, tenant=tenant, membership=membership)


def get_current_user(
    context: AuthContext = Depends(get_current_auth_context),
) -> UserView:
    return context.user


def get_current_tenant(
    context: AuthContext = Depends(get_current_auth_context),
) -> TenantView:
    return context.tenant


def get_current_role(
    context: AuthContext = Depends(get_current_auth_context),
) -> str:
    return context.role


def require_roles(roles: Collection[str]) -> Callable[..., T]:
    def dependency(context: AuthContext = Depends(get_current_auth_context)) -> AuthContext:
        if context.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return context
    return dependency


def get_current_internal_user(
    context: AuthContext = Depends(get_current_auth_context),
) -> UserView:
    if not context.user.is_internal:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal platform access required",
        )
    return context.user



def get_identity_provisioning_port():
    from app.modules.identity.wiring import create_provisioning_adapter
    return create_provisioning_adapter()
