from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import jwt

from .config import Settings
from .contracts import RuntimeEventV1, RuntimeSessionSpecV1
from .credentials import (
    ProviderCredential,
    ProviderCredentialNotConfiguredError,
    ProviderCredentialSessionNotFoundError,
    ProviderCredentialUnavailableError,
    ProviderCredentialUnsupportedError,
)


class ControlPlaneError(RuntimeError):
    pass


class ControlPlaneClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(base_url=settings.CONTROL_PLANE_BASE_URL.rstrip("/"), timeout=settings.CONTROL_PLANE_TIMEOUT_SECONDS)

    def _headers(self) -> dict[str, str]:
        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {"iss": self.settings.VOICE_RUNTIME_JWT_ISSUER, "aud": self.settings.VOICE_RUNTIME_JWT_AUDIENCE, "sub": "voice-runtime", "iat": now, "exp": now + timedelta(seconds=60)},
            self.settings.VOICE_RUNTIME_SERVICE_SECRET,
            algorithm="HS256",
        )
        return {"Authorization": f"Bearer {token}"}

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.settings.CONTROL_PLANE_MAX_ATTEMPTS):
            try:
                response = await self.client.request(method, path, headers=self._headers(), **kwargs)
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    break
                if attempt + 1 < self.settings.CONTROL_PLANE_MAX_ATTEMPTS:
                    await asyncio.sleep(0.2 * (2**attempt))
        raise ControlPlaneError("Control Plane request failed") from last_error

    async def get_session_spec(self, session_id: str) -> RuntimeSessionSpecV1:
        response = await self._request("GET", f"/api/v1/internal/voice-runtime/sessions/{session_id}/spec")
        return RuntimeSessionSpecV1.model_validate(response.json())

    async def get_provider_credential(self, *, session_id: str, provider: str) -> ProviderCredential:
        try:
            response = await self._request(
                "GET", f"/api/v1/internal/voice-runtime/sessions/{session_id}/credentials/{provider}"
            )
        except ControlPlaneError as exc:
            status_code = exc.__cause__.response.status_code if isinstance(exc.__cause__, httpx.HTTPStatusError) else None
            if status_code == 404:
                raise ProviderCredentialSessionNotFoundError("Voice session or provider not found") from exc
            if status_code == 409:
                raise ProviderCredentialNotConfiguredError("Provider credentials are not available for this tenant") from exc
            if status_code == 422:
                raise ProviderCredentialUnsupportedError("Provider is not supported") from exc
            raise ProviderCredentialUnavailableError("Unable to resolve provider credential") from exc
        data = response.json()
        return ProviderCredential(provider=data["provider"], api_key=data["api_key"], base_url=data.get("base_url"))

    async def send_event(self, session_id: str, event_type: str, *, source: str = "voice-runtime", payload: dict | None = None, sequence: int | None = None) -> None:
        event = RuntimeEventV1(event_id=str(uuid4()), session_id=session_id, event_type=event_type, source=source, sequence=sequence, payload=payload or {}, occurred_at=datetime.now(timezone.utc))
        await self._request("POST", f"/api/v1/internal/voice-runtime/sessions/{session_id}/events", json=event.model_dump(mode="json"))

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()
