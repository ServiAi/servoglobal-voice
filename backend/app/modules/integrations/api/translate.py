"""Pydantic (HTTP) -> application command translation."""

from __future__ import annotations

from app.modules.integrations.api.schemas import WhatsAppTemplateCreateRequest, WhatsAppTemplateUpdateRequest
from app.modules.integrations.application.dto import (
    WhatsAppTemplateButton,
    WhatsAppTemplateCreateCommand,
    WhatsAppTemplateUpdateCommand,
)


def template_create_command(body: WhatsAppTemplateCreateRequest) -> WhatsAppTemplateCreateCommand:
    data = body.model_dump()
    data["buttons"] = tuple(WhatsAppTemplateButton(**button) for button in data["buttons"])
    return WhatsAppTemplateCreateCommand(**data)


def template_update_command(body: WhatsAppTemplateUpdateRequest) -> WhatsAppTemplateUpdateCommand:
    data = body.model_dump()
    if data["buttons"] is not None:
        data["buttons"] = tuple(WhatsAppTemplateButton(**button) for button in data["buttons"])
    return WhatsAppTemplateUpdateCommand(**data)
