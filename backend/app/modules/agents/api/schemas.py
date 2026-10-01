"""Agent Builder HTTP contracts: request/response models of the
/api/v1/agents routes (and the use-case inputs AgentService consumes).
Pure value objects live in app.modules.agents.domain.contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.modules.agents.domain.contracts import (
    AgentBehavior,
    AgentIdentity,
    AgentInstructions,
    AgentToolBinding,
    AgentVoiceConfig,
    ProviderAgentReference,
    ProviderManagedOverrides,
    _reject_secret_keys,
    _StrictModel,
)


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
    # comes from app.modules.tools.domain.registry, validated by AgentService --
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


class AgentToolContextRequirementResponse(_StrictModel):
    path: str
    required: bool
    description: str


class AgentToolCatalogEntryResponse(_StrictModel):
    """One Tool Registry entry, annotated for the current tenant.
    `available` is only ever true for `status="available"` tools whose
    `required_integration` is actually configured for this tenant --
    `planned` tools always report `available=False` so the Agent Builder
    UI never lets them be enabled. `input_schema` is the tool's static/base
    LLM schema (see ToolDefinition's docstring) -- for a configurable tool
    (`configuration_required=True`) the real, binding-aware schema the
    model will see is computed at compile/dispatch time by
    PlatformToolContractService, not shown here."""

    key: str
    name: str
    description: str
    status: Literal["available", "planned"]
    required_integration: Literal["booking", "whatsapp", "crm", "chatwoot"] | None
    available: bool
    input_schema: dict[str, Any]
    source: Literal["platform", "custom"] = "platform"
    context_requirements: list[AgentToolContextRequirementResponse] = Field(default_factory=list)
    binding_config_schema: dict[str, Any] = Field(default_factory=dict)
    configuration_required: bool = False


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


def agent_response(agent: Any) -> AgentResponse:
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        status=agent.status,
        published_version_id=agent.published_version_id,
        draft_version_id=agent.draft_version_id,
        archived_at=agent.archived_at,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def version_response(version: Any) -> AgentVersionResponse:
    return AgentVersionResponse(
        id=version.id,
        agent_id=version.agent_id,
        version=version.version,
        status=version.status,
        language=version.language,
        timezone=version.timezone,
        identity=AgentIdentity.model_validate(version.identity_json),
        instructions=AgentInstructions.model_validate(version.instructions_json),
        behavior=AgentBehavior.model_validate(version.behavior_json),
        runtime_binding=version.runtime_binding_json,
        voice_agent_config_id=version.voice_agent_config_id,
        published_at=version.published_at,
        created_at=version.created_at,
    )
