from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.schemas.agents import AgentCreateRequest, AgentInstructions, AgentVoiceConfig
from app.schemas.ultravox_admin import (
    UltravoxAgentDetail,
    UltravoxAgentPage,
    UltravoxAgentSummary,
    UltravoxImportResponse,
    UltravoxToolSummary,
    UltravoxVoicePage,
    UltravoxVoiceSummary,
)
from app.services.agent_service import AgentService
from app.services.voice_config_service import VoiceConfigService
from app.services.voice_selection_service import VoiceSelectionError, VoiceSelectionService
from app.services.ultravox_provider_client import UltravoxProviderClient


# Explicit ServiGlobal -> Ultravox field mapping for an ElevenLabs external
# voice, matching the runtime mapper in
# voice-runtime/src/serviglobal_voice_runtime/providers.py::build_elevenlabs_external_voice
# field-for-field (see test_ultravox_admin.py for the parity assertion).
# Backend and voice-runtime are separate deploys/packages with no shared
# code, so this is intentionally its own small mapper, not a generic
# camelCase converter -- it only knows these five keys and nothing else.
_ELEVENLABS_SETTINGS_TO_ULTRAVOX_FIELDS = {
    "model": "model",
    "speed": "speed",
    "stability": "stability",
    "similarity_boost": "similarityBoost",
    "use_speaker_boost": "useSpeakerBoost",
}


def build_elevenlabs_external_voice(voice: AgentVoiceConfig) -> dict[str, Any]:
    elevenlabs: dict[str, Any] = {"voiceId": voice.voice_id}
    for settings_key, ultravox_key in _ELEVENLABS_SETTINGS_TO_ULTRAVOX_FIELDS.items():
        if settings_key in voice.settings:
            elevenlabs[ultravox_key] = voice.settings[settings_key]
    return {"elevenLabs": elevenlabs}


SUPPORTED_TOOLS = {
    "check_availability",
    "create_booking",
    "reschedule_booking",
    "cancel_booking",
}
FORBIDDEN_KEY_PARTS = (
    "secret", "token", "password", "authorization", "api_key", "apikey", "header"
)


