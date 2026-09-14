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

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.agents import AgentBehavior, AgentIdentity, AgentInstructions, AgentVoiceConfig
from app.schemas.session_context import SessionContextV1


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RealtimeModelSpec(_StrictModel):
    provider: str
    model: str
    settings: dict = Field(default_factory=dict)
    management_mode: Literal["serviglobal_managed", "provider_managed"] = "serviglobal_managed"
    provider_agent: dict | None = None
    voice: AgentVoiceConfig | None = None
    provider_overrides: dict = Field(default_factory=dict)
    provider_extensions: dict = Field(default_factory=dict)

    @field_validator("settings")
    @classmethod
    def reject_secret_settings(cls, value: dict) -> dict:
        if any(part in str(key).lower() for key in value for part in ("api_key", "secret", "token", "password", "authorization")):
            raise ValueError("Runtime settings contain a forbidden secret field")
        return value

    @field_validator("provider_agent")
    @classmethod
    def validate_provider_agent(cls, value: dict | None) -> dict | None:
        if value is not None and (
            set(value) - {"agent_id", "observed_published_revision_id"}
            or not isinstance(value.get("agent_id"), str)
        ):
            raise ValueError("Invalid provider agent reference")
        return value

    @field_validator("provider_overrides")
    @classmethod
    def validate_provider_overrides(cls, value: dict) -> dict:
        allowed = {"join_timeout", "max_duration", "recording_enabled", "initial_output_medium"}
        if set(value) - allowed:
            raise ValueError("Runtime provider overrides are not allowlisted")
        return value

    @field_validator("provider_extensions")
    @classmethod
    def reject_secret_extensions(cls, value: dict) -> dict:
        pending: list[object] = [value]
        while pending:
            current = pending.pop()
            if isinstance(current, dict):
                for key, item in current.items():
                    if any(part in str(key).lower() for part in ("api_key", "secret", "token", "password", "authorization", "header")):
                        raise ValueError("Provider extensions contain a forbidden secret field")
                    pending.append(item)
            elif isinstance(current, list):
                pending.extend(current)
        return value


class CompiledToolSpec(_StrictModel):
    """A tool the runtime should register with the LLM/provider for this
    session. Deliberately carries only what the LLM needs to know a tool
    exists and how to call it (key/name/description/input_schema) -- never
    the binding's `config` (e.g. which WhatsApp template), which the
    backend re-resolves itself when the tool is actually invoked, and
    never a handler reference or credentials. Compiled once by
    AgentCompilerService from runtime_binding_json["tools"] against
    app.domain.tool_registry; nothing here is trusted at face value by the
    tool-invoke endpoint, which re-validates against the published
    version's own binding."""

    key: str
    name: str
    description: str
    input_schema: dict


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

    tools: list[CompiledToolSpec] = Field(default_factory=list)

    # Typed, versioned business context (caller/contact/lead/campaign/
    # variables) resolved by ContactResolutionService and snapshotted onto
    # VoiceSession.session_context_json -- see schemas/session_context.py.
    # SessionContextV1's own secret-key/size/depth validators cover this
    # field; an empty dict `{}` (today's default) still validates fine
    # (every field on SessionContextV1 is optional).
    context: SessionContextV1 = Field(default_factory=SessionContextV1)
