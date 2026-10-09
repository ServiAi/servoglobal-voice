from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VoiceContextOptionSnapshot:
    value: str
    label: str


@dataclass(frozen=True, slots=True)
class VoiceContextFieldSnapshot:
    key: str
    label: str
    description: str | None
    field_type: str
    collection_mode: str
    required: bool
    position: int
    options: tuple[VoiceContextOptionSnapshot, ...]


@dataclass(frozen=True, slots=True)
class VoiceContextSchemaSnapshot:
    id: str
    schema_key: str
    version: int
    name: str
    description: str | None
    fields: tuple[VoiceContextFieldSnapshot, ...]


@dataclass(frozen=True, slots=True)
class VoiceRuntimeWebhookTarget:
    """Framework-free handle for a runtime call a provider webhook refers to."""

    tenant_id: str
    runtime_call_id: str
    voice_call_id: str
    provider: str
    provider_call_id: str | None
    contact_id: str | None
    lead_id: str | None
