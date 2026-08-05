from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VoiceExperienceContent(_StrictModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=2000)
    submit_label: str = Field(min_length=1, max_length=80)
    call_label: str = Field(min_length=1, max_length=80)
    success_message: str = Field(min_length=1, max_length=1000)


class VoiceExperienceTheme(_StrictModel):
    logo_url: AnyHttpUrl | None = None
    primary_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    layout: Literal["centered", "split", "card"]

    @field_validator("logo_url")
    @classmethod
    def require_https_logo(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is not None and value.scheme != "https":
            raise ValueError("logo_url must use HTTPS")
        return value


class VoiceExperienceConsent(_StrictModel):
    required: bool
    label: str = Field(min_length=1, max_length=1000)
    privacy_url: AnyHttpUrl | None = None

    @field_validator("privacy_url")
    @classmethod
    def require_https_privacy(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is not None and value.scheme != "https":
            raise ValueError("privacy_url must use HTTPS")
        return value


class VoiceExperienceCallSettings(_StrictModel):
    auto_start: bool
    show_microphone_help: bool
    language: str = Field(min_length=2, max_length=16, pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")


class VoiceExperienceWriteRequest(_StrictModel):
    agent_config_id: str = Field(min_length=1, max_length=36)
    context_schema_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=160)
    default_locale: str = Field(
        min_length=2, max_length=16, pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$"
    )
    content: VoiceExperienceContent
    theme: VoiceExperienceTheme
    consent: VoiceExperienceConsent
    call_settings: VoiceExperienceCallSettings

class VoiceExperienceResponse(_StrictModel):
    id: str
    agent_config_id: str
    context_schema_id: str
    name: str
    slug: str
    status: Literal["draft", "published", "unpublished", "archived"]
    default_locale: str
    content: VoiceExperienceContent
    theme: VoiceExperienceTheme
    consent: VoiceExperienceConsent
    call_settings: VoiceExperienceCallSettings
    published_version_id: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class VoiceExperienceVersionResponse(_StrictModel):
    id: str
    experience_id: str
    version: int
    agent_config_id: str
    context_schema_id: str
    name: str
    slug: str
    default_locale: str
    content: VoiceExperienceContent
    theme: VoiceExperienceTheme
    consent: VoiceExperienceConsent
    call_settings: VoiceExperienceCallSettings
    published_at: datetime
    created_at: datetime
