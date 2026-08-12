from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PublicVoiceCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    context_token: str = Field(min_length=32, max_length=512)


class PublicVoiceCallCapabilities(BaseModel):
    submissions: bool = True
    calls: bool = True


class PublicVoiceCallResponse(BaseModel):
    status: Literal["ready"]
    join_url: str
    capabilities: PublicVoiceCallCapabilities = PublicVoiceCallCapabilities()


PublicCallErrorCode = Literal[
    "experience_unavailable",
    "experience_version_changed",
    "call_already_started",
    "call_state_conflict",
    "context_session_unavailable",
    "context_session_expired",
    "validation_error",
    "rate_limited",
    "call_unavailable",
    "call_provider_unavailable",
    "internal_error",
]


class PublicVoiceCallError(BaseModel):
    code: PublicCallErrorCode
