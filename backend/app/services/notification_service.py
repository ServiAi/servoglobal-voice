"""
notification_service.py
=======================
Servicio centralizado de notificaciones WhatsApp para Serviglobal IA.

Flujo para TODAS las plantillas:
  1. Enviar plantilla directo a Meta Cloud API (templates requieren Meta directo)
  2. Registrar nota interna en Chatwoot CRM (visible solo para agentes)

Plantillas configuradas en Meta:
  • alerta_lead_owner      → avisa a los dueños del negocio sobre un nuevo lead/cita
  • cita_confirmada_cliente → confirma la cita al cliente en su número de WhatsApp

Variables de ambas plantillas: {{1}} name  {{2}} date_str  {{3}} time_str
"""

import asyncio
import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Números de los dueños/equipo — reciben alerta_lead_owner ─────────────────
OWNER_PHONES: list[str] = [
    "+573106666709",
    "+573014023104",
    "+573178193641",
]

# ── Configuración de plantillas ───────────────────────────────────────────────
TEMPLATES = {
    "alerta_lead_owner": {
        "language": "es-CO",
        "description": "Alerta interna al equipo: nuevo lead o cita agendada",
    },
    "cita_confirmada_cliente": {
        "language": "es-CO",
        "description": "Confirmación de cita enviada al cliente",
    },
}


