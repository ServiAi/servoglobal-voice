from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator


PublicAnswer = StrictStr | StrictInt | StrictBool | None


class PublicVoiceExperienceSubmissionRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    version: StrictInt
    locale: Literal["es", "en"]
    answers: dict[StrictStr, PublicAnswer]
    consent: StrictBool
    turnstile_token: StrictStr | None = Field(default=None, max_length=2048)
    hp: StrictStr = Field(default="", max_length=200)

    @field_validator("answers", mode="before")
    @classmethod
    def reject_nested_answers(cls, value):
        if not isinstance(value, dict):
            raise ValueError("answers must be an object")
        if len(value) > 100:
            raise ValueError("answers contain too many fields")
        for key, answer in value.items():
            if type(key) is not str or len(key) > 80:
                raise ValueError("answer key is invalid")
            if answer is not None and type(answer) not in (str, int, bool):
                raise ValueError("answers contain an unsupported type")
        if len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()) > 50_000:
            raise ValueError("answers payload is too large")
        return value


class PublicFieldError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    code: Literal[
        "required",
        "unknown_field",
        "invalid_type",
        "too_long",
        "too_short",
        "invalid_option",
        "invalid_format",
        "consent_required",
    ]


class PublicSubmissionError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "experience_version_changed",
        "validation_error",
        "verification_failed",
        "rate_limited",
        "internal_error",
    ]
    fields: list[PublicFieldError] = Field(default_factory=list)


class PublicSubmissionCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submissions: Literal[True] = True
    calls: Literal[True] = True


class PublicVoiceExperienceSubmissionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted"] = "accepted"
    context_token: str
    expires_at: datetime
    capabilities: PublicSubmissionCapabilities = PublicSubmissionCapabilities()
