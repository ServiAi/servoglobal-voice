from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UltravoxToolSummary(_StrictModel):
    name: str
    classification: Literal[
        "provider_native", "serviglobal_supported", "unsupported_client_tool"
    ]


class UltravoxAgentSummary(_StrictModel):
    agent_id: str
    published_revision_id: str | None = None
    name: str
    model: str | None = None
    voice_name: str | None = None
    call_count: int = 0
    tools: list[UltravoxToolSummary] = Field(default_factory=list)
    has_unsupported_client_tools: bool = False


class UltravoxAgentDetail(UltravoxAgentSummary):
    language_hint: str | None = None
    temperature: float | None = None
    first_speaker: str | None = None
    max_duration: str | None = None
    vad_settings: dict[str, Any] | None = None


class UltravoxAgentPage(_StrictModel):
    results: list[UltravoxAgentSummary]
    next_cursor: str | None = None
    previous_cursor: str | None = None
    total: int = 0


class UltravoxVoiceSummary(_StrictModel):
    voice_id: str
    name: str
    language_label: str | None = None
    primary_language: str | None = None
    ownership: Literal["public", "private"]
    billing_style: Literal[
        "VOICE_BILLING_STYLE_INCLUDED", "VOICE_BILLING_STYLE_EXTERNAL"
    ]
    provider: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)
    settings_schema: dict[str, Any] = Field(default_factory=dict)


class UltravoxVoicePage(_StrictModel):
    results: list[UltravoxVoiceSummary]
    next_cursor: str | None = None
    previous_cursor: str | None = None
    total: int = 0


class UltravoxImportResponse(_StrictModel):
    agent_id: str
    draft_version_id: str
    warnings: list[str] = Field(default_factory=list)

