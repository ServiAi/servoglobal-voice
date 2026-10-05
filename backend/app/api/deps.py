from fastapi import HTTPException
import httpx
from app.core.config import settings

async def verify_turnstile(token: str):
    secret_key = settings.TURNSTILE_SECRET_KEY
    if not secret_key:
        print("WARNING: TURNSTILE_SECRET_KEY not set. Skipping verification.")
        return

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": secret_key, "response": token},
        )
        result = response.json()
        if not result.get("success"):
            raise HTTPException(status_code=400, detail="Invalid Turnstile token")


def require_enabled_integration(provider: str, roles: list[str]):
    """Role check plus the tenant's on/off switch for ``provider`` (Integrations catalog)."""
    from fastapi import Depends, status
    from sqlalchemy.orm import Session

    from app.api.auth.deps import AuthContext, require_roles
    from app.db.session import get_db
    from app.modules.integrations.public import IntegrationsFacade

    role_dependency = require_roles(roles)

    def dependency(
        context: AuthContext = Depends(role_dependency),
        db: Session = Depends(get_db),
    ) -> AuthContext:
        if not IntegrationsFacade(db).is_enabled(context.tenant.id, provider):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration is not enabled for this tenant.")
        return context

    return dependency
