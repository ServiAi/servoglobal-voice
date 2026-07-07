from __future__ import annotations

import json
import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.voice_webhook_service import VoiceWebhookService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice", tags=["Voice Webhooks"])


@router.post("/webhook/{provider}")
async def voice_webhook(
    provider: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    raw_body = await request.body()
    
    # Try parsing json body
    try:
        payload = json.loads(raw_body.decode())
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON body",
        ) from exc

    service = VoiceWebhookService(db)

    # Resolve call to get tenant signature validation
    call = service.resolve_call_by_metadata_or_provider_id(payload)
    if call:
        config = service.config_service.get_provider_config(call.tenant_id, provider)
        if config and config.webhook_secret_encrypted:
            secret = service.config_service.decrypt_webhook_secret(config)
            if secret:
                try:
                    service.verify_webhook_signature(request, raw_body, secret)
                except HTTPException:
                    # Reraise signature failure
                    raise
                except Exception as exc:
                    logger.error("Error verifying webhook signature: %s", str(exc))
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Webhook signature verification failed",
                    ) from exc

    try:
        result = service.handle_provider_event(provider, payload)
        return result
    except Exception as exc:
        logger.error("Error processing voice webhook: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing error: {str(exc)}",
        ) from exc
