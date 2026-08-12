from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicFieldOption(_PublicModel):
    value: str
    label: str


class PublicVoiceContextField(_PublicModel):
    key: str
    label: str
    description: str | None
    field_type: Literal[
        "text", "textarea", "email", "phone", "integer", "select", "checkbox", "date"
    ]
    required: bool
    options: list[PublicFieldOption]


class PublicVoiceContent(_PublicModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=2000)
    submit_label: str = Field(min_length=1, max_length=80)
    call_label: str = Field(min_length=1, max_length=80)
    success_message: str = Field(min_length=1, max_length=1000)


class PublicVoiceTheme(_PublicModel):
    logo_url: str | None
    primary_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    layout: Literal["centered", "split", "card"]


class PublicVoiceConsent(_PublicModel):
    required: bool
    label: str | None
    privacy_url: str | None


class PublicCapabilities(_PublicModel):
    submissions: bool = True
    calls: bool = True


class PublicVoiceCallSettings(_PublicModel):
    auto_start: bool = False
    show_microphone_help: bool = True
    language: str = Field(default="es", min_length=2, max_length=16)


class PublicVoiceExperienceResponse(_PublicModel):
    slug: str
    locale: str
    version: int
    content: PublicVoiceContent
    theme: PublicVoiceTheme
    consent: PublicVoiceConsent
    fields: list[PublicVoiceContextField]
    call_settings: PublicVoiceCallSettings
    capabilities: PublicCapabilities
