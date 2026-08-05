from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


FieldType = Literal["text", "textarea", "email", "phone", "integer", "select", "checkbox", "date"]
CollectionMode = Literal[
    "ask_if_missing",
    "prefill_and_confirm",
    "trust_prefill",
    "internal_only",
    "collect_during_call",
]
SchemaStatus = Literal["draft", "active", "archived"]
Sensitivity = Literal["standard", "sensitive"]


class VoiceContextFieldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=160)
    field_type: FieldType
    collection_mode: CollectionMode
    required: bool = False
    position: int = Field(ge=0)
    sensitivity: Sensitivity = "standard"
    validation_json: dict[str, Any] = Field(default_factory=dict)
    options_json: list[dict[str, Any]] = Field(default_factory=list)


class VoiceContextFieldResponse(VoiceContextFieldRequest):
    id: str


class VoiceContextSchemaCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(None, max_length=2000)


class VoiceContextSchemaMetaUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(None, max_length=2000)


class VoiceContextSchemaResponse(BaseModel):
    id: str
    agent_config_id: str
    schema_key: str
    version: int
    status: SchemaStatus
    name: str
    description: str | None
    fields: list[VoiceContextFieldResponse]
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None
    archived_at: datetime | None


class VoiceContextSchemaSummaryResponse(BaseModel):
    id: str
    agent_config_id: str
    schema_key: str
    version: int
    status: SchemaStatus
    name: str
    field_count: int
    updated_at: datetime
