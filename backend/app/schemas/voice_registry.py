from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VoiceProviderResponse(_StrictModel):
    key: str
    name: str
    status: Literal["active", "planned"]
    supports_managed_credentials: bool
    supports_byok: bool


class ParameterSpecResponse(_StrictModel):
    supported: bool
    min: float | None = None
    max: float | None = None
    default: Any = None


class VoiceModelResponse(_StrictModel):
    id: str
    provider_key: str
    key: str
    name: str
    model_type: Literal["stt", "llm", "tts", "realtime"]
    implementation_status: Literal["planned", "available", "deprecated"]
    capabilities: dict[str, bool]
    parameters: dict[str, ParameterSpecResponse]
