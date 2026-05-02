from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.session import get_db
from app.schemas.me import MeResponse
from app.services.identity_service import IdentityService

router = APIRouter(prefix="/api/v1", tags=["Private"])


@router.get("/me", response_model=MeResponse)
def get_me(
    request: Request,
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> MeResponse:
    IdentityService(db).audit_access(
        user_id=context.user.id,
        tenant_id=context.tenant.id,
        action="profile_view",
        resource="/api/v1/me",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return MeResponse(
        user_id=context.user.id,
        email=context.user.email,
        name=context.user.name,
        tenant_id=context.tenant.id,
        tenant_name=context.tenant.name,
        role=context.role,
        is_internal=context.user.is_internal,
    )