class NotificationService:
    """
    Servicio de notificaciones de Serviglobal IA.

    Uso típico (desde bookings o el agente de voz):

        from app.services.notification_service import notification_service

        await notification_service.notify_new_booking(
            client_phone="+573201234567",
            client_name="Juan García",
            date_str="Miércoles 2 de abril de 2026",
            time_str="10:00 AM",
        )
    """

    def __init__(self):
        self.api_token       = settings.WHATSAPP_API_TOKEN
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.meta_url        = f"https://graph.facebook.com/v23.0/{self.phone_number_id}/messages"

    # ══════════════════════════════════════════════════════════════════════════
    # API PÚBLICA
    # ══════════════════════════════════════════════════════════════════════════

    async def notify_new_booking(
        self,
        client_phone: str,
        client_name: str,
        date_str: str,
        time_str: str,
        client_email: str = "",
    ) -> dict:
        """
        Dispara ambas notificaciones cuando se agenda una cita:

          1. alerta_lead_owner  → a los 3 números del equipo (+57310..., +57301..., +57317...)
          2. cita_confirmada_cliente → al número del cliente

        Además registra nota interna en Chatwoot para cada envío.

        Args:
            client_phone:  Teléfono del cliente en formato +573201234567
            client_name:   Nombre del cliente
            date_str:      Fecha legible  (ej. "Miércoles 2 de abril de 2026")
            time_str:      Hora legible   (ej. "10:00 AM")
            client_email:  Email del cliente (opcional, para el CRM)

        Returns:
            dict con resultados de cada envío
        """
        results: dict = {
            "alerta_owners": [],
            "confirmacion_cliente": None,
        }

        # ── 1. Alertas a los dueños (en paralelo) ────────────────────────────
        owner_tasks = [
            self._send_alerta_lead_owner(phone, client_name, date_str, time_str)
            for phone in OWNER_PHONES
        ]
        owner_results = await asyncio.gather(*owner_tasks, return_exceptions=True)

        for phone, result in zip(OWNER_PHONES, owner_results):
            if isinstance(result, Exception):
                logger.error(f"Error enviando alerta_lead_owner a {phone}: {result}")
                results["alerta_owners"].append({"phone": phone, "ok": False})
            else:
                results["alerta_owners"].append({"phone": phone, "ok": result})

        # ── 2. Confirmación al cliente ────────────────────────────────────────
        ok = await self._send_cita_confirmada_cliente(
            client_phone, client_name, date_str, time_str, client_email
        )
        results["confirmacion_cliente"] = {"phone": client_phone, "ok": ok}

        logger.info(f"notify_new_booking completado: {results}")
        return results

    # ── Envío individual: alerta_lead_owner ───────────────────────────────────

    async def _send_alerta_lead_owner(
        self, to: str, name: str, date_str: str, time_str: str
    ) -> bool:
        """
        Envía la plantilla alerta_lead_owner a un número del equipo.
        Variables: {{1}} name  {{2}} date_str  {{3}} time_str
        """
        components = self._build_body_components(name, date_str, time_str)
        result = await self._send_template(to, "alerta_lead_owner", "es", components)

        if result:
            await self._register_in_crm(
                phone=to,
                template_name="alerta_lead_owner",
                note=(
                    f"📢 *Alerta de nuevo lead enviada al equipo*\n"
                    f"• Cliente: *{name}*\n"
                    f"• Fecha: *{date_str}*\n"
                    f"• Hora: *{time_str}*\n"
                    f"• Plantilla: `alerta_lead_owner`"
                ),
                contact_name=f"Equipo Serviglobal ({to})",
            )

        return bool(result)

    # ── Envío individual: cita_confirmada_cliente ─────────────────────────────

    async def _send_cita_confirmada_cliente(
        self, to: str, name: str, date_str: str, time_str: str, email: str = ""
    ) -> bool:
        """
        Envía la plantilla cita_confirmada_cliente al número del cliente.
        Variables: {{1}} name  {{2}} date_str  {{3}} time_str
        """
        components = self._build_body_components(name, date_str, time_str)
        result = await self._send_template(to, "cita_confirmada_cliente", "es", components)

        if result:
            await self._register_in_crm(
                phone=to,
                template_name="cita_confirmada_cliente",
                note=(
                    f"✅ *Confirmación de cita enviada al cliente*\n"
                    f"• Nombre: *{name}*\n"
                    f"• Fecha: *{date_str}*\n"
                    f"• Hora: *{time_str}*\n"
                    f"• Plantilla: `cita_confirmada_cliente`"
                ),
                contact_name=name,
                contact_email=email,
                labels=["cita-confirmada"],
            )

        return bool(result)

    # ══════════════════════════════════════════════════════════════════════════
    # ENVÍO DE PLANTILLAS (Meta Cloud API)
    # ══════════════════════════════════════════════════════════════════════════

    def _build_body_components(self, name: str, date_str: str, time_str: str) -> list:
        """
        Construye los componentes del body para plantillas con 3 variables.
        Mapeo: {{1}} → name   {{2}} → date_str   {{3}} → time_str
        """
        return [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": name},
                    {"type": "text", "text": date_str},
                    {"type": "text", "text": time_str},
                ],
            }
        ]

    async def _send_template(
        self,
        to: str,
        template_name: str,
        language_code: str,
        components: list,
    ) -> dict | None:
        """
        Envía una plantilla aprobada de WhatsApp directamente a Meta Cloud API.
        Retorna el JSON de respuesta de Meta o None si falla.
        """
        if not self.api_token or not self.phone_number_id:
            logger.error(
                f"[Template:{template_name}] Faltan WHATSAPP_API_TOKEN o WHATSAPP_PHONE_NUMBER_ID"
            )
            return None

        to_clean = to.replace("+", "").replace(" ", "").strip()

        payload = {
            "messaging_product": "whatsapp",
            "to": to_clean,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            },
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    self.meta_url,
                    headers={
                        "Authorization": f"Bearer {self.api_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                logger.info(f"[Template:{template_name}] Enviado a {to}")
                return resp.json()

            except httpx.HTTPStatusError as e:
                logger.error(
                    f"[Template:{template_name}] Error HTTP a {to}: "
                    f"{e.response.status_code} — {e.response.text}"
                )
                return None
            except Exception as e:
                logger.error(f"[Template:{template_name}] Error inesperado a {to}: {e}")
                return None

    # ══════════════════════════════════════════════════════════════════════════
    # REGISTRO EN CHATWOOT CRM
    # ══════════════════════════════════════════════════════════════════════════

    async def _register_in_crm(
        self,
        phone: str,
        template_name: str,
        note: str,
        contact_name: str = "",
        contact_email: str = "",
        labels: list[str] | None = None,
    ) -> None:
        """
        Registra una nota interna en Chatwoot después de enviar una plantilla.
        La nota es privada (solo visible para agentes, NO para el cliente).
        Si el contacto no existe en Chatwoot, lo crea automáticamente.
        """
        try:
            from app.services.chatwoot_service import chatwoot_service

            if not chatwoot_service.api_token:
                logger.warning(
                    f"[CRM] CHATWOOT_API_TOKEN no configurado — "
                    f"plantilla '{template_name}' no registrada en CRM"
                )
                return

            # Obtener o crear el contacto
            contact_id = await chatwoot_service.get_or_create_contact(
                phone, contact_name, contact_email
            )
            if not contact_id:
                logger.warning(f"[CRM] No se pudo obtener contacto para {phone}")
                return

            # Obtener o crear la conversación
            conv_id = await chatwoot_service.get_or_create_conversation(contact_id)
            if not conv_id:
                logger.warning(f"[CRM] No se pudo obtener conversacion para contact_id={contact_id}")
                return

            # Nota interna (private=True → solo agentes la ven)
            await chatwoot_service.send_message(conv_id, note, private=True)

            # Etiquetas opcionales
            if labels:
                await chatwoot_service.add_label(conv_id, labels)

            logger.info(
                f"[CRM] Nota registrada en conv={conv_id} para {phone} "
                f"(template: {template_name})"
            )

        except Exception as e:
            logger.warning(
                f"[CRM] Error registrando nota para template '{template_name}' "
                f"en {phone}: {e}"
            )


# Singleton — importar desde cualquier parte del proyecto
notification_service = NotificationService()
