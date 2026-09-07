from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class VoiceExperienceLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_experiences: int = Field(ge=1)
    max_context_fields: int = Field(ge=1)


class VoiceExperiencesFeatureUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    limits: VoiceExperienceLimits


class EmptyLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WhatsAppBusinessCallingFeatureUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class AgentBuilderFeatureUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class TenantFeatureResponse(BaseModel):
    feature_key: str
    enabled: bool
    limits: dict[str, int]
    created_at: datetime
    updated_at: datetime
