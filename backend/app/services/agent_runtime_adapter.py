from __future__ import annotations

from typing import Protocol

from app.models.integrations import TenantVoiceAgentConfig
from app.schemas.runtime_session import RuntimeSessionSpecV1


class AgentRuntimeAdapter(Protocol):
    """Boundary between the Agent Builder domain and a provider runtime.

    Not wired into any live call flow yet: this is the seam future phases
    (LiveKit, OpenAI Realtime, ...) will implement against. `VoiceClient` and
    the existing Ultravox call flow are untouched by this phase.
    """

    def validate_configuration(self, spec: RuntimeSessionSpecV1) -> None: ...

    def compile_settings(
        self,
        spec: RuntimeSessionSpecV1,
        voice_agent_config: TenantVoiceAgentConfig | None,
    ) -> dict: ...


class UltravoxLegacyRuntimeAdapter:
    """Resolves a RuntimeSessionSpecV1 against the legacy TenantVoiceAgentConfig
    when an AgentVersion is linked to one (`voice_agent_config_id`).

    This does not execute calls -- it only compiles the settings a future
    runtime dispatcher would hand to the existing Ultravox integration.
    """

    def validate_configuration(self, spec: RuntimeSessionSpecV1) -> None:
        if spec.runtime.pipeline_type != "realtime":
            raise ValueError(
                "UltravoxLegacyRuntimeAdapter only supports the 'realtime' pipeline type."
            )
        if spec.runtime.realtime.provider != "ultravox":
            raise ValueError(
                "UltravoxLegacyRuntimeAdapter only supports the 'ultravox' realtime provider."
            )

    def compile_settings(
        self,
        spec: RuntimeSessionSpecV1,
        voice_agent_config: TenantVoiceAgentConfig | None,
    ) -> dict:
        self.validate_configuration(spec)
        settings = {
            "provider": "ultravox",
            "provider_agent_id": None,
            "system_prompt": spec.instructions.system_prompt,
            "language": spec.language,
            "voice": None,
        }
        if voice_agent_config is not None:
            settings["provider_agent_id"] = voice_agent_config.provider_agent_id
            settings["voice"] = voice_agent_config.default_voice
            if not settings["system_prompt"]:
                settings["system_prompt"] = voice_agent_config.default_system_prompt or ""
        return settings
