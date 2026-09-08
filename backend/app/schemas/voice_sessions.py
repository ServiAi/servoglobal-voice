from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VoiceSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: str
    channel: Literal["internal_test"] = "internal_test"
    direction: Literal["internal"] = "internal"
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)


class VoiceSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    agent_id: str
    agent_version_id: str
    channel: str
    direction: str
    runtime_engine: str
    pipeline_type: str
    provider: str
    status: str
    livekit_room_name: str | None
    livekit_dispatch_id: str | None
    livekit_job_id: str | None
    provider_session_id: str | None
    requested_at: datetime
    dispatched_at: datetime | None
    started_at: datetime | None
    connected_at: datetime | None
    ended_at: datetime | None
    end_reason: str | None
    error_code: str | None
    error_message_sanitized: str | None


class RuntimeEventV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec_version: Literal["1"] = "1"
    event_id: str = Field(min_length=1, max_length=80)
    session_id: str
    event_type: Literal[
        "voice.session.started",
        "voice.session.connected",
        "voice.session.ended",
        "voice.session.failed",
        "voice.transcript.final",
    ]
    source: Literal["voice-runtime", "livekit", "ultravox"] = "voice-runtime"
    sequence: int | None = Field(default=None, ge=0)
    payload: dict = Field(default_factory=dict)
    occurred_at: datetime


class RuntimeEventAck(BaseModel):
    accepted: bool = True
    duplicate: bool = False
