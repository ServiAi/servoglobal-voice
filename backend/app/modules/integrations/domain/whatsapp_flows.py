from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


FlowCategory = Literal[
    "SIGN_UP",
    "SIGN_IN",
    "APPOINTMENT_BOOKING",
    "LEAD_GENERATION",
    "CONTACT_US",
    "CUSTOMER_SUPPORT",
    "SURVEY",
    "OTHER",
]
FlowComponentType = Literal[
    "heading",
    "body",
    "text_input",
    "email_input",
    "phone_input",
    "number_input",
    "text_area",
    "dropdown",
    "radio",
    "checkbox",
    "date",
    "footer",
]


class FlowOption(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_\-]+$")
    title: str = Field(min_length=1, max_length=30)
    context_value: str | None = Field(None, max_length=160)


class NavigationAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["navigate", "complete"]
    target_screen_id: str | None = Field(None, max_length=80, pattern=r"^[A-Z][A-Z0-9_]*$")

    @model_validator(mode="after")
    def validate_target(self) -> "NavigationAction":
        if self.type == "navigate" and not self.target_screen_id:
            raise ValueError("Navigate actions require a target screen.")
        if self.type == "complete" and self.target_screen_id:
            raise ValueError("Complete actions cannot define a target screen.")
        return self


class ContextBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_field_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    prefill_supported_later: bool = False


class FlowComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    type: FlowComponentType
    label: str | None = Field(None, max_length=160)
    text: str | None = Field(None, max_length=4096)
    placeholder: str | None = Field(None, max_length=160)
    required: bool = False
    options: list[FlowOption] = Field(default_factory=list, max_length=20)
    action: NavigationAction | None = None
    binding: ContextBinding | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "FlowComponent":
        if self.type in {"heading", "body"} and not self.text:
            raise ValueError(f"{self.type} requires text.")
        if self.type not in {"heading", "body"} and not self.label:
            raise ValueError(f"{self.type} requires a label.")
        if self.type in {"dropdown", "radio"} and not self.options:
            raise ValueError(f"{self.type} requires at least one option.")
        if self.type not in {"dropdown", "radio"} and self.options:
            raise ValueError("Only dropdown and radio components accept options.")
        if self.type == "footer" and not self.action:
            raise ValueError("Footer requires an action.")
        if self.type != "footer" and self.action:
            raise ValueError("Only footer components accept an action.")
        if self.type in {"heading", "body", "footer"} and self.binding:
            raise ValueError("Only input components accept context bindings.")
        option_ids = [option.id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("Option IDs must be unique.")
        return self


class FlowScreen(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Z][A-Z0-9_]*$")
    title: str = Field(min_length=1, max_length=80)
    terminal: bool = False
    components: list[FlowComponent] = Field(default_factory=list, max_length=50)


class FlowBuilder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    screens: list[FlowScreen] = Field(min_length=1, max_length=20)


class WhatsAppFlowCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    flow_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    categories: list[FlowCategory] = Field(min_length=1, max_length=3)
    source_mode: Literal["visual", "context_schema"] = "visual"
    context_schema_id: str | None = None
    builder: FlowBuilder | None = None

    @model_validator(mode="after")
    def validate_source(self) -> "WhatsAppFlowCreateRequest":
        if self.source_mode == "context_schema" and not self.context_schema_id:
            raise ValueError("Context schema source requires context_schema_id.")
        if self.source_mode == "visual" and self.context_schema_id:
            raise ValueError("Visual source cannot define context_schema_id.")
        return self


class WhatsAppFlowUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(None, min_length=1, max_length=160)
    categories: list[FlowCategory] | None = Field(None, min_length=1, max_length=3)
    builder: FlowBuilder | None = None


class MetaFlowValidationError(BaseModel):
    model_config = ConfigDict(extra="ignore")

    error: str | None = None
    error_type: str | None = None
    message: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    column_start: int | None = None
    column_end: int | None = None


class WhatsAppFlowResponse(BaseModel):
    id: str
    flow_key: str
    version: int
    parent_flow_id: str | None
    name: str
    categories: list[FlowCategory]
    source_mode: Literal["visual", "context_schema"]
    context_schema_id: str | None
    context_schema_snapshot: dict | None
    status: Literal["draft", "synced", "published", "deprecated", "error"]
    meta_status: str | None
    provider_flow_id: str | None
    builder_schema_version: int
    builder: FlowBuilder
    compiled_flow_json: dict | None
    compiled_hash: str | None
    validation_errors: list[MetaFlowValidationError]
    last_synced_at: datetime | None
    published_at: datetime | None
    deprecated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WhatsAppFlowCompileResponse(BaseModel):
    compiled_flow_json: dict
    compiled_hash: str


class WhatsAppFlowContextSchemaResponse(BaseModel):
    id: str
    name: str
    schema_key: str
    version: int
    status: str
    field_count: int
