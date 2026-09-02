from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.integrations import TenantIntegrationEvent
from app.services.chatwoot_config_service import ChatwootConfigService
from app.services.integration_event_service import IntegrationEventService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks/chatwoot", tags=["Chatwoot Webhook"])


def _extract_account_id(payload: dict) -> int | None:
    """El objeto 'account' no siempre viene en el nivel superior: eventos como
    message_created/message_updated lo traen ahi, pero otros (p. ej.
    conversation_typing_on/off) solo lo anidan dentro de 'conversation'."""
    account = payload.get("account")
    if not isinstance(account, dict):
        account = (payload.get("conversation") or {}).get("account")
    return account.get("id") if isinstance(account, dict) else None


@router.post("/{webhook_key}")
async def chatwoot_webhook(webhook_key: str, request: Request, db: Session = Depends(get_db)):
    """
    Recibe eventos de Chatwoot para la Account de un tenant especifico.

    Chatwoot no firma sus webhooks salientes; el aislamiento por tenant se
    logra con la combinacion de:
      1. `webhook_key` opaco en la URL (unico por tenant, no adivinable).
      2. Cross-check de `payload.account.id` contra la Account configurada
         para ese tenant.

    Chatwoot puede reintentar la entrega del mismo evento (timeouts, errores
    transitorios de red); un `message_created` ya procesado se detecta por
    el id estable del mensaje y no se vuelve a registrar ni loguear.
    """
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Chatwoot webhook: payload no es JSON valido")
        return {"status": "ignored"}

    config_service = ChatwootConfigService(db)
    config = config_service.get_config_by_webhook_key(webhook_key)
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    payload_account_id = _extract_account_id(payload)
    if payload_account_id != config.account_id:
        message = (
            f"account_id mismatch: payload={payload_account_id!r} "
            f"expected={config.account_id} event={payload.get('event')!r}"
        )
        IntegrationEventService(db).record_event(
            tenant_id=config.tenant_id,
            provider="chatwoot",
            event_type="webhook_rejected",
            status="rejected",
            message=message,
        )
        logger.warning("Chatwoot webhook: %s tenant_id=%s", message, config.tenant_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account mismatch")

    event_type = payload.get("event")
    if event_type != "message_created":
        return {"status": "ignored", "reason": "not message_created"}

    if payload.get("message_type") != "incoming":
        return {"status": "ignored", "reason": "not incoming"}

    conversation = payload.get("conversation") or {}
    conversation_id = conversation.get("id")
    message_content = (payload.get("content") or "").strip()
    message_id = payload.get("id")

    if not conversation_id or not message_content:
        return {"status": "ignored", "reason": "missing conversation_id or content"}

    if message_id is not None:
        # Chatwoot puede reintentar la entrega del mismo webhook (timeouts,
        # errores transitorios); el id del mensaje es estable entre reintentos
        # y es lo que usamos para no procesar/loguear el mismo evento dos veces.
        duplicate = db.scalar(
            select(TenantIntegrationEvent.id).where(
                TenantIntegrationEvent.tenant_id == config.tenant_id,
                TenantIntegrationEvent.provider == "chatwoot",
                TenantIntegrationEvent.event_type == "webhook_received",
                TenantIntegrationEvent.resource_type == "message",
                TenantIntegrationEvent.resource_id == str(message_id),
            )
        )
        if duplicate is not None:
            return {"status": "ignored", "reason": "duplicate"}

    logger.info(
        "Chatwoot webhook mensaje entrante tenant_id=%s conversation_id=%s",
        config.tenant_id,
        conversation_id,
    )
    IntegrationEventService(db).record_event(
        tenant_id=config.tenant_id,
        provider="chatwoot",
        event_type="webhook_received",
        status="success",
        resource_type="message",
        resource_id=str(message_id) if message_id is not None else str(conversation_id),
        metadata={"conversation_id": conversation_id},
    )

    return {"status": "ok"}
