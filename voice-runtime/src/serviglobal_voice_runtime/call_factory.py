from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import aiohttp


ULTRAVOX_API_BASE_URL = "https://api.ultravox.ai"
logger = logging.getLogger(__name__)
SUPPORTED_SERVIGLOBAL_TOOLS = {
    "check_availability",
    "create_booking",
    "reschedule_booking",
    "cancel_booking",
}
ALLOWED_OVERRIDE_KEYS = {
    "join_timeout",
    "max_duration",
    "recording_enabled",
    "initial_output_medium",
}


class CallCreationFailed(RuntimeError):
    pass


class CallCreationOutcomeUnknown(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderCall:
    call_id: str
    join_url: str
    published_revision_id: str | None


class ProviderCallFactory(Protocol):
    async def create(
        self,
        *,
        api_key: str,
        agent_id: str,
        observed_revision_id: str | None,
        session_id: str,
        local_agent_id: str,
        context: dict[str, Any],
        overrides: dict[str, Any],
        input_sample_rate: int,
        output_sample_rate: int,
    ) -> ProviderCall: ...


def _safe_context(value: Any, *, depth: int = 0) -> Any:
    if depth > 3:
        raise CallCreationFailed("template_context_too_deep")
    if isinstance(value, dict):
        if len(value) > 50:
            raise CallCreationFailed("template_context_too_large")
        result: dict[str, Any] = {}
        for key, item in value.items():
            key = str(key)
            if len(key) > 80 or any(
                part in key.lower()
                for part in ("secret", "token", "password", "authorization", "api_key", "header")
            ):
                raise CallCreationFailed("template_context_forbidden_key")
            result[key] = _safe_context(item, depth=depth + 1)
        return result
    if isinstance(value, list):
        if len(value) > 50:
            raise CallCreationFailed("template_context_too_large")
        return [_safe_context(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    raise CallCreationFailed("template_context_invalid_value")


def _classify_tools(agent: dict[str, Any]) -> list[tuple[str, str]]:
    template = agent.get("callTemplate") if isinstance(agent.get("callTemplate"), dict) else {}
    rows = template.get("selectedTools") if isinstance(template.get("selectedTools"), list) else []
    classified: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("toolName") or row.get("name") or "unnamed")[:120]
        if _requires_client_execution(row):
            kind = "unsupported_client_tool"
        elif name in SUPPORTED_SERVIGLOBAL_TOOLS:
            kind = "serviglobal_supported"
        else:
            kind = "provider_native"
        classified.append((name, kind))
    return classified


def _requires_client_execution(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower() in {"client", "dataconnection", "data_connection"}
            or _requires_client_execution(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_requires_client_execution(item) for item in value)
    return False


class UltravoxAgentCallFactory:
    """Preflights the current remote agent and creates exactly one call."""

    def __init__(self, http_session: aiohttp.ClientSession) -> None:
        self.http_session = http_session

    async def _get_agent(self, api_key: str, agent_id: str) -> dict[str, Any]:
        headers = {"X-API-Key": api_key}
        for attempt in range(2):
            try:
                async with self.http_session.get(
                    f"{ULTRAVOX_API_BASE_URL}/api/agents/{agent_id}", headers=headers
                ) as response:
                    if response.status in {429, 500, 502, 503, 504} and not attempt:
                        await asyncio.sleep(0.1)
                        continue
                    if response.status >= 400:
                        raise CallCreationFailed(f"provider_agent_preflight_{response.status}")
                    data = await response.json()
                    if not isinstance(data, dict) or data.get("agentId") != agent_id:
                        raise CallCreationFailed("provider_agent_not_accessible")
                    return data
            except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as exc:
                if attempt:
                    raise CallCreationFailed("provider_agent_preflight_failed") from exc
        raise CallCreationFailed("provider_agent_preflight_failed")

    async def create(
        self,
        *,
        api_key: str,
        agent_id: str,
        observed_revision_id: str | None,
        session_id: str,
        local_agent_id: str,
        context: dict[str, Any],
        overrides: dict[str, Any],
        input_sample_rate: int,
        output_sample_rate: int,
    ) -> ProviderCall:
        if not api_key or set(overrides) - ALLOWED_OVERRIDE_KEYS:
            raise CallCreationFailed("provider_call_overrides_invalid")
        remote = await self._get_agent(api_key, agent_id)
        current_revision = remote.get("publishedRevisionId")
        if observed_revision_id and current_revision != observed_revision_id:
            logger.warning(
                "Provider-managed agent revision drift detected",
                extra={"voice_session_id": session_id, "provider": "ultravox"},
            )
        if any(kind == "unsupported_client_tool" for _, kind in _classify_tools(remote)):
            raise CallCreationFailed("provider_agent_has_unsupported_client_tools")

        payload: dict[str, Any] = {
            "templateContext": _safe_context(context),
            "metadata": {
                "voice_session_id": session_id,
                "agent_id": local_agent_id,
            },
            "medium": {
                "serverWebSocket": {
                    "inputSampleRate": input_sample_rate,
                    "outputSampleRate": output_sample_rate,
                    "clientBufferSizeMs": 30000,
                }
            },
        }
        names = {
            "join_timeout": "joinTimeout",
            "max_duration": "maxDuration",
            "recording_enabled": "recordingEnabled",
            "initial_output_medium": "initialOutputMedium",
        }
        payload.update({names[key]: value for key, value in overrides.items()})
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        try:
            async with self.http_session.post(
                f"{ULTRAVOX_API_BASE_URL}/api/agents/{agent_id}/calls",
                headers=headers,
                json=payload,
            ) as response:
                if response.status >= 500:
                    raise CallCreationOutcomeUnknown("call_creation_outcome_unknown")
                if response.status >= 400:
                    raise CallCreationFailed(f"call_creation_failed_{response.status}")
                data = await response.json()
        except CallCreationFailed:
            raise
        except CallCreationOutcomeUnknown:
            raise
        except aiohttp.ClientConnectorError as exc:
            raise CallCreationFailed("call_creation_failed") from exc
        except (asyncio.TimeoutError, aiohttp.ServerDisconnectedError, aiohttp.ClientPayloadError) as exc:
            raise CallCreationOutcomeUnknown("call_creation_outcome_unknown") from exc

        call_id, join_url = data.get("callId"), data.get("joinUrl")
        if not isinstance(call_id, str) or not isinstance(join_url, str):
            raise CallCreationOutcomeUnknown("call_creation_outcome_unknown")
        return ProviderCall(
            call_id=call_id,
            join_url=join_url,
            published_revision_id=current_revision,
        )


class _CreatedCallResponse:
    status = 201

    def __init__(self, call: ProviderCall) -> None:
        self.call = call

    def raise_for_status(self) -> None:
        return None

    async def json(self) -> dict[str, str]:
        return {"callId": self.call.call_id, "joinUrl": self.call.join_url}


class _CreatedCallContext:
    def __init__(self, create_call: Any) -> None:
        self.create_call = create_call

    async def __aenter__(self) -> _CreatedCallResponse:
        return _CreatedCallResponse(await self.create_call)

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class ManagedAgentHttpSession:
    """Thin compatibility seam: replace only the plugin's direct-call POST."""

    def __init__(self, session: aiohttp.ClientSession, create_call: Any) -> None:
        self.session = session
        self.create_call = create_call
        self._call_task: asyncio.Task[ProviderCall] | None = None

    def post(self, *_args: Any, **_kwargs: Any) -> _CreatedCallContext:
        if self._call_task is None:
            self._call_task = asyncio.create_task(self.create_call())
        return _CreatedCallContext(self._call_task)

    def ws_connect(self, *args: Any, **kwargs: Any):
        return self.session.ws_connect(*args, **kwargs)
