"""Agent Builder value objects: pure, provider-agnostic, no HTTP/DB.

Persisted inside TenantAgentVersion JSON columns and reused by the
RuntimeSessionSpecV1 runtime contract (see agents.public).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentIdentity(_StrictModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)


class AgentInstructions(_StrictModel):
    role: str = Field(default="", max_length=200)
    objective: str = Field(default="", max_length=2000)
    system_prompt: str = Field(default="", max_length=8000)
    greeting: str = Field(default="", max_length=1000)
    closing: str = Field(default="", max_length=1000)


class AgentBehavior(_StrictModel):
    response_style: Literal["precise", "balanced", "creative"] = "balanced"
    interruptions: Literal["conservative", "balanced", "responsive"] = "balanced"
    turn_detection: Literal["automatic", "conservative", "balanced", "responsive"] = "automatic"
    confirmation_strategy: Literal["important_data", "always", "never"] = "important_data"
    agent_first: bool = True


class ProviderAgentReference(_StrictModel):
    agent_id: str = Field(min_length=1, max_length=120)
    observed_published_revision_id: str | None = Field(default=None, max_length=120)


_FORBIDDEN_VOICE_SETTINGS_KEY_PARTS = (
    "api_key", "apikey", "secret", "token", "password", "authorization", "header",
)


def _reject_secret_keys(value: dict[str, Any]) -> dict[str, Any]:
    if any(part in str(key).lower() for key in value for part in _FORBIDDEN_VOICE_SETTINGS_KEY_PARTS):
        raise ValueError("Settings contain a forbidden secret field")
    return value


class AgentVoiceConfig(_StrictModel):
    """A voice selection for a realtime agent.

    `mode="provider"` is a voice known/managed by the realtime provider's own
    catalog (e.g. an Ultravox voice) -- it does not imply the provider
    synthesizes the audio itself, only that ServiGlobal doesn't need to know
    which TTS backs it. `mode="provider_external"` asks the realtime provider
    to delegate synthesis to a named external TTS provider (e.g. Ultravox's
    externalVoice -> ElevenLabs) using an ID from that provider's own
    namespace, never the realtime provider's voice IDs.

    This schema validates shape only: `mode`/`provider`/`voice_id` types and
    that `settings` is a plain mapping with no secret-like keys. It
    deliberately does NOT know which settings keys or ranges a given
    (mode, provider) actually allows -- that is provider-specific business
    logic and lives in app.modules.agents.domain.voice_selection, which has the sibling realtime
    provider/model context this schema doesn't, and is the single place
    that logic should be read or changed.
    """

    mode: Literal["provider", "provider_external"] = "provider"
    provider: str = Field(max_length=40)
    voice_id: str = Field(min_length=1, max_length=160)
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("settings")
    @classmethod
    def reject_secret_settings(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_secret_keys(value)


class AgentToolBinding(_StrictModel):
    """One tool bound to a serviglobal_managed agent version. `key` is
    validated against the platform Tool Registry (app.modules.tools.domain.registry)
    by AgentService, not here -- this schema validates shape only: key
    length, no duplicate enforcement (that needs the whole list), and no
    secrets in `config`. `config` is binding-time configuration (e.g. which
    WhatsApp template to use), never the per-call arguments a tool
    invocation carries -- those come from the LLM at call time and are
    validated against ToolDefinition.input_schema separately.
    """

    key: str = Field(min_length=1, max_length=80)
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def reject_secret_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_secret_keys(value)


class ProviderManagedOverrides(_StrictModel):
    join_timeout: str | None = Field(default=None, max_length=24)
    max_duration: str | None = Field(default=None, max_length=24)
    recording_enabled: bool | None = None
    initial_output_medium: Literal["MESSAGE_MEDIUM_VOICE", "MESSAGE_MEDIUM_TEXT"] | None = None