class UltravoxAdminService:
    def __init__(self, db: Session, client: UltravoxProviderClient | None = None) -> None:
        self.db = db
        self.config_service = VoiceConfigService(db)
        self.client = client or UltravoxProviderClient()

    def _api_key(self, tenant_id: str) -> str:
        config = self.config_service.get_active_provider_config(tenant_id, "ultravox")
        return self.config_service.decrypt_api_key(config)

    @staticmethod
    def _requires_client_execution(value: Any) -> bool:
        if isinstance(value, dict):
            return any(
                str(key).lower() in {"client", "dataconnection", "data_connection"}
                or UltravoxAdminService._requires_client_execution(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return any(UltravoxAdminService._requires_client_execution(item) for item in value)
        return False

    @staticmethod
    def _tools(agent: dict[str, Any]) -> list[UltravoxToolSummary]:
        template = agent.get("callTemplate") if isinstance(agent.get("callTemplate"), dict) else {}
        rows = template.get("selectedTools") if isinstance(template.get("selectedTools"), list) else []
        result: list[UltravoxToolSummary] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("toolName") or row.get("name") or "unnamed")[:120]
            if UltravoxAdminService._requires_client_execution(row):
                classification = "unsupported_client_tool"
            elif name in SUPPORTED_TOOLS:
                classification = "serviglobal_supported"
            else:
                classification = "provider_native"
            result.append(UltravoxToolSummary(name=name, classification=classification))
        return result

    @classmethod
    def _agent(cls, row: dict[str, Any], *, detail: bool = False):
        template = row.get("callTemplate") if isinstance(row.get("callTemplate"), dict) else {}
        tools = cls._tools(row)
        common = dict(
            agent_id=str(row.get("agentId") or ""),
            published_revision_id=row.get("publishedRevisionId"),
            name=str(row.get("name") or template.get("name") or "Ultravox Agent")[:160],
            model=template.get("model"),
            voice_name=template.get("voice"),
            call_count=int((row.get("statistics") or {}).get("calls") or 0),
            tools=tools,
            has_unsupported_client_tools=any(
                tool.classification == "unsupported_client_tool" for tool in tools
            ),
        )
        if not detail:
            return UltravoxAgentSummary(**common)
        temperature = template.get("temperature")
        return UltravoxAgentDetail(
            **common,
            language_hint=template.get("languageHint"),
            temperature=float(temperature) if isinstance(temperature, (int, float)) else None,
            first_speaker=template.get("firstSpeaker"),
            max_duration=template.get("maxDuration"),
            vad_settings=cls._safe_value(template.get("vadSettings")),
        )

    @classmethod
    def _safe_value(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key)[:80]: cls._safe_value(item)
                for key, item in value.items()
                if not any(part in str(key).lower() for part in FORBIDDEN_KEY_PARTS)
            }
        if isinstance(value, list):
            return [cls._safe_value(item) for item in value[:50]]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value if not isinstance(value, str) else value[:2000]
        return None

    @staticmethod
    def _voice(row: dict[str, Any]) -> UltravoxVoiceSummary:
        definition = row.get("definition") if isinstance(row.get("definition"), dict) else {}
        provider = row.get("provider")
        key = str(provider or next(iter(definition), "ultravox"))
        capability_map = {
            "elevenLabs": {"speed", "stability", "similarity_boost", "style"},
            "cartesia": {"speed", "emotion"},
            "google": {"speed"},
        }
        supported = capability_map.get(key, set())
        return UltravoxVoiceSummary(
            voice_id=str(row.get("voiceId") or ""),
            name=str(row.get("name") or "Voice")[:80],
            language_label=row.get("languageLabel"),
            primary_language=row.get("primaryLanguage"),
            ownership=row.get("ownership") if row.get("ownership") in {"public", "private"} else "public",
            billing_style=row.get("billingStyle")
            if row.get("billingStyle") in {"VOICE_BILLING_STYLE_INCLUDED", "VOICE_BILLING_STYLE_EXTERNAL"}
            else "VOICE_BILLING_STYLE_INCLUDED",
            provider=provider,
            capabilities={
                "native_voice": not bool(definition),
                "external_voice": bool(definition),
                "voice_preview": True,
                "voice_clone": False,
                **{name: name in supported for name in ("speed", "stability", "similarity_boost", "style", "emotion")},
            },
            settings_schema={name: {"type": "number"} for name in supported},
        )

    def list_agents(self, tenant_id: str, **filters: Any) -> UltravoxAgentPage:
        data = self.client.list_agents(self._api_key(tenant_id), **filters)
        rows = data.get("results") if isinstance(data.get("results"), list) else []
        return UltravoxAgentPage(
            results=[self._agent(row) for row in rows if isinstance(row, dict)],
            next_cursor=self.client._cursor(data.get("next")),
            previous_cursor=self.client._cursor(data.get("previous")),
            total=int(data.get("total") or 0),
        )

    def get_agent(self, tenant_id: str, agent_id: str) -> UltravoxAgentDetail:
        return self._agent(self.client.get_agent(self._api_key(tenant_id), agent_id), detail=True)

    def validate_provider_agent_link(self, tenant_id: str, agent_id: str) -> UltravoxAgentDetail:
        agent = self.get_agent(tenant_id, agent_id)
        if agent.agent_id != agent_id:
            raise ValueError("provider_agent_not_accessible")
        return agent

    def validate_execution_preflight(self, tenant_id: str, agent_id: str) -> UltravoxAgentDetail:
        agent = self.validate_provider_agent_link(tenant_id, agent_id)
        if agent.has_unsupported_client_tools:
            raise ValueError("provider_agent_has_unsupported_client_tools")
        return agent

    def list_voices(self, tenant_id: str, **filters: Any) -> UltravoxVoicePage:
        params = {key: value for key, value in filters.items() if value not in (None, "")}
        data = self.client.list_voices(self._api_key(tenant_id), params=params)
        rows = data.get("results") if isinstance(data.get("results"), list) else []
        return UltravoxVoicePage(
            results=[self._voice(row) for row in rows if isinstance(row, dict)],
            next_cursor=self.client._cursor(data.get("next")),
            previous_cursor=self.client._cursor(data.get("previous")),
            total=int(data.get("total") or 0),
        )

    def get_voice(self, tenant_id: str, voice_id: str) -> UltravoxVoiceSummary:
        return self._voice(self.client.get_voice(self._api_key(tenant_id), voice_id))

    def preview(self, tenant_id: str, voice_id: str) -> bytes:
        key = self._api_key(tenant_id)
        voice = self.client.get_voice(key, voice_id)
        if str(voice.get("voiceId") or "") != voice_id:
            raise ValueError("provider_voice_not_accessible")
        return self.client.get_voice_preview(key, voice_id)

    def preview_external_voice(self, tenant_id: str, voice: AgentVoiceConfig) -> bytes:
        """Explicit "Probar voz" action for provider_external + elevenlabs.
        Local-only validation, then a single (no-retry) call to Ultravox's
        own ad-hoc voice_preview endpoint -- ServiGlobal never resolves or
        stores an ElevenLabs credential; Ultravox uses the BYOK key already
        configured on the tenant's Ultravox account."""
        if voice.mode != "provider_external" or voice.provider != "elevenlabs":
            raise ValueError("voice_provider_not_supported")
        try:
            VoiceSelectionService.validate_settings(voice)
        except VoiceSelectionError as exc:
            raise ValueError("voice_settings_invalid") from exc
        payload = {
            "name": "ServiGlobal External Voice Preview",
            "definition": build_elevenlabs_external_voice(voice),
        }
        return self.client.preview_external_voice(self._api_key(tenant_id), payload=payload)

    def validate_external_voice_credentials(self, tenant_id: str, provider: str) -> None:
        """Publish-time preflight for provider_external voices: confirms the
        tenant's Ultravox account has a BYOK key configured for `provider`,
        without ever seeing that key's value and without generating audio
        (no call to voice_preview here)."""
        if provider != "elevenlabs":
            raise ValueError("voice_provider_not_supported")
        keys = self.client.get_tts_api_keys(self._api_key(tenant_id))
        entry = keys.get("elevenLabs") if isinstance(keys, dict) else None
        if not isinstance(entry, dict) or not entry:
            raise ValueError("external_tts_credentials_unavailable")

    def import_agent(self, tenant_id: str, agent_id: str, user_id: str | None) -> UltravoxImportResponse:
        raw = self.client.get_agent(self._api_key(tenant_id), agent_id)
        remote = self._agent(raw, detail=True)
        template = raw.get("callTemplate") if isinstance(raw.get("callTemplate"), dict) else {}
        warnings = [
            f"Tool '{tool.name}' remains provider_only."
            for tool in remote.tools
            if tool.classification != "serviglobal_supported"
        ]
        created = AgentService(self.db).create_agent(
            tenant_id,
            AgentCreateRequest(
                name=remote.name,
                language=remote.language_hint or "es",
                instructions=AgentInstructions(system_prompt=str(template.get("systemPrompt") or "")),
                provider="ultravox",
                model="ultravox-v0.7",
            ),
            user_id,
        )
        draft = created.draft_version
        binding = dict(draft.runtime_binding_json)
        realtime = dict(binding["realtime"])
        realtime["provider_extensions"] = {
            "source": "ultravox_import",
            "source_agent_id": remote.agent_id,
            "source_revision_id": remote.published_revision_id,
            "tools": [tool.model_dump() for tool in remote.tools],
            "warnings": warnings,
            "temperature": remote.temperature,
            "first_speaker": remote.first_speaker,
            "max_duration": remote.max_duration,
            "vad_settings": remote.vad_settings,
        }
        if remote.voice_name:
            realtime["voice"] = {
                "mode": "provider", "provider": "ultravox", "voice_id": remote.voice_name
            }
        binding["realtime"] = self._safe_value(realtime)
        draft.runtime_binding_json = binding
        self.db.commit()
        return UltravoxImportResponse(
            agent_id=created.id, draft_version_id=draft.id, warnings=warnings
        )
