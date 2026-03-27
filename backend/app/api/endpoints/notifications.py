from fastapi import APIRouter, Request, HTTPException, Query
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])

@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge")
):
    """
    Endpoint para la verificación inicial requerida por Meta/WhatsApp.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verificado correctamente.")
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Token de verificación inválido")

@router.post("/webhook")
async def receive_webhook(request: Request):
    """
    Recibe los eventos desde WhatsApp Cloud API (estados de mensajes o mensajes entrantes).
    """
    payload = await request.json()
    logger.info(f"Webhook de WhatsApp recibido: {payload}")
    
    # Aquí se puede procesar eventos específicos a futuro
    
    return {"status": "ok"}
