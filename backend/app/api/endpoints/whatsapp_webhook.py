from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.whatsapp_message_service import WhatsAppMessageService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/webhook/whatsapp", tags=["WhatsApp"])


@router.get("")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
) -> Any:
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified")
        try:
            return int(hub_challenge)
        except (TypeError, ValueError):
            return hub_challenge
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid verification token")


@router.post("")
async def receive_whatsapp_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload")
    result = WhatsAppMessageService(db).handle_webhook_payload(payload)
    logger.info("WhatsApp webhook processed statuses=%s inbound=%s", result["statuses"], result["inbound"])
    return {"status": "ok", **result}
