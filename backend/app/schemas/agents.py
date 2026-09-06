from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class AgentCreateRequest(_StrictModel):
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
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)


class AgentDraftUpdateRequest(_StrictModel):
    language: str = Field(default="es", min_length=2, max_length=16)
    timezone: str = Field(default="America/Bogota", max_length=80)
    instructions: AgentInstructions = AgentInstructions()
    behavior: AgentBehavior = AgentBehavior()
    voice_agent_config_id: str | None = Field(default=None, max_length=36)
    pipeline_type: Literal["realtime"] = "realtime"
    provider: str = Field(default="ultravox", max_length=40)
    model: str = Field(default="ultravox", max_length=80)


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
