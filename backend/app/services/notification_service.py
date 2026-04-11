"""
services/notification_service.py
=================================
Servicio de lógica de negocio para notificaciones de Serviglobal IA.

RESPONSABILIDAD ÚNICA: Orquestar "qué enviar, a quién y cuándo".
  ✅ Usa meta_client     → para enviar templates a Meta Cloud API
  ✅ Usa chatwoot_service → para guardar notas internas en el CRM

NO hace llamadas HTTP directamente (eso lo hacen los clientes de capa 1).

──────────────────────────────────────────────────────
PLANTILLAS CONFIGURADAS EN META BUSINESS MANAGER
──────────────────────────────────────────────────────
 • alerta_lead_owner
     Destino : los 3 números del equipo Serviglobal (OWNER_PHONES)
     Propósito: avisa al equipo cuando se agenda una cita nueva
     Variables: {{1}} nombre_cliente  {{2}} fecha  {{3}} hora

 • cita_confirmada_cliente
     Destino : el número del cliente (dinámico)
     Propósito: confirmation de su cita agendada
     Variables: {{1}} nombre_cliente  {{2}} fecha  {{3}} hora

──────────────────────────────────────────────────────
CÓMO USAR ESTE SERVICIO
──────────────────────────────────────────────────────
  from app.services.notification_service import notification_service

  # Cuando Cal.com confirma una cita
  await notification_service.notify_new_booking(
      client_phone="+573201234567",
      client_name="Juan García",
      date_str="Miércoles 2 de abril de 2026",
      time_str="10:00 AM",
      client_email="juan@empresa.com",  # opcional
  )
──────────────────────────────────────────────────────
"""

import asyncio
import logging
from app.services.meta_client import meta_client
from app.services.chatwoot_service import chatwoot_service

logger = logging.getLogger(__name__)

# ── Números del equipo que reciben la alerta de nuevo lead ───────────────────
OWNER_PHONES: list[str] = [
    "+573106666709",
    "+573014023104",
    "+573178193641",
]


