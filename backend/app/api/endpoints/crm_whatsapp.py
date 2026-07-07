from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.db.session import get_db
from app.schemas.crm import WhatsAppActionRequest, WhatsAppActionResponse, WhatsAppMessageResponse
from app.services.whatsapp_message_service import WhatsAppMessageService


router = APIRouter(prefix="/api/v1/crm", tags=["CRM"])


@router.post("/leads/{lead_id}/actions/whatsapp", response_model=WhatsAppActionResponse)
def send_lead_whatsapp(
    lead_id: str,
    body: WhatsAppActionRequest | None = None,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    service = WhatsAppMessageService(db)
    request = body or WhatsAppActionRequest()
    try:
        result = (
            service.preview_lead_whatsapp(context.tenant.id, lead_id, request)
            if request.preview_only
            else service.send_lead_whatsapp(context.tenant.id, lead_id, request)
        )
    except ValueError as exc:
        code = status.HTTP_404_NOT_FOUND if str(exc) == "Lead not found" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error_message or "WhatsApp send failed.")
    return service.action_response(result)


@router.get("/leads/{lead_id}/messages", response_model=list[WhatsAppMessageResponse])
def list_lead_whatsapp_messages(
    lead_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return WhatsAppMessageService(db).list_lead_messages(context.tenant.id, lead_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
