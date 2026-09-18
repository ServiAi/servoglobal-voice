from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

import httpx


ULTRAVOX_API_BASE_URL = "https://api.ultravox.ai"
PREVIEW_REJECTION_REASONS = frozenset({"voice", "model", "permission", "quota", "sample_rate", "plan_restriction", "other"})


class UltravoxProviderError(Exception):
    def __init__(self, code: str, status_code: int | None = None, *, reason: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.reason = reason


class UltravoxCallOutcomeUnknown(UltravoxProviderError):
    pass


@dataclass(frozen=True)
class UltravoxCallResult:
    call_id: str
    join_url: str


PreviewMediaType = Literal["audio/wav", "audio/mpeg"]


@dataclass(frozen=True)
class VoicePreviewAudio:
    content: bytes
    media_type: PreviewMediaType


def _has_mp3_frame_header(data: bytes) -> bool:
    return (
        len(data) >= 4
        and data[0] == 0xFF
        and (data[1] & 0xE0) == 0xE0  # 11-bit sync
        and ((data[1] >> 3) & 0x03) != 0x01  # reserved MPEG version
        and ((data[1] >> 1) & 0x03) == 0x01  # Layer III only
        and 0 < ((data[2] >> 4) & 0x0F) < 0x0F  # defined bitrate
        and ((data[2] >> 2) & 0x03) != 0x03  # defined sample rate
    )


def detect_preview_audio_type(data: bytes) -> PreviewMediaType | None:
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if len(data) < 32:
        return None
    if data.startswith(b"ID3"):
        if len(data) < 10 or data[3] not in {2, 3, 4} or data[4] == 0xFF:
            return None
        size_bytes = data[6:10]
        if any(byte & 0x80 for byte in size_bytes):
            return None
        tag_size = sum(byte << shift for byte, shift in zip(size_bytes, (21, 14, 7, 0)))
        frame_offset = 10 + tag_size + (10 if data[3] == 4 and data[5] & 0x10 else 0)
        return "audio/mpeg" if _has_mp3_frame_header(data[frame_offset:frame_offset + 4]) else None
    return "audio/mpeg" if _has_mp3_frame_header(data[:4]) else None


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
        self, path: str, api_key: str, *, params: dict[str, Any] | None = None,
        preview_kind: str | None = None,
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
                    return self._checked(response, preview_kind=preview_kind)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
                if attempt:
                    raise UltravoxProviderError("provider_unavailable") from None
            time.sleep(0.1)
        raise UltravoxProviderError("provider_unavailable")

    @staticmethod
    def _checked(response: httpx.Response, *, preview_kind: str | None = None) -> httpx.Response:
        status = response.status_code
        if status == 400 and preview_kind:
            reason = UltravoxProviderClient._classify_preview_rejection(response)
            UltravoxProviderClient._log_preview_rejection(preview_kind, reason)
            raise UltravoxProviderError("voice_preview_rejected", status, reason=reason)
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
    def _classify_preview_rejection(response: httpx.Response) -> str:
        # The provider body stays here; only a fixed category may leave this boundary.
        detail = response.content[:4096].decode("utf-8", errors="replace").lower()
        if "library voices via the api" in detail and (
            "free users cannot use" in detail or "upgrade your subscription" in detail
        ):
            return "plan_restriction"
        if "pcm_44100" in detail or "sample rate" in detail or "sample_rate" in detail:
            return "sample_rate"
        elif "quota" in detail or "credits" in detail or "credit balance" in detail:
            return "quota"
        elif "permission" in detail or "text_to_speech" in detail:
            return "permission"
        elif "model" in detail and any(word in detail for word in ("invalid", "unknown", "not found", "not available", "unsupported")):
            return "model"
        elif ("voice" in detail or "voiceid" in detail) and any(
            word in detail for word in ("invalid", "unknown", "not found", "not available", "does not exist", "unavailable")
        ):
            return "voice"
        return "other"

    @staticmethod
    def _log_preview_rejection(preview_kind: str, reason: str) -> None:
        logging.getLogger(__name__).warning(
            "Ultravox voice preview rejected | kind=%s | upstream_status=400 | reason=%s",
            preview_kind, reason,
        )

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

    def get_voice_preview(self, api_key: str, voice_id: str) -> VoicePreviewAudio:
        logger = logging.getLogger(__name__)
        response = self._get(f"/api/voices/{voice_id}/preview", api_key, preview_kind="catalog")
        for _ in range(2):
            if not response.is_redirect:
                break
            location = response.headers.get("location")
            try:
                target = response.request.url.join(location) if location else None
            except httpx.InvalidURL:
                target = None
            if (target is None or target.scheme != "https" or target.port not in {None, 443}
                    or target.username or target.password or not target.host
                    or not (target.host.endswith(".ultravox.ai") or target.host == "storage.googleapis.com")):
                logger.warning(
                    "Ultravox voice preview redirect blocked | upstream_status=%s", response.status_code,
                )
                raise UltravoxProviderError("provider_preview_redirect_blocked")
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.get(
                        str(target),
                        headers=self._headers(api_key) if target.host == "api.ultravox.ai" else {},
                    )
            except httpx.RequestError as exc:
                raise UltravoxProviderError("provider_unavailable") from exc
            response = self._checked(response, preview_kind="catalog")
        if response.is_redirect:
            logger.warning(
                "Ultravox voice preview redirect limit reached | upstream_status=%s", response.status_code,
            )
            raise UltravoxProviderError("provider_preview_redirect_blocked")
        if len(response.content) > 5 * 1024 * 1024:
            raise UltravoxProviderError("provider_preview_too_large")
        media_type = detect_preview_audio_type(response.content)
        if media_type is None:
            mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            mime_class = mime if mime in {
                "audio/wav", "audio/x-wav", "application/octet-stream", "audio/mpeg",
                "application/json", "text/html", "text/plain",
            } else "other" if mime else "missing"
            logger.warning(
                "Ultravox voice preview invalid audio | upstream_status=%s | mime_class=%s | bytes=%s",
                response.status_code, mime_class, len(response.content),
            )
            raise UltravoxProviderError("provider_invalid_preview")
        return VoicePreviewAudio(content=response.content, media_type=media_type)

    def get_tts_api_keys(self, api_key: str) -> dict[str, Any]:
        """GET is idempotent, so this reuses the retrying _get helper unlike
        preview_external_voice below."""
        return self._get("/api/accounts/me/tts_api_keys", api_key).json()

    def preview_external_voice(self, api_key: str, *, payload: dict[str, Any]) -> VoicePreviewAudio:
        """POST /api/voice_preview generates real audio and can consume the
        tenant's provider quota, so -- unlike every GET above -- this makes
        exactly one attempt. No retry on timeout/connection reset/5xx: the
        user must explicitly press "Probar voz" again rather than have this
        silently retry a billable generation."""
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{ULTRAVOX_API_BASE_URL}/api/voice_preview",
                    headers=self._headers(api_key),
                    json=payload,
                )
        except (
            httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
            httpx.WriteError, httpx.RemoteProtocolError,
        ) as exc:
            raise UltravoxProviderError("provider_unavailable") from exc
        status = response.status_code
        if status in {401, 403}:
            raise UltravoxProviderError("provider_auth_failed", status)
        if status == 429:
            raise UltravoxProviderError("provider_rate_limited", status)
        if status >= 500:
            raise UltravoxProviderError("provider_unavailable", status)
        if status >= 400:
            # Ultravox rejected this specific voiceId/model/settings
            # combination (e.g. unknown ElevenLabs voice). Never surface the
            # provider's raw response body to the caller.
            if status == 400:
                reason = self._classify_preview_rejection(response)
                self._log_preview_rejection("external", reason)
                raise UltravoxProviderError("voice_preview_rejected", status, reason=reason)
            raise UltravoxProviderError("external_voice_preview_failed", status)
        if len(response.content) > 5 * 1024 * 1024:
            raise UltravoxProviderError("provider_preview_too_large")
        media_type = detect_preview_audio_type(response.content)
        if media_type is None:
            raise UltravoxProviderError("provider_invalid_preview")
        return VoicePreviewAudio(content=response.content, media_type=media_type)

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

