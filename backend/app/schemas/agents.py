from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class AgentVoiceConfig(_StrictModel):
    mode: Literal["provider"] = "provider"
    provider: str = Field(max_length=40)
    voice_id: str = Field(min_length=1, max_length=160)


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
