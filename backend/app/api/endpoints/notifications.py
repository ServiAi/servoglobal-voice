from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


# ── Verificación del webhook Meta (handshake) ─────────────────────────────────

@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    Verificación inicial requerida por Meta/WhatsApp Cloud API.
    Meta hace un GET con hub.challenge y esperamos devolverlo.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook Meta verificado correctamente.")
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Token de verificación inválido")


@router.post("/webhook")
async def receive_webhook(request: Request):
    """
    Recibe eventos de estado de Meta (delivery, read, etc.).
    Los mensajes entrantes ahora son procesados por Chatwoot → /api/v1/chatwoot/webhook.
    """
    payload = await request.json()
    logger.debug(f"Evento Meta recibido: {payload}")
    return {"status": "ok"}


# ── Endpoint de notificaciones de reserva ────────────────────────────────────

class BookingNotificationRequest(BaseModel):
    """
    Payload para disparar ambas notificaciones de cita:
      - alerta_lead_owner    → equipo Serviglobal (3 números fijos)
      - cita_confirmada_cliente → número del cliente

    Ejemplo:
    {
        "client_phone": "+573201234567",
        "client_name": "Juan García",
        "date_str": "Miércoles 2 de abril de 2026",
        "time_str": "10:00 AM",
        "client_email": "juan@empresa.com"    (opcional)
    }
    """
    client_phone: str
    client_name: str
    date_str: str
    time_str: str
    client_email: str = ""


@router.post("/booking")
async def send_booking_notifications(request: BookingNotificationRequest):
    """
    Dispara las dos plantillas de notificación de cita:

    1. **alerta_lead_owner** → enviada a los 3 números del equipo Serviglobal:
       +573106666709, +573014023104, +573178193641

    2. **cita_confirmada_cliente** → enviada al número del cliente

    Ambas se registran como notas internas en Chatwoot CRM (visibles solo para agentes).

    Usar cuando:
    - El agente de voz agendó una cita
    - El frontend creó una reserva en Cal.com
    - Cualquier flujo que confirme una cita

    Returns:
        {
            "alerta_owners": [{"phone": "+57...", "ok": true}, ...],
            "confirmacion_cliente": {"phone": "+57...", "ok": true}
        }
    """
    from app.services.notification_service import notification_service

    try:
        results = await notification_service.notify_new_booking(
            client_phone=request.client_phone,
            client_name=request.client_name,
            date_str=request.date_str,
            time_str=request.time_str,
            client_email=request.client_email,
        )
        return {"status": "ok", "results": results}

    except Exception as e:
        logger.error(f"Error en send_booking_notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))
