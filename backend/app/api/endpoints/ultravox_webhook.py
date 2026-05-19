from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.ultravox_ingestion_service import UltravoxIngestionService


router = APIRouter(prefix="/api/v1/integrations/ultravox", tags=["Ultravox Ingestion"])


def _parse_ultravox_timestamp(timestamp: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook timestamp",
        ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _verify_ultravox_signature(request: Request, raw_body: bytes) -> None:
    secret = settings.ULTRAVOX_WEBHOOK_SECRET
    if not secret:
        if settings.ULTRAVOX_ALLOW_UNSIGNED_WEBHOOKS:
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ultravox webhook secret is not configured",
        )

    timestamp = request.headers.get("x-ultravox-webhook-timestamp")
    if not timestamp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Ultravox webhook timestamp header",
        )

    signature_header = request.headers.get("x-ultravox-webhook-signature")
    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Ultravox webhook signature header",
        )

    request_time = _parse_ultravox_timestamp(timestamp)
    age_seconds = abs((datetime.now(UTC) - request_time).total_seconds())
    if age_seconds > settings.ULTRAVOX_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expired Ultravox webhook timestamp",
        )

    expected_signature = hmac.new(
        secret.encode(),
        raw_body + timestamp.encode(),
        hashlib.sha256,
    ).hexdigest()
    signatures = [signature.strip() for signature in signature_header.split(",")]
    if not any(hmac.compare_digest(signature, expected_signature) for signature in signatures):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Ultravox webhook signature",
        )


@router.post("/events")
async def ingest_ultravox_event(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    raw_body = await request.body()
    _verify_ultravox_signature(request, raw_body)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ultravox webhook payload must be valid JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ultravox webhook payload must be an object",
        )

    result = UltravoxIngestionService(db).ingest_event(payload)
    return {
        "call_id": result.call.id,
        "event_id": result.event.id if result.event else None,
        "external_call_id": result.call.external_call_id,
        "normalized_status": result.call.normalized_status,
    }
