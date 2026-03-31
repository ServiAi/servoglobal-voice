import httpx
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class WhatsAppService:
    """
    Servicio de notificaciones WhatsApp.

    Estrategia de envío:
    ┌─────────────────────────────────────────────────────────────┐
    │  MODO CHATWOOT (recomendado — visible en CRM)               │
    │  Python → Chatwoot API → WhatsApp                           │
    │  Requiere: CHATWOOT_API_TOKEN + CHATWOOT_INBOX_ID           │
    ├─────────────────────────────────────────────────────────────┤
    │  MODO DIRECTO (fallback — NO visible en CRM)                │
    │  Python → Meta Graph API → WhatsApp                         │
    │  Requiere: WHATSAPP_API_TOKEN + WHATSAPP_PHONE_NUMBER_ID    │
    └─────────────────────────────────────────────────────────────┘

    El modo Chatwoot se usa automáticamente si CHATWOOT_API_TOKEN está
    configurado. De lo contrario, cae al modo directo.
    """

    def __init__(self):
        # Meta Cloud API (directo)
        self.api_token       = settings.WHATSAPP_API_TOKEN
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.meta_base_url   = f"https://graph.facebook.com/v23.0/{self.phone_number_id}/messages"

        # Chatwoot (preferido)
        self.chatwoot_token  = getattr(settings, "CHATWOOT_API_TOKEN", "")

    @property
    def use_chatwoot(self) -> bool:
        """True si Chatwoot está configurado como canal de salida."""
        return bool(self.chatwoot_token)

    # ══════════════════════════════════════════════════════════════════════════
    # API PÚBLICA
    # ══════════════════════════════════════════════════════════════════════════

    async def send_notification(
        self,
        to: str,
        message: str,
        name: str = "",
        email: str = "",
        labels: list[str] | None = None,
    ) -> bool:
        """
        Envía un mensaje de texto libre a un contacto de WhatsApp.

        Si Chatwoot está configurado → envía por Chatwoot (visible en CRM).
        Si no → fallback a Meta Cloud API directamente.

        Args:
            to:      Teléfono en formato +573201234567
            message: Texto del mensaje
            name:    Nombre del contacto (para el CRM)
            email:   Email opcional
            labels:  Etiquetas Chatwoot (ej. ['cita-confirmada'])
        """
        if self.use_chatwoot:
            logger.info(f"[WhatsApp] Enviando via Chatwoot a {to}")
            return await self._send_via_chatwoot(to, message, name, email, labels)
        else:
            logger.warning("[WhatsApp] CHATWOOT_API_TOKEN no configurado — usando Meta directo (no visible en CRM)")
            return await self._send_text_direct(to, message)

    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "es",
        components: list | None = None,
        name: str = "",
    ) -> dict | None:
        """
        Envía una plantilla pre-aprobada de WhatsApp.

        Las plantillas SIEMPRE van directo a Meta Cloud API porque Chatwoot
        no soporta templates personalizados via API en todas las versiones.
        Se registra una nota interna en el CRM si Chatwoot está disponible.

        Args:
            to:            Teléfono destino
            template_name: Nombre de la plantilla en Meta
            language_code: Código de idioma (ej. 'es', 'es_CO', 'en')
            components:    Variables de la plantilla (headers, body, buttons)
            name:          Nombre del contacto (para nota en CRM)
        """
        result = await self._send_template_direct(to, template_name, language_code, components)

        # Registrar nota interna en Chatwoot si está disponible
        if result and self.use_chatwoot:
            await self._register_template_in_crm(to, template_name, name)

        return result

    # ══════════════════════════════════════════════════════════════════════════
    # IMPLEMENTACIONES INTERNAS
    # ══════════════════════════════════════════════════════════════════════════

    async def _send_via_chatwoot(
        self,
        phone: str,
        message: str,
        name: str = "",
        email: str = "",
        labels: list[str] | None = None,
    ) -> bool:
        """Envía un mensaje a través de Chatwoot (visible en CRM)."""
        from app.services.chatwoot_service import chatwoot_service
        return await chatwoot_service.send_notification(
            phone=phone,
            message=message,
            name=name,
            email=email,
            labels=labels or ["notificacion"],
        )

    async def _send_text_direct(self, to: str, message: str) -> bool:
        """Envía texto plano directo a Meta Cloud API. NO visible en Chatwoot."""
        if not self.api_token or not self.phone_number_id:
            logger.error("Faltan WHATSAPP_API_TOKEN o WHATSAPP_PHONE_NUMBER_ID")
            return False

        to_clean = to.replace("+", "").replace(" ", "").strip()

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    self.meta_base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "messaging_product": "whatsapp",
                        "to": to_clean,
                        "type": "text",
                        "text": {"body": message},
                    },
                )
                resp.raise_for_status()
                logger.info(f"[Meta directo] Mensaje enviado a {to}")
                return True
            except httpx.HTTPStatusError as e:
                logger.error(f"[Meta directo] Error HTTP: {e.response.text}")
                return False
            except Exception as e:
                logger.error(f"[Meta directo] Error inesperado: {e}")
                return False

    async def _send_template_direct(
        self,
        to: str,
        template_name: str,
        language_code: str,
        components: list | None,
    ) -> dict | None:
        """Envía una plantilla directamente a Meta Cloud API."""
        if not self.api_token or not self.phone_number_id:
            logger.error("Faltan WHATSAPP_API_TOKEN o WHATSAPP_PHONE_NUMBER_ID")
            return None

        to_clean = to.replace("+", "").replace(" ", "").strip()

        payload: dict = {
            "messaging_product": "whatsapp",
            "to": to_clean,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        if components:
            payload["template"]["components"] = components

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    self.meta_base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                logger.info(f"[Template] '{template_name}' enviado a {to}")
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"[Template] Error HTTP: {e.response.text}")
                return None
            except Exception as e:
                logger.error(f"[Template] Error inesperado: {e}")
                return None

    async def _register_template_in_crm(
        self,
        phone: str,
        template_name: str,
        name: str = "",
    ) -> None:
        """
        Deja una nota interna en Chatwoot indicando que se envió una plantilla.
        Se registra como mensaje privado (solo visible para agentes, no el cliente).
        """
        try:
            from app.services.chatwoot_service import chatwoot_service

            contact_id = await chatwoot_service.get_or_create_contact(phone, name)
            if not contact_id:
                return

            conv_id = await chatwoot_service.get_or_create_conversation(contact_id)
            if not conv_id:
                return

            await chatwoot_service.send_message(
                conv_id,
                f"📤 *Plantilla enviada:* `{template_name}`",
                private=True,  # nota interna — solo agentes la ven
            )
        except Exception as e:
            logger.warning(f"No se pudo registrar template en CRM: {e}")


# Singleton
whatsapp_service = WhatsAppService()
