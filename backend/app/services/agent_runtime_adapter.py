from __future__ import annotations

from typing import Protocol

from app.models.integrations import TenantVoiceAgentConfig


class AgentRuntimeAdapter(Protocol):
    """Boundary between the Agent Builder domain and a provider runtime.

    Not wired into any live call flow yet: this is the seam future phases
    (LiveKit, OpenAI Realtime, ...) will implement against. `VoiceClient` and
    the existing Ultravox call flow are untouched by this phase.
    """

    def validate_configuration(self, spec: dict) -> None: ...

    def compile_settings(
        self, spec: dict, voice_agent_config: TenantVoiceAgentConfig | None
    ) -> dict: ...


class UltravoxLegacyRuntimeAdapter:
    """Resolves a RuntimeSessionSpec against the legacy TenantVoiceAgentConfig
    when an AgentVersion is linked to one (`voice_agent_config_id`).

    This does not execute calls -- it only compiles the settings a future
    runtime dispatcher would hand to the existing Ultravox integration.
    """

    def validate_configuration(self, spec: dict) -> None:
        pipeline = spec.get("pipeline", {})
        if pipeline.get("pipeline_type") != "realtime":
            raise ValueError(
                "UltravoxLegacyRuntimeAdapter only supports the 'realtime' pipeline type."
            )
        if pipeline.get("realtime", {}).get("provider") != "ultravox":
            raise ValueError(
                "UltravoxLegacyRuntimeAdapter only supports the 'ultravox' realtime provider."
            )

    def compile_settings(
        self, spec: dict, voice_agent_config: TenantVoiceAgentConfig | None
    ) -> dict:
        self.validate_configuration(spec)
        settings = {
            "provider": "ultravox",
            "provider_agent_id": None,
            "system_prompt": spec["instructions"].get("system_prompt", ""),
            "language": spec["language"],
            "voice": None,
        }
        if voice_agent_config is not None:
            settings["provider_agent_id"] = voice_agent_config.provider_agent_id
            settings["voice"] = voice_agent_config.default_voice
            if not settings["system_prompt"]:
                settings["system_prompt"] = voice_agent_config.default_system_prompt or ""
        return settings
