from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator


PublicAnswer = StrictStr | StrictInt | StrictBool | None


class PublicVoiceExperienceSubmissionRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    version: StrictInt
    locale: StrictStr
    answers: dict[StrictStr, PublicAnswer]
    consent: StrictBool
    turnstile_token: StrictStr
    hp: StrictStr = ""

    @field_validator("answers", mode="before")
    @classmethod
    def reject_nested_answers(cls, value):
        if not isinstance(value, dict):
            raise ValueError("answers must be an object")
        for answer in value.values():
            if answer is not None and type(answer) not in (str, int, bool):
                raise ValueError("answers contain an unsupported type")
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
    ]
    fields: list[PublicFieldError] = Field(default_factory=list)


class PublicSubmissionCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submissions: Literal[True] = True
    calls: Literal[False] = False


class PublicVoiceExperienceSubmissionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted"] = "accepted"
    context_token: str
    expires_at: datetime
    capabilities: PublicSubmissionCapabilities = PublicSubmissionCapabilities()
