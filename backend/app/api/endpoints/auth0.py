"""Auth0 redirect endpoint — handles post-login/password-reset redirects.

This endpoint is called by Auth0 after password reset or first login.
It redirects to the internal login page instead of the public landing.
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse

from app.core.config import settings

router = APIRouter(tags=["auth0"])


@router.get("/api/auth0/redirect")
async def auth0_redirect(request: Request) -> RedirectResponse:
    """Redirect to internal login after Auth0 password reset or first login.

    Auth0 calls this endpoint as the post-login redirect URI.
    Instead of sending the user to the public landing page,
    it sends them to /es/login to authenticate with their new credentials.
    """
    return RedirectResponse(
        url=f"/es/login",
        status_code=302,
    )
