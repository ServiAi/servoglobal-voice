from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class VoiceContextFieldOption(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    value: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=160)


class VoiceContextFieldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=160)
    description: str | None = Field(None, max_length=1000)
    field_type: FieldType
    collection_mode: CollectionMode
    required: bool = False
    position: int = Field(ge=0)
    sensitivity: Sensitivity = "standard"
    validation_json: dict[str, Any] = Field(default_factory=dict)
    options_json: list[VoiceContextFieldOption] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_options(self) -> "VoiceContextFieldRequest":
        if self.field_type == "select" and not self.options_json:
            raise ValueError("Select fields require at least one option.")
        if self.field_type != "select" and self.options_json:
            raise ValueError("Only select fields may define options.")
        values = [option.value for option in self.options_json]
        if len(values) != len(set(values)):
            raise ValueError("Select option values must be unique.")
        return self


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
