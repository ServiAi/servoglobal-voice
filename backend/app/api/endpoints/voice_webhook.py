from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.notifications.public import publish_call_event
from app.modules.telephony.public import CANONICAL_SIP_PROVIDER
from app.modules.voice.public import VoiceSessionFacade
from app.modules.voice_experiences.public import HistoricalSettlementOwnershipError, create_historical_call_settlement
from app.services.billing_duration import provider_duration_to_minutes
from app.services.voice_webhook_service import VoiceWebhookService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice", tags=["Voice Webhooks"])


def _billed_minutes(payload: dict[str, Any], call_obj: dict[str, Any]) -> Decimal | None:
    """``billedMinutes`` wins; otherwise the provider's ``billedDuration`` (e.g. ``75s`` -> 1.25)."""
    raw = call_obj.get("billedMinutes") or payload.get("billedMinutes")
    if raw is not None:
        try:
            return Decimal(str(raw))
        except (InvalidOperation, ValueError):
            return None
    return provider_duration_to_minutes(call_obj.get("billedDuration") or payload.get("billedDuration"))

_NOTIFIABLE_CALL_STATUSES = {"completed", "failed", "no_answer", "busy"}


@router.post("/webhook/{provider}")
async def voice_webhook(
    provider: str,
    request: Request,
    background_tasks: BackgroundTasks,
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
    if call and (
        call.provider == CANONICAL_SIP_PROVIDER
        or call.id in VoiceSessionFacade(db).agent_ids_by_crm_call(call.tenant_id, [call.id])
    ):
        # A call backed by a VoiceSession (LiveKit SIP, or a public WebRTC launch) takes its lifecycle
        # from the voice runtime's events: a provider webhook never mutates it. Only historical
        # provider-originated calls, which have no session, are still reconciled below.
        return {"status": "ignored", "processed": False}
    signature_verified = False
    if call:
        config = service.config_service.get_provider_config(call.tenant_id, provider)
        if config and config.webhook_secret_encrypted:
            secret = service.config_service.decrypt_webhook_secret(config)
            if secret:
                try:
                    service.verify_webhook_signature(request, raw_body, secret)
                    signature_verified = True
                except HTTPException:
                    # Reraise signature failure
                    raise
                except Exception as exc:
                    logger.error("Error verifying webhook signature: %s", type(exc).__name__)
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Webhook signature verification failed",
                    ) from exc

    event_type = str(payload.get("event") or payload.get("event_type") or payload.get("type") or "")
    if call and event_type == "call.billed":
        settlement = create_historical_call_settlement(db)
        if settlement.owns(call.id):
            # Late billing of a historical provider-originated call: settle Analytics only (never the
            # lifecycle, never a runtime). Billing needs a verified signature.
            if not signature_verified:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook validation failed")
            call_obj = payload.get("call") or payload
            provider_call_id = call_obj.get("callId") or call_obj.get("id")
            if not provider_call_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook call identifier missing")
            try:
                return settlement.settle_billed(
                    crm_call_id=call.id,
                    provider=provider,
                    provider_call_id=str(provider_call_id),
                    billed_minutes=_billed_minutes(payload, call_obj),
                    provider_status=str(call_obj.get("status") or call_obj.get("state") or "call.billed"),
                    provider_agent_id=str(call_obj["agentId"]) if call_obj.get("agentId") else None,
                )
            except HistoricalSettlementOwnershipError:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook validation failed") from None

    try:
        result = service.handle_provider_event(provider, payload)
    except Exception as exc:
        logger.error("Error processing voice webhook: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing error",
        ) from exc

    if result.get("status") == "processed" and result.get("call_status") in _NOTIFIABLE_CALL_STATUSES:
        background_tasks.add_task(
            publish_call_event,
            tenant_id=call.tenant_id,
            voice_call_id=result["voice_call_id"],
        )

    return result
