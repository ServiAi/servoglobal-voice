from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.ultravox_ingestion_service import UltravoxIngestionService


router = APIRouter(prefix="/api/v1/integrations/ultravox", tags=["Ultravox Ingestion"])


@router.post("/events")
async def ingest_ultravox_event(
    request: Request,
    x_serviai_webhook_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    if settings.ULTRAVOX_WEBHOOK_SECRET and (
        x_serviai_webhook_secret != settings.ULTRAVOX_WEBHOOK_SECRET
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )

    payload = await request.json()
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
