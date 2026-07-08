from __future__ import annotations

import httpx
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VoiceClientConfig:
    provider: str
    api_key: str
    base_url: str | None = None
    default_agent_id: str | None = None
    default_from_number: str | None = None
    default_language: str = "es"
    default_timezone: str = "America/Bogota"


class VoiceClientError(Exception):
    pass


class VoiceClient:
    def start_outbound_call(
        self,
        config: VoiceClientConfig,
        *,
        to_phone: str,
        agent_id: str,
        metadata: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if config.provider == "ultravox":
            return self._start_ultravox_call(config, to_phone=to_phone, agent_id=agent_id, metadata=metadata, context=context)
        else:
            raise VoiceClientError(f"Provider '{config.provider}' is not supported yet.")

    def get_call(
        self,
        config: VoiceClientConfig,
        *,
        provider_call_id: str,
    ) -> dict[str, Any]:
        if config.provider == "ultravox":
            return self._get_ultravox_call(config, provider_call_id=provider_call_id)
        else:
            raise VoiceClientError(f"Provider '{config.provider}' is not supported yet.")

    def normalize_provider_response(self, provider: str, data: dict[str, Any]) -> dict[str, Any]:
        if provider == "ultravox":
            return {
                "provider_call_id": data.get("callId") or data.get("id"),
                "provider_session_id": data.get("sessionId") or data.get("session_id"),
                "status": data.get("status") or data.get("state"),
                "recording_url": data.get("recordingUrl") or data.get("recording_url"),
            }
        return data

    def sanitize_voice_error(self, exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            try:
                err_data = exc.response.json()
                if isinstance(err_data, dict) and "detail" in err_data:
                    return str(err_data["detail"])
            except Exception:
                pass
            return f"HTTP error {exc.response.status_code}"
        return str(exc)

    def _start_ultravox_call(
        self,
        config: VoiceClientConfig,
        *,
        to_phone: str,
        agent_id: str,
        metadata: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        from app.services.voice_service import normalize_e164_colombia
        from app.core.config import settings

        number = normalize_e164_colombia(to_phone)
        dialed = f"+{number}"

        host = settings.ASTERISK_PUBLIC_HOST
        pbx_uri = f"sip:{dialed}@{host}:5060"

        username = settings.UVX_SIP_USERNAME
        password = settings.UVX_SIP_PASSWORD

        base_url = config.base_url or "https://api.ultravox.ai"
        url = f"{base_url.rstrip('/')}/api/agents/{agent_id}/calls"

        headers = {
            "X-API-Key": config.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "medium": {
                "sip": {
                    "outgoing": {
                        "to": pbx_uri,
                        "username": username,
                        "password": password,
                    }
                }
            },
            "firstSpeakerSettings": {"agent": {}},
            "metadata": metadata,
            "templateContext": context,
        }

        digits = "".join(ch for ch in str(to_phone) if ch.isdigit())
        phone_tail = f"***{digits[-4:]}" if len(digits) > 4 else "***"

        logger.info(
            "Initiating Ultravox call | provider=ultravox | agent_id=%s | phone_tail=%s",
            agent_id,
            phone_tail,
        )

        try:
            with httpx.Client() as client:
                response = client.post(url, json=payload, headers=headers, timeout=20.0)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "Ultravox API error on call start | status_code=%s",
                e.response.status_code,
            )
            raise e
        except Exception as e:
            logger.error("Unexpected error on Ultravox call start: %s", type(e).__name__)
            raise e

    def _get_ultravox_call(
        self,
        config: VoiceClientConfig,
        *,
        provider_call_id: str,
    ) -> dict[str, Any]:
        base_url = config.base_url or "https://api.ultravox.ai"
        url = f"{base_url.rstrip('/')}/api/calls/{provider_call_id}"

        headers = {
            "X-API-Key": config.api_key,
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client() as client:
                response = client.get(url, headers=headers, timeout=10.0)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "Ultravox API error on get call | status_code=%s",
                e.response.status_code,
            )
            raise e
        except Exception as e:
            logger.error("Unexpected error on Ultravox get call: %s", type(e).__name__)
            raise e
