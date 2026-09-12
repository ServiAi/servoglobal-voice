from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx


ULTRAVOX_API_BASE_URL = "https://api.ultravox.ai"


class UltravoxProviderError(Exception):
    def __init__(self, code: str, status_code: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class UltravoxCallOutcomeUnknown(UltravoxProviderError):
    pass


@dataclass(frozen=True)
class UltravoxCallResult:
    call_id: str
    join_url: str


class UltravoxProviderClient:
    """Single tenant-keyed REST boundary for Ultravox administration."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        if not api_key.strip():
            raise UltravoxProviderError("provider_credentials_unavailable")
        return {"X-API-Key": api_key, "Content-Type": "application/json"}

    def _get(
        self, path: str, api_key: str, *, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        for attempt in range(2):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.get(
                        f"{ULTRAVOX_API_BASE_URL}{path}",
                        headers=self._headers(api_key),
                        params=params,
                    )
                if response.status_code not in {429, 500, 502, 503, 504} or attempt:
                    return self._checked(response)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
                if attempt:
                    raise UltravoxProviderError("provider_unavailable") from None
            time.sleep(0.1)
        raise UltravoxProviderError("provider_unavailable")

    @staticmethod
    def _checked(response: httpx.Response) -> httpx.Response:
        status = response.status_code
        if status in {401, 403}:
            raise UltravoxProviderError("provider_auth_failed", status)
        if status == 404:
            raise UltravoxProviderError("provider_resource_not_found", status)
        if status == 429:
            raise UltravoxProviderError("provider_rate_limited", status)
        if status >= 500:
            raise UltravoxProviderError("provider_unavailable", status)
        if status >= 400:
            raise UltravoxProviderError("provider_rejected", status)
        return response

    @staticmethod
    def _cursor(url: Any) -> str | None:
        if not isinstance(url, str):
            return None
        values = parse_qs(urlparse(url).query).get("cursor")
        return values[0] if values else None

    def list_agents(
        self, api_key: str, *, cursor: str | None, page_size: int, search: str | None
    ) -> dict[str, Any]:
        params = {"pageSize": page_size}
        if cursor:
            params["cursor"] = cursor
        if search:
            params["search"] = search
        return self._get("/api/agents", api_key, params=params).json()

    def get_agent(self, api_key: str, agent_id: str) -> dict[str, Any]:
        return self._get(f"/api/agents/{agent_id}", api_key).json()

    def list_voices(self, api_key: str, *, params: dict[str, Any]) -> dict[str, Any]:
        return self._get("/api/voices", api_key, params=params).json()

    def get_voice(self, api_key: str, voice_id: str) -> dict[str, Any]:
        return self._get(f"/api/voices/{voice_id}", api_key).json()

    def get_voice_preview(self, api_key: str, voice_id: str) -> bytes:
        response = self._get(f"/api/voices/{voice_id}/preview", api_key)
        if "audio/wav" not in response.headers.get("content-type", ""):
            raise UltravoxProviderError("provider_invalid_preview")
        if len(response.content) > 5 * 1024 * 1024:
            raise UltravoxProviderError("provider_preview_too_large")
        return response.content

    def create_agent_call(
        self, api_key: str, agent_id: str, *, payload: dict[str, Any]
    ) -> UltravoxCallResult:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{ULTRAVOX_API_BASE_URL}/api/agents/{agent_id}/calls",
                    headers=self._headers(api_key),
                    json=payload,
                )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise UltravoxProviderError("call_creation_failed") from exc
        except (httpx.ReadTimeout, httpx.WriteError, httpx.RemoteProtocolError) as exc:
            raise UltravoxCallOutcomeUnknown("call_creation_outcome_unknown") from exc
        if response.status_code >= 500:
            raise UltravoxCallOutcomeUnknown(
                "call_creation_outcome_unknown", response.status_code
            )
        self._checked(response)
        data = response.json()
        call_id, join_url = data.get("callId"), data.get("joinUrl")
        if not isinstance(call_id, str) or not isinstance(join_url, str):
            raise UltravoxCallOutcomeUnknown("call_creation_outcome_unknown")
        return UltravoxCallResult(call_id=call_id, join_url=join_url)

