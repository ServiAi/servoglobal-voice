from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentIdentity(StrictModel):
    name: str
    description: str | None = None


class AgentInstructions(StrictModel):
    role: str = ""
    objective: str = ""
    system_prompt: str = ""
    greeting: str = ""
    closing: str = ""


class AgentBehavior(StrictModel):
    response_style: Literal["precise", "balanced", "creative"] = "balanced"
    interruptions: Literal["conservative", "balanced", "responsive"] = "balanced"
    turn_detection: Literal["automatic", "conservative", "balanced", "responsive"] = "automatic"
    confirmation_strategy: Literal["important_data", "always", "never"] = "important_data"
    agent_first: bool = True


_FORBIDDEN_VOICE_SETTINGS_KEY_PARTS = (
    "api_key", "apikey", "secret", "token", "password", "authorization", "header",
)


class AgentVoiceConfig(StrictModel):
    """Manual mirror of backend/app/schemas/agents.py::AgentVoiceConfig --
    this repo has no shared package between backend and voice-runtime, so the
    two must be kept in sync by hand (pre-existing duplication, not resolved
    by this change). The runtime consumes this field in providers.py.

    Deliberately lightweight: only shape (mode/provider/voice_id types) and
    the generic secret-key guard below. Provider-specific rules (e.g. which
    ElevenLabs settings/ranges are valid for provider_external) are NOT
    duplicated here -- the Control Plane (backend VoiceSelectionService)
    already enforces those before a draft can be saved or published. The
    external_voice mapper in providers.py repeats the provider-specific
    checks before constructing plugin options as defense in depth."""

    mode: Literal["provider", "provider_external"] = "provider"
    provider: str
    voice_id: str
    settings: dict = Field(default_factory=dict)

    @field_validator("settings")
    @classmethod
    def reject_secret_settings(cls, value: dict) -> dict:
        if any(part in str(key).lower() for key in value for part in _FORBIDDEN_VOICE_SETTINGS_KEY_PARTS):
            raise ValueError("Voice settings contain a forbidden secret field")
        return value


class RealtimeModelSpec(StrictModel):
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
        if set(value) - {"join_timeout", "max_duration", "recording_enabled", "initial_output_medium"}:
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


class RealtimeRuntimeSpec(StrictModel):
    pipeline_type: Literal["realtime"]
    realtime: RealtimeModelSpec


class CompiledToolSpec(StrictModel):
    """Manual mirror of backend/app/schemas/runtime_session.py::CompiledToolSpec.
    Carries only what the LLM needs to know a tool exists and how to call
    it -- never a handler reference or credentials. See tool_dispatcher.py
    for how this is turned into a registered RawFunctionTool."""

    key: str
    name: str
    description: str
    input_schema: dict


_FORBIDDEN_VARIABLE_KEY_PARTS = (
    "api_key", "apikey", "secret", "token", "password", "authorization", "header",
)
_MAX_VARIABLE_KEYS = 20
_MAX_VARIABLE_KEY_LENGTH = 60
_MAX_VARIABLE_DEPTH = 2
_MAX_VARIABLES_SERIALIZED_BYTES = 4000


class CallerContext(StrictModel):
    phone: str | None = Field(default=None, max_length=32)


class ContactContext(StrictModel):
    id: str = Field(min_length=1, max_length=36)
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=200)


class LeadContext(StrictModel):
    id: str = Field(min_length=1, max_length=36)
    status: str | None = Field(default=None, max_length=32)
    stage: str | None = Field(default=None, max_length=80)


class CampaignContext(StrictModel):
    name: str | None = Field(default=None, max_length=120)


class SessionContextV1(StrictModel):
    """Manual mirror of backend/app/schemas/session_context.py::SessionContextV1
    (see that file for the full rationale). Every field optional; a
    VoiceSession with no resolved context stays valid and unchanged."""

    schema_version: Literal["1"] = "1"
    source: Literal["webrtc", "inbound", "outbound", "campaign", "manual"] | None = None
    caller: CallerContext | None = None
    contact: ContactContext | None = None
    lead: LeadContext | None = None
    campaign: CampaignContext | None = None
    variables: dict = Field(default_factory=dict)

    @field_validator("variables")
    @classmethod
    def validate_variables(cls, value: dict) -> dict:
        if len(value) > _MAX_VARIABLE_KEYS:
            raise ValueError(f"variables cannot have more than {_MAX_VARIABLE_KEYS} keys")

        def check(node: Any, depth: int) -> None:
            if depth > _MAX_VARIABLE_DEPTH:
                raise ValueError("variables cannot be nested more than 2 levels deep")
            if isinstance(node, dict):
                for key, item in node.items():
                    if len(str(key)) > _MAX_VARIABLE_KEY_LENGTH:
                        raise ValueError(f"variable key '{key}' exceeds {_MAX_VARIABLE_KEY_LENGTH} characters")
                    if any(part in str(key).lower() for part in _FORBIDDEN_VARIABLE_KEY_PARTS):
                        raise ValueError("variables contain a forbidden secret-like key")
                    if isinstance(item, (dict, list)):
                        check(item, depth + 1)
            elif isinstance(node, list):
                for item in node:
                    if isinstance(item, (dict, list)):
                        check(item, depth + 1)

        check(value, 1)
        try:
            serialized = json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("variables must be JSON serializable") from exc
        if len(serialized.encode("utf-8")) > _MAX_VARIABLES_SERIALIZED_BYTES:
            raise ValueError(f"variables exceed {_MAX_VARIABLES_SERIALIZED_BYTES} bytes serialized")
        return value


class RuntimeSessionSpecV1(StrictModel):
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
    runtime: RealtimeRuntimeSpec
    tools: list[CompiledToolSpec] = Field(default_factory=list)
    context: SessionContextV1 = Field(default_factory=SessionContextV1)


class RuntimeEventV1(StrictModel):
    spec_version: Literal["1"] = "1"
    event_id: str
    session_id: str
    event_type: Literal[
        "voice.session.started",
        "voice.provider.session.started",
        "voice.agent.ready",
        "voice.participant.connected",
        "voice.audio.input.started",
        "voice.session.connected",
        "voice.transcript.final",
        "voice.audio.output.started",
        "voice.audio.output.completed",
        "voice.participant.disconnected",
        "voice.session.ended",
        "voice.session.failed",
    ]
    source: Literal["voice-runtime", "livekit", "ultravox"] = "voice-runtime"
    sequence: int | None = None
    payload: dict = Field(default_factory=dict)
    occurred_at: datetime
