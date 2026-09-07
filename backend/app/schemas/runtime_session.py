"""RuntimeSessionSpec: the typed, versioned contract between Agent Builder
and any future voice runtime (LiveKit, OpenAI Realtime, ...).

Deliberately pure Pydantic with no SQLAlchemy imports -- a runtime process
consuming this contract in a separate deploy must never need TenantAgent,
TenantAgentVersion, or TenantVoiceAgentConfig to understand it. Never put
secrets (API keys, SIP passwords, OAuth tokens) in this contract; those are
resolved by the runtime at execution time via a credential resolver, not
carried here.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.agents import AgentBehavior, AgentIdentity, AgentInstructions


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RealtimeModelSpec(_StrictModel):
    provider: str
    model: str
    settings: dict = Field(default_factory=dict)


class RealtimeRuntimeSpec(_StrictModel):
    pipeline_type: Literal["realtime"]
    realtime: RealtimeModelSpec


class CascadeRuntimeSpec(_StrictModel):
    """Structural placeholder only. No cascade adapter exists yet, and
    AgentService.validate_runtime_selection never allows a version to be
    saved with this pipeline_type -- the compiler should never actually
    produce one today."""

    pipeline_type: Literal["cascade"]


class HalfCascadeRuntimeSpec(_StrictModel):
    """Structural placeholder only, same status as CascadeRuntimeSpec."""

    pipeline_type: Literal["half_cascade"]


RuntimeSpec = Annotated[
    RealtimeRuntimeSpec | CascadeRuntimeSpec | HalfCascadeRuntimeSpec,
    Field(discriminator="pipeline_type"),
]


class RuntimeSessionSpecV1(_StrictModel):
    spec_version: Literal["1"] = "1"
    session_id: str | None = None

    tenant_id: str
    agent_id: str
    agent_version_id: str

    identity: AgentIdentity
    instructions: AgentInstructions
    behavior: AgentBehavior

    language: str
    timezone: str

    runtime: RuntimeSpec

    context: dict = Field(default_factory=dict)
