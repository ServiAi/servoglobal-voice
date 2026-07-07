from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.whatsapp_message_service import WhatsAppMessageService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/webhook/whatsapp", tags=["WhatsApp"])


def _signature_is_valid(body: bytes, signature: str | None) -> bool:
    if not settings.META_APP_SECRET:
        return True
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(settings.META_APP_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature.removeprefix("sha256="), expected)


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
    body = await request.body()
    if not _signature_is_valid(body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook signature")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload")
    result = WhatsAppMessageService(db).handle_webhook_payload(payload)
    logger.info("WhatsApp webhook processed statuses=%s inbound=%s", result["statuses"], result["inbound"])
    return {"status": "ok", **result}
