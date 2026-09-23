from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    logic and lives in VoiceSelectionService, which has the sibling realtime
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
    validated against the platform Tool Registry (app.domain.tool_registry)
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


class _RuntimeSelection(_StrictModel):
    management_mode: Literal["serviglobal_managed", "provider_managed"] = "serviglobal_managed"
    provider_agent: ProviderAgentReference | None = None
    voice: AgentVoiceConfig | None = None
    provider_overrides: ProviderManagedOverrides | None = None
    # Provider/model runtime parameters (e.g. temperature) for a
    # serviglobal_managed agent. Shape-only here (no secrets); which keys
    # are actually allowed for a given (provider, model) is registry-driven
    # business logic, validated by AgentService against
    # voice_registry.validate_model_settings(), not by this schema.
    settings: dict[str, Any] = Field(default_factory=dict)
    # Tools bound to this agent version. Which keys are known/executable
    # comes from app.domain.tool_registry, validated by AgentService --
    # this schema only validates shape (see AgentToolBinding).
    tools: list[AgentToolBinding] = Field(default_factory=list)

    @field_validator("settings")
    @classmethod
    def reject_secret_runtime_settings(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_secret_keys(value)

    @model_validator(mode="after")
    def validate_management_mode(self):
        if self.management_mode == "provider_managed" and self.provider_agent is None:
            raise ValueError("provider_agent is required for provider_managed agents")
        if self.management_mode == "serviglobal_managed" and self.provider_agent is not None:
            raise ValueError("provider_agent is only valid for provider_managed agents")
        return self


class AgentCreateRequest(_RuntimeSelection):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    language: str = Field(default="es", min_length=2, max_length=16)
    timezone: str = Field(default="America/Bogota", max_length=80)
    instructions: AgentInstructions = AgentInstructions()
    behavior: AgentBehavior = AgentBehavior()
    voice_agent_config_id: str | None = Field(default=None, max_length=36)
    pipeline_type: Literal["realtime"] = "realtime"
    provider: str = Field(default="ultravox", max_length=40)
    model: str = Field(default="ultravox", max_length=80)


class AgentUpdateRequest(_StrictModel):
    """Legacy identity-only update, kept for API compatibility.

    The Agent Builder UI no longer uses this: it PATCHes name/description
    together with the rest of the draft via AgentDraftUpdateRequest so both
    land in one transaction. This endpoint still works standalone for any
    other caller, but on a mutable agent with an open draft it will leave
    that draft's identity_json snapshot stale until the draft is next saved.
    """

    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)


class AgentDraftUpdateRequest(_RuntimeSelection):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    language: str = Field(default="es", min_length=2, max_length=16)
    timezone: str = Field(default="America/Bogota", max_length=80)
    instructions: AgentInstructions = AgentInstructions()
    behavior: AgentBehavior = AgentBehavior()
    voice_agent_config_id: str | None = Field(default=None, max_length=36)
    pipeline_type: Literal["realtime"] = "realtime"
    provider: str = Field(default="ultravox", max_length=40)
    model: str = Field(default="ultravox", max_length=80)


class AgentPublishRequest(_StrictModel):
    """Optional concurrency guard: when set, publish fails with a conflict
    if the agent's current draft_version_id no longer matches (someone else
    saved or published a different draft in the meantime)."""

    expected_draft_version_id: str | None = None


class AgentToolCatalogEntryResponse(_StrictModel):
    """One Tool Registry entry, annotated for the current tenant.
    `available` is only ever true for `status="available"` tools whose
    `required_integration` is actually configured for this tenant --
    `planned` tools always report `available=False` so the Agent Builder
    UI never lets them be enabled."""

    key: str
    name: str
    description: str
    status: Literal["available", "planned"]
    required_integration: Literal["booking", "whatsapp", "crm", "chatwoot"] | None
    available: bool
    input_schema: dict[str, Any]
    source: Literal["platform", "custom"] = "platform"


class AgentResponse(_StrictModel):
    id: str
    name: str
    description: str | None
    status: Literal["draft", "active", "archived"]
    published_version_id: str | None
    draft_version_id: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgentVersionResponse(_StrictModel):
    id: str
    agent_id: str
    version: int
    status: Literal["draft", "published", "superseded"]
    language: str
    timezone: str
    identity: AgentIdentity
    instructions: AgentInstructions
    behavior: AgentBehavior
    runtime_binding: dict
    voice_agent_config_id: str | None
    published_at: datetime | None
    created_at: datetime
