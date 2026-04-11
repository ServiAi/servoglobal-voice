"""
services/meta_client.py
========================
Cliente HTTP de bajo nivel para Meta WhatsApp Cloud API.

RESPONSABILIDAD ÚNICA: Hacer llamadas HTTP a Meta y devolver el resultado.
No sabe nada de Chatwoot, ni de lógica de negocio, ni de contactos.

Usa este cliente:
  - notification_service.py  (para enviar templates)
  - Cualquier otro servicio que necesite hablar con Meta directamente
"""

import httpx
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class MetaClient:
    """Cliente HTTP para Meta WhatsApp Cloud API (Graph API v23.0)."""

    def __init__(self):
        self._token          = settings.WHATSAPP_API_TOKEN
        self._phone_id       = settings.WHATSAPP_PHONE_NUMBER_ID
        self._base_url       = f"https://graph.facebook.com/v23.0/{self._phone_id}/messages"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _clean_phone(self, phone: str) -> str:
        """Elimina '+' y espacios que Meta no acepta."""
        return phone.replace("+", "").replace(" ", "").strip()

    def _ready(self) -> bool:
        """Verifica que las credenciales están configuradas."""
        if not self._token or not self._phone_id:
            logger.error("[Meta] Faltan WHATSAPP_API_TOKEN o WHATSAPP_PHONE_NUMBER_ID en .env")
            return False
        return True

    # ── Texto libre ──────────────────────────────────────────────────────────

    async def send_text(self, to: str, body: str) -> bool:
        """
        Envía un mensaje de texto libre a un número de WhatsApp.

        Úsalo solo cuando NO hay una conversación activa en Chatwoot
        (en ese caso prefiere chatwoot_service.send_message para registrar en CRM).

        Args:
            to:   Teléfono en formato +573201234567
            body: Texto del mensaje

        Returns:
            True si Meta aceptó el mensaje, False si hubo error.
        """
        if not self._ready():
            return False

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    self._base_url,
                    headers=self._headers(),
                    json={
                        "messaging_product": "whatsapp",
                        "to": self._clean_phone(to),
                        "type": "text",
                        "text": {"body": body},
                    },
                )
                resp.raise_for_status()
                logger.info(f"[Meta] Texto enviado a {to}")
                return True
            except httpx.HTTPStatusError as e:
                logger.error(f"[Meta] Error HTTP send_text a {to}: {e.response.status_code} — {e.response.text}")
                return False
            except Exception as e:
                logger.error(f"[Meta] Error inesperado send_text a {to}: {e}")
                return False

    # ── Plantillas ───────────────────────────────────────────────────────────

    async def send_template(
        self,
        to: str,
        template_name: str,
        language_code: str = "es",
        components: list | None = None,
    ) -> dict | None:
        """
        Envía una plantilla aprobada de WhatsApp Business.

        Las plantillas son obligatorias para iniciar conversaciones
        o cuando han pasado más de 24h desde el último mensaje del cliente.

        Args:
            to:            Teléfono en formato +573201234567
            template_name: Nombre exacto de la plantilla en Meta Business Manager
            language_code: Código de idioma ('es', 'es_CO', 'en', etc.)
            components:    Variables de la plantilla.
                           Formato para body con 3 variables:
                           [{"type": "body", "parameters": [
                               {"type": "text", "text": "valor 1"},
                               {"type": "text", "text": "valor 2"},
                               {"type": "text", "text": "valor 3"},
                           ]}]

        Returns:
            JSON de respuesta de Meta (contiene message_id) o None si falla.
        """
        if not self._ready():
            return None

        template_payload: dict = {
            "name": template_name,
            "language": {"code": language_code},
        }
        if components:
            template_payload["components"] = components

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    self._base_url,
                    headers=self._headers(),
                    json={
                        "messaging_product": "whatsapp",
                        "to": self._clean_phone(to),
                        "type": "template",
                        "template": template_payload,
                    },
                )
                resp.raise_for_status()
                logger.info(f"[Meta] Template '{template_name}' enviado a {to}")
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"[Meta] Error HTTP send_template '{template_name}' a {to}: "
                    f"{e.response.status_code} — {e.response.text}"
                )
                return None
            except Exception as e:
                logger.error(f"[Meta] Error inesperado send_template '{template_name}' a {to}: {e}")
                return None


# Singleton
meta_client = MetaClient()
