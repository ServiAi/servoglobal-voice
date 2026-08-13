from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.models.integrations import TenantVoiceAgentConfig, TenantVoiceProviderConfig
from app.services.voice_config_service import VoiceConfigService


@dataclass(frozen=True)
class ProviderCallResult:
    provider_call_id: str | None
    join_url: str | None
    joined_at: str | None = None
    ended_at: str | None = None
    end_reason: str | None = None


class ProviderDefiniteFailure(Exception):
    def __init__(self, failure_code: str, status_code: int | None = None) -> None:
        self.failure_code = failure_code
        self.status_code = status_code


class ProviderAmbiguousFailure(Exception):
    pass


class VoiceExperienceRuntimeProvider:
    def __init__(self, config_service: VoiceConfigService, *, timeout_seconds: float) -> None:
        self.config_service = config_service
        self.timeout_seconds = timeout_seconds

    def _credentials(self, config: TenantVoiceProviderConfig) -> tuple[str, dict[str, str]]:
        base_url = (config.base_url or "https://api.ultravox.ai").rstrip("/")
        return base_url, {"X-API-Key": self.config_service.decrypt_api_key(config)}

    def create_webrtc_call(
        self,
        config: TenantVoiceProviderConfig,
        agent: TenantVoiceAgentConfig,
        *,
        metadata: dict[str, str],
        user_context: dict[str, Any],
    ) -> ProviderCallResult:
        base_url, headers = self._credentials(config)
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{base_url}/api/agents/{agent.provider_agent_id}/calls",
                    headers=headers,
                    json={"metadata": metadata, "templateContext": {"user_context": user_context}},
                )
                if 400 <= response.status_code < 500:
                    raise ProviderDefiniteFailure("provider_rejected", response.status_code)
                if response.status_code >= 500:
                    raise ProviderAmbiguousFailure
                response.raise_for_status()
                data = response.json()
        except ProviderDefiniteFailure:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise ProviderDefiniteFailure("provider_connect_failed") from exc
        except (httpx.ReadTimeout, httpx.WriteError, httpx.RemoteProtocolError, httpx.HTTPStatusError, ValueError) as exc:
            raise ProviderAmbiguousFailure from exc
        return self._result(data)

    def get_call(self, config: TenantVoiceProviderConfig, provider_call_id: str) -> ProviderCallResult:
        base_url, headers = self._credentials(config)
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(f"{base_url}/api/calls/{provider_call_id}", headers=headers)
                response.raise_for_status()
                return self._result(response.json())
        except Exception as exc:
            raise ProviderAmbiguousFailure from exc

    def find_call_by_runtime_metadata(
        self,
        config: TenantVoiceProviderConfig,
        agent: TenantVoiceAgentConfig,
        *,
        runtime_call_id: str,
        attempted_at: datetime | None,
    ) -> list[ProviderCallResult]:
        base_url, headers = self._credentials(config)
        params: dict[str, str] = {
            "metadata.runtime_call_id": runtime_call_id,
            "agentIds": agent.provider_agent_id,
        }
        if attempted_at:
            params["fromDate"] = attempted_at.isoformat()
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(f"{base_url}/api/calls", headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise ProviderAmbiguousFailure from exc
        rows = data.get("results") or data.get("calls") or []
        return [
            self._result(row)
            for row in rows
            if isinstance(row, dict)
            and str((row.get("metadata") or {}).get("runtime_call_id")) == runtime_call_id
            and str(row.get("agentId") or row.get("agent_id") or agent.provider_agent_id) == agent.provider_agent_id
        ]

    @staticmethod
    def _result(data: dict[str, Any]) -> ProviderCallResult:
        join_url = data.get("joinUrl") or data.get("join_url")
        if not isinstance(join_url, str) or not join_url.startswith("https://"):
            join_url = None
        provider_call_id = data.get("callId") or data.get("id")
        return ProviderCallResult(
            provider_call_id=str(provider_call_id) if provider_call_id else None,
            join_url=join_url,
            joined_at=data.get("joined") or data.get("joinedAt") or data.get("joined_at"),
            ended_at=data.get("ended") or data.get("endedAt") or data.get("ended_at"),
            end_reason=data.get("endReason") or data.get("end_reason"),
        )
