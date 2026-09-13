from __future__ import annotations

from datetime import datetime
from typing import Literal

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
    by this change). Runtime execution does not consume this field yet
    (that lands in later phases); this only tightens the contract shape."""

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
    context: dict = Field(default_factory=dict)

    @field_validator("context")
    @classmethod
    def reject_secret_context_keys(cls, value: dict) -> dict:
        forbidden = ("api_key", "secret", "token", "password", "authorization")
        pending = [value]
        while pending:
            current = pending.pop()
            for key, item in current.items():
                if any(part in str(key).lower() for part in forbidden):
                    raise ValueError("Runtime context contains a forbidden secret field")
                if isinstance(item, dict):
                    pending.append(item)
        return value


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
