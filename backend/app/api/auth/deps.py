from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.identity import Tenant, TenantMembership, User
from app.services.auth0_service import AuthenticatedIdentity, auth0_verifier
from app.services.identity_service import IdentityService


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    tenant: Tenant
    membership: TenantMembership

    @property
    def role(self) -> str:
        return self.membership.role


async def get_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedIdentity:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth0_verifier.verify(credentials.credentials)


def get_current_auth_context(
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> AuthContext:
    identity_service = IdentityService(db)
    user = identity_service.resolve_user(identity)
    membership = identity_service.resolve_active_membership(user)
    return AuthContext(user=user, tenant=membership.tenant, membership=membership)


def get_current_user(context: AuthContext = Depends(get_current_auth_context)) -> User:
    return context.user


def get_current_tenant(context: AuthContext = Depends(get_current_auth_context)) -> Tenant:
    return context.tenant


def get_current_role(context: AuthContext = Depends(get_current_auth_context)) -> str:
    return context.role
