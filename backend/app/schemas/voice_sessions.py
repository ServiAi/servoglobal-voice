from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VoiceSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: str
    channel: Literal["webrtc", "sip", "internal_test"] = "internal_test"
    direction: Literal["internal", "outbound"] = "internal"
    purpose: Literal["production", "qa"] = "production"
    qa_context_mode: Literal["preloaded", "conversation"] = "preloaded"
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)
    # Optional, trusted only because this endpoint requires WRITE_ROLES
    # authentication -- never a bare pass-through of unauthenticated or
    # LLM-supplied input. Lets an operator test an agent against a real
    # Contact/Lead's resolved SessionContextV1. See ContactResolutionService.
    contact_id: str | None = Field(default=None, min_length=1, max_length=36)
    lead_id: str | None = Field(default=None, min_length=1, max_length=36)
    # Also trusted-only (see contact_id/lead_id above). Lets an operator
    # test a caller-scoped tool (e.g. crm.create_lead) against a real
    # phone number without a real inbound/outbound call existing yet.
    caller_phone: str | None = Field(default=None, min_length=1, max_length=32)
    variables: dict = Field(default_factory=dict)
    to_phone: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_qa_context(self) -> "VoiceSessionCreateRequest":
        if self.purpose == "qa" and self.qa_context_mode == "conversation" and (
            self.caller_phone or self.contact_id or self.lead_id or self.variables
        ):
            raise ValueError("qa_conversation_context_must_be_empty")
        return self


class WebRTCParticipantTokenResponse(BaseModel):
    voice_session_id: str
    server_url: str
    room_name: str
    participant_token: str
    expires_in: int


class VoiceSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    agent_id: str | None
    agent_version_id: str | None
    crm_voice_call_id: str | None = None
    sip_route_id: str | None = None
    deleted_agent_id: str | None = None
    deleted_agent_version_id: str | None = None
    channel: str
    direction: str
    purpose: str
    runtime_engine: str
    pipeline_type: str
    provider: str
    status: str
    livekit_room_name: str | None
    livekit_dispatch_id: str | None
    livekit_job_id: str | None
    livekit_sip_trunk_id: str | None = None
    livekit_sip_participant_identity: str | None = None
    sip_call_id: str | None = None
    provider_session_id: str | None
    requested_at: datetime
    dispatched_at: datetime | None
    started_at: datetime | None
    runtime_ready_at: datetime | None = None
    connected_at: datetime | None
    ended_at: datetime | None
    end_reason: str | None
    error_code: str | None
    error_message_sanitized: str | None


class VoiceSessionContextResponse(BaseModel):
    caller_phone: str | None = None
    contact_id: str | None = None
    lead_id: str | None = None
    variables: dict = Field(default_factory=dict)


class VoiceSessionEventResponse(BaseModel):
    event_id: str
    event_type: str
    source: str
    sequence: int | None = None
    payload: dict[str, str | int | bool | None] = Field(default_factory=dict)
    occurred_at: datetime


class VoiceSessionEventsResponse(BaseModel):
    session: VoiceSessionResponse
    context: VoiceSessionContextResponse
    events: list[VoiceSessionEventResponse]


class RuntimeEventV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec_version: Literal["1"] = "1"
    event_id: str = Field(min_length=1, max_length=80)
    session_id: str
    event_type: Literal[
        "voice.session.started",
        "voice.provider.session.started",
        "voice.agent.ready",
        "voice.participant.connected",
        "voice.audio.input.started",
        "voice.session.connected",
        "voice.session.ended",
        "voice.session.failed",
        "voice.transcript.final",
        "voice.audio.output.started",
        "voice.audio.output.completed",
        "voice.participant.disconnected",
    ]
    source: Literal["voice-runtime", "livekit", "ultravox"] = "voice-runtime"
    sequence: int | None = Field(default=None, ge=0)
    payload: dict = Field(default_factory=dict)
    occurred_at: datetime


class RuntimeEventAck(BaseModel):
    accepted: bool = True
    duplicate: bool = False


class ToolInvokeRequest(BaseModel):
    """The voice runtime's request to execute one tool call for a live
    session. `arguments` are whatever the LLM produced for the tool's
    input_schema -- validated by AgentService against the bound tool's
    real ToolDefinition.input_schema before any handler runs, never
    trusted at face value."""

    model_config = ConfigDict(extra="forbid")
    arguments: dict = Field(default_factory=dict)


class ToolInvokeResponse(BaseModel):
    result: dict = Field(default_factory=dict)
