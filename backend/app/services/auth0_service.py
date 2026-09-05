from __future__ import annotations

from dataclasses import dataclass

import logging
import httpx
import jwt
from fastapi import HTTPException, status
from jwt import PyJWKClient

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedIdentity:
    external_auth_id: str
    email: str | None = None
    name: str | None = None
    email_verified: bool | None = None
    claims: dict | None = None


class Auth0TokenVerifier:
    def __init__(self) -> None:
        self._jwks_client: PyJWKClient | None = None

    @property
    def issuer(self) -> str:
        if settings.AUTH0_ISSUER:
            return settings.AUTH0_ISSUER
        if not settings.AUTH0_DOMAIN:
            return ""
        return f"https://{settings.AUTH0_DOMAIN.rstrip('/')}/"

    @property
    def jwks_url(self) -> str:
        domain = settings.AUTH0_DOMAIN.rstrip("/")
        return f"https://{domain}/.well-known/jwks.json"

    def verify(self, token: str) -> AuthenticatedIdentity:
        if not settings.AUTH0_DOMAIN or not settings.AUTH0_AUDIENCE:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Auth0 backend configuration is incomplete",
            )

        try:
            jwks_client = self._get_jwks_client()
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=self._algorithms(),
                audience=settings.AUTH0_AUDIENCE,
                issuer=self.issuer,
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        external_auth_id = claims.get("sub")
        email = (
            claims.get("email")
            or claims.get("https://serviglobal-ia.com/email")
            or claims.get("https://serviglobal.co/email")
        )
        name = claims.get("name") or claims.get("nickname")
        email_verified = (
            claims.get("email_verified")
            if "email_verified" in claims
            else claims.get("https://serviglobal-ia.com/email_verified")
        )

        if not external_auth_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token is missing required identity claims",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not email and settings.AUTH0_DOMAIN:
            try:
                domain = settings.AUTH0_DOMAIN.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
                resp = httpx.get(
                    f"https://{domain}/userinfo",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    info = resp.json()
                    email = info.get("email")
                    name = name or info.get("name") or info.get("nickname")
                    if email_verified is None:
                        email_verified = info.get("email_verified")
            except Exception as exc:
                logger.debug("Failed to fetch userinfo from Auth0: %s", exc)

        return AuthenticatedIdentity(
            external_auth_id=external_auth_id,
            email=email,
            name=name,
            email_verified=email_verified,
            claims=claims,
        )

    def _get_jwks_client(self) -> PyJWKClient:
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(self.jwks_url)
        return self._jwks_client

    def _algorithms(self) -> list[str]:
        return [algorithm.strip() for algorithm in settings.AUTH0_ALGORITHMS.split(",") if algorithm.strip()]


auth0_verifier = Auth0TokenVerifier()
