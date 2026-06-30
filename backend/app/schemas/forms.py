from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class FormFieldRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=80)
    label: str = Field(..., min_length=1, max_length=160)
    field_type: str = Field(default="text", max_length=32)
    required: bool = False
    options: list[str] = Field(default_factory=list)
    position: int = 0


class FormCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    description: Optional[str] = None
    status: str = "active"
    fields: list[FormFieldRequest] = Field(default_factory=list)


class FormFieldResponse(BaseModel):
    id: str
    key: str
    label: str
    field_type: str
    required: bool
    options: list[str]
    position: int


class FormResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    status: str
    fields: list[FormFieldResponse]


class FormTokenCreateRequest(BaseModel):
    lead_id: str = Field(..., min_length=1)
    expires_in_days: int = Field(default=7, ge=1, le=90)


class FormTokenResponse(BaseModel):
    id: str
    form_link: str
    expires_at: datetime


class PublicFormResponse(BaseModel):
    form: FormResponse
    lead_preview: dict[str, Any]


class PublicFormSubmitRequest(BaseModel):
    answers: dict[str, str | bool | None] = Field(default_factory=dict)
    hp: Optional[str] = None


class PublicFormSubmitResponse(BaseModel):
    status: str
    submission_id: str
