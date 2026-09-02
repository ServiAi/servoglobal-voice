import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.identity_service import IdentityService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Legacy Meta verification endpoint kept for backward compatibility."""
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Legacy Meta webhook verified")
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Invalid verification token")


@router.post("/webhook")
async def receive_webhook():
    """Legacy Meta webhook; canonical processing lives at /api/v1/webhook/whatsapp."""
    logger.info("Legacy Meta webhook ignored; use /api/v1/webhook/whatsapp")
    return {"status": "ignored", "canonical_webhook": "/api/v1/webhook/whatsapp"}


class BookingNotificationRequest(BaseModel):
    """
    Payload para disparar ambas notificaciones de cita:
      - alerta_lead_owner -> equipo Serviglobal (3 numeros fijos)
      - cita_confirmada_cliente -> numero del cliente
    """

    client_phone: str
    client_name: str
    date_str: str
    time_str: str
    client_email: str = ""


@router.post("/booking")
async def send_booking_notifications(request: BookingNotificationRequest, db: Session = Depends(get_db)):
    """
    Dispara las dos plantillas de notificacion de cita.
    """
    from app.services.notification_service import notification_service

    tenant = IdentityService(db).bootstrap_tenant()

    try:
        results = await notification_service.notify_new_booking(
            db=db,
            tenant_id=tenant.id,
            client_phone=request.client_phone,
            client_name=request.client_name,
            date_str=request.date_str,
            time_str=request.time_str,
            client_email=request.client_email,
        )
        return {"status": "ok", "results": results}

    except Exception as e:
        logger.error("Error en send_booking_notifications: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