class NotificationService:
    """Orquestador de notificaciones de negocio para Serviglobal IA."""

    # ══════════════════════════════════════════════════════════════════════════
    # API PÚBLICA — métodos que llamas desde endpoints o desde el agente
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
        Envía las dos notificaciones de cita y registra notas en el CRM.

        Dispara en paralelo:
          1. alerta_lead_owner → a cada número de OWNER_PHONES
          2. cita_confirmada_cliente → al número del cliente

        Cada envío exitoso registra una nota interna en Chatwoot CRM.

        Returns:
            {
                "alerta_owners": [{"phone": "+57...", "ok": True}, ...],
                "confirmacion_cliente": {"phone": "+57...", "ok": True}
            }
        """
        # 1. Alertas al equipo (en paralelo para reducir latencia)
        owner_tasks = [
            self._notify_owner(phone, client_name, date_str, time_str)
            for phone in OWNER_PHONES
        ]
        owner_results = await asyncio.gather(*owner_tasks, return_exceptions=True)

        alerta_owners = []
        for phone, result in zip(OWNER_PHONES, owner_results):
            if isinstance(result, Exception):
                logger.error(f"[Notif] Error en alerta_lead_owner a {phone}: {result}")
                alerta_owners.append({"phone": phone, "ok": False})
            else:
                alerta_owners.append({"phone": phone, "ok": result})

        # 2. Confirmación al cliente
        ok_cliente = await self._notify_client(
            client_phone, client_name, date_str, time_str, client_email
        )

        results = {
            "alerta_owners": alerta_owners,
            "confirmacion_cliente": {"phone": client_phone, "ok": ok_cliente},
        }
        logger.info(f"[Notif] notify_new_booking completado → {results}")
        return results

    async def notify_demo_start(self, context: dict) -> None:
        """
        Registra el inicio de una llamada de demostración (Web o SIP) en el CRM 
        junto con el contexto del negocio capturado en el formulario frontend.
        """
        phone = context.get("user_phone")
        if not phone:
            logger.warning("[Notif] Demo start call without user_phone, skipping CRM logging.")
            return

        name = context.get("user_name", "Usuario Demo")
        email = context.get("user_email", "")

        industry = context.get("user_industry", "No especificada")
        use_case = context.get("user_use_case", "No especificado")
        volume = context.get("user_volume", "No especificado")
        pain_point = context.get("user_pain_point", "No especificado")

        note = (
            f"📞 *Demostración de Agente IA Iniciada*\n"
            f"• Industria: {industry}\n"
            f"• Caso de Uso: {use_case}\n"
            f"• Dolor / Reto: {pain_point}\n"
            f"• Volumen de Op: {volume}\n"
        )

        logger.info(f"[Notif] Registrando demo iniciada para {phone} en CRM.")
        import asyncio
        asyncio.create_task(
            self._crm_private_note(
                phone=phone,
                note=note,
                contact_name=name,
                contact_email=email,
                labels=["demo-iniciada"]
            )
        )

    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS PRIVADOS — un método por plantilla
    # ══════════════════════════════════════════════════════════════════════════

    async def _notify_owner(
        self, phone: str, client_name: str, date_str: str, time_str: str
    ) -> bool:
        """
        Envía alerta_lead_owner a un número del equipo.
        Variables: {{1}} client_name  {{2}} date_str  {{3}} time_str
        """
        ok = await meta_client.send_template(
            to=phone,
            template_name="alerta_lead_owner",
            language_code="es_CO",
            components=self._body_components(client_name, date_str, time_str),
        )
        if ok:
            await self._crm_private_note(
                phone=phone,
                contact_name=f"Equipo Serviglobal",
                note=(
                    f"📢 *Alerta de nuevo lead enviada*\n"
                    f"• Cliente: *{client_name}*\n"
                    f"• Fecha: *{date_str}*\n"
                    f"• Hora: *{time_str}*\n"
                    f"• Plantilla: `alerta_lead_owner`"
                ),
            )
        return bool(ok)

    async def _notify_client(
        self,
        phone: str,
        name: str,
        date_str: str,
        time_str: str,
        email: str = "",
    ) -> bool:
        """
        Envía cita_confirmada_cliente al número del cliente.
        Variables: {{1}} name  {{2}} date_str  {{3}} time_str
        """
        ok = await meta_client.send_template(
            to=phone,
            template_name="cita_confirmada_cliente",
            language_code="es_CO",
            components=self._body_components(name, date_str, time_str),
        )
        if ok:
            await self._crm_private_note(
                phone=phone,
                contact_name=name,
                contact_email=email,
                labels=["cita-confirmada"],
                note=(
                    f"✅ *Confirmación de cita enviada al cliente*\n"
                    f"• Nombre: *{name}*\n"
                    f"• Fecha: *{date_str}*\n"
                    f"• Hora: *{time_str}*\n"
                    f"• Plantilla: `cita_confirmada_cliente`"
                ),
            )
        return bool(ok)

    # ══════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _body_components(self, name: str, date_str: str, time_str: str) -> list:
        """
        Construye los componentes de body de Meta para plantillas con 3 variables.
          {{1}} → name     {{2}} → date_str     {{3}} → time_str
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

    async def _crm_private_note(
        self,
        phone: str,
        note: str,
        contact_name: str = "",
        contact_email: str = "",
        labels: list[str] | None = None,
    ) -> None:
        """
        Registra una nota privada en Chatwoot CRM (solo visible para agentes).
        Crea el contacto y la conversación si no existen.
        Nunca lanza excepción (falla silenciosamente con log de error).
        """
        try:
            if not chatwoot_service.api_token:
                logger.warning("[CRM] CHATWOOT_API_TOKEN no configurado — nota no registrada")
                return

            contact_id = await chatwoot_service.get_or_create_contact(
                phone, contact_name, contact_email
            )
            if not contact_id:
                return

            conv_id = await chatwoot_service.get_or_create_conversation(contact_id)
            if not conv_id:
                return

            await chatwoot_service.send_message(conv_id, note, private=True)

            if labels:
                await chatwoot_service.add_label(conv_id, labels)

        except Exception as e:
            logger.error(f"[CRM] Error registrando nota para {phone}: {e}")


# Singleton
notification_service = NotificationService()
