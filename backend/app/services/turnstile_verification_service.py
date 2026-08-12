from __future__ import annotations

import httpx

from app.core.config import settings


class TurnstileVerificationService:
    VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

    def __init__(self, *, secret: str | None = None, timeout_seconds: float = 5.0) -> None:
        self.secret = settings.TURNSTILE_SECRET_KEY if secret is None else secret
        self.timeout_seconds = timeout_seconds

    async def verify(self, token: str | None, remote_ip: str) -> bool:
        if not token or not self.secret:
            return False
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self.VERIFY_URL,
                    data={"secret": self.secret, "response": token, "remoteip": remote_ip},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            return False
        return payload.get("success") is True
