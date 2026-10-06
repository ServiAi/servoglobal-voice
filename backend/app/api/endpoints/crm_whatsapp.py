from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.modules.identity.public import AuthContext, require_roles
from app.db.session import get_db
from app.modules.integrations.public import WhatsAppFacade
from app.schemas.crm import (
    WhatsAppActionRequest,
    WhatsAppActionResponse,
    WhatsAppMessageResponse,
)

router = APIRouter(prefix="/api/v1/crm", tags=["CRM"])


@router.post("/leads/{lead_id}/actions/whatsapp", response_model=WhatsAppActionResponse)
def send_lead_whatsapp(
    lead_id: str,
    body: WhatsAppActionRequest | None = None,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    facade = WhatsAppFacade(db)
    request = body or WhatsAppActionRequest()
    command = {
        "tenant_id": context.tenant.id,
        "lead_id": lead_id,
        "template_key": request.template_key,
        "message": request.message,
        "variables": request.variables,
    }
    try:
        result = facade.preview_lead_message(**command) if request.preview_only else facade.send_lead_message(**command)
    except ValueError as exc:
        code = status.HTTP_404_NOT_FOUND if str(exc) == "Lead not found" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error_message or "WhatsApp send failed.")
    return WhatsAppActionResponse(
        status=result.status,
        whatsapp_message_id=result.whatsapp_message_id,
        provider_message_id=result.provider_message_id,
        preview=dict(result.preview) if result.preview is not None else None,
        error_message=result.error_message,
    )


@router.get("/leads/{lead_id}/messages", response_model=list[WhatsAppMessageResponse])
def list_lead_whatsapp_messages(
    lead_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return [WhatsAppMessageResponse.model_validate(message, from_attributes=True) for message in WhatsAppFacade(db).list_lead_messages(context.tenant.id, lead_id)]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
