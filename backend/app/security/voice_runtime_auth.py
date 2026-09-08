from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

runtime_bearer = HTTPBearer(auto_error=False)


def create_runtime_token(*, ttl_seconds: int = 60) -> str:
    if not settings.VOICE_RUNTIME_SERVICE_SECRET:
        raise RuntimeError("VOICE_RUNTIME_SERVICE_SECRET is not configured")
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"iss": settings.VOICE_RUNTIME_JWT_ISSUER, "aud": settings.VOICE_RUNTIME_JWT_AUDIENCE, "sub": "voice-runtime", "iat": now, "exp": now + timedelta(seconds=ttl_seconds)},
        settings.VOICE_RUNTIME_SERVICE_SECRET,
        algorithm="HS256",
    )


def require_voice_runtime(credentials: HTTPAuthorizationCredentials | None = Depends(runtime_bearer)) -> None:
    if credentials is None or credentials.scheme.lower() != "bearer" or not settings.VOICE_RUNTIME_SERVICE_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Runtime authentication required")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.VOICE_RUNTIME_SERVICE_SECRET,
            algorithms=["HS256"],
            issuer=settings.VOICE_RUNTIME_JWT_ISSUER,
            audience=settings.VOICE_RUNTIME_JWT_AUDIENCE,
            options={"require": ["iss", "aud", "iat", "exp", "sub"]},
        )
        if payload.get("sub") != "voice-runtime":
            raise jwt.InvalidTokenError("invalid subject")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid runtime authentication") from exc
