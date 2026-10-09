from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VoiceContextFieldSnapshot:
    key: str
    label: str
    description: str | None
    field_type: str
    collection_mode: str
    required: bool
    position: int
    options: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VoiceContextSchemaSnapshot:
    id: str
    schema_key: str
    version: int
    name: str
    description: str | None
    fields: tuple[VoiceContextFieldSnapshot, ...]
