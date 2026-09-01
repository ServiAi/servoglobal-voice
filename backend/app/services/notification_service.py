"""
services/notification_service.py
=================================
Servicio de lógica de negocio para notificaciones de Serviglobal IA.

RESPONSABILIDAD ÚNICA: Orquestar "qué enviar, a quién y cuándo".
  ✅ Usa meta_client        → para enviar templates a Meta Cloud API
  ✅ Usa ChatwootConfigService/ChatwootClient → para guardar notas internas
     en el CRM, con la Account de Chatwoot configurada para cada tenant

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
      db=db,
      tenant_id=tenant_id,
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

from sqlalchemy.orm import Session

from app.services.chatwoot_config_service import ChatwootConfigService
from app.services.chatwoot_client import ChatwootClient
from app.services.meta_client import meta_client

logger = logging.getLogger(__name__)

# ── Números del equipo que reciben la alerta de nuevo lead ───────────────────
OWNER_PHONES: list[str] = [
    "+573106666709",
]

# Bloqueados temporalmente: no reciben alerta_lead_owner mientras esta lista exista.
BLOCKED_OWNER_PHONES: list[str] = [
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
        db: Session,
        tenant_id: str,
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

        Cada envío exitoso registra una nota interna en Chatwoot CRM (por tenant).

        Returns:
            {
                "alerta_owners": [{"phone": "+57...", "ok": True}, ...],
                "confirmacion_cliente": {"phone": "+57...", "ok": True}
            }
        """
        # 1. Alertas al equipo (en paralelo para reducir latencia)
        owner_tasks = [
            self._notify_owner(db, tenant_id, phone, client_name, date_str, time_str)
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
            db, tenant_id, client_phone, client_name, date_str, time_str, client_email
        )

        results = {
            "alerta_owners": alerta_owners,
            "confirmacion_cliente": {"phone": client_phone, "ok": ok_cliente},
        }
        logger.info(f"[Notif] notify_new_booking completado → {results}")
        return results

    async def notify_demo_start(self, db: Session, tenant_id: str, context: dict) -> bool:
        """
        Registra el inicio de una llamada de demostración (Web o SIP) en el CRM
        junto con el contexto del negocio capturado en el formulario frontend.
        """
        def value(*keys: str) -> str:
            for key in keys:
                found = context.get(key)
                if found not in (None, ""):
                    return str(found)
            return ""

        phone = value("user_phone", "phone", "customer_phone", "lead_phone")
        if not phone:
            logger.warning("[Notif] Demo start call without phone, skipping CRM logging.")
            return False

        name = value("user_name", "name", "customer_name", "lead_name") or "Usuario Demo"
        email = value("user_email", "email", "customer_email", "lead_email")

        industry = value("user_industry", "industry") or "No especificada"
        use_case = value("user_use_case", "use_case", "useCase") or "No especificado"
        volume = value("user_volume", "volume") or "No especificado"
        pain_point = value("user_pain_point", "pain_point", "painPoint") or "No especificado"

        note = (
            f"📞 *Demostración de Agente IA Iniciada*\n"
            f"• Industria: {industry}\n"
            f"• Caso de Uso: {use_case}\n"
            f"• Dolor / Reto: {pain_point}\n"
            f"• Volumen de Op: {volume}\n"
        )

        logger.info("[Notif] Registrando demo iniciada en CRM tenant_id=%s", tenant_id)
        ok = await self._crm_private_note(
            db,
            tenant_id,
            phone=phone,
            note=note,
            contact_name=name,
            contact_email=email,
            labels=["demo-iniciada"],
        )
        if not ok:
            logger.warning("[Notif] Demo start note was not registered in Chatwoot tenant_id=%s", tenant_id)
        return ok

    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS PRIVADOS — un método por plantilla
    # ══════════════════════════════════════════════════════════════════════════

    async def _notify_owner(
        self, db: Session, tenant_id: str, phone: str, client_name: str, date_str: str, time_str: str
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
                db,
                tenant_id,
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
        db: Session,
        tenant_id: str,
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
                db,
                tenant_id,
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
        db: Session,
        tenant_id: str,
        phone: str,
        note: str,
        contact_name: str = "",
        contact_email: str = "",
        labels: list[str] | None = None,
    ) -> bool:
        """
        Registra una nota privada en Chatwoot CRM (solo visible para agentes),
        usando la Account de Chatwoot configurada para este tenant.
        Crea el contacto y la conversación si no existen.
        Nunca lanza excepción (falla silenciosamente con log de error).
        """
        try:
            try:
                _, client_config = ChatwootConfigService(db).get_active_client_config(tenant_id)
            except ValueError:
                logger.warning("[CRM] Chatwoot integration is not configured for tenant_id=%s", tenant_id)
                return False
            client = ChatwootClient(client_config)

            contact_id = await client.get_or_create_contact(phone, contact_name, contact_email)
            if not contact_id:
                logger.warning("[CRM] Chatwoot contact could not be resolved tenant_id=%s", tenant_id)
                return False

            conv_id = await client.get_or_create_conversation(contact_id)
            if not conv_id:
                logger.warning("[CRM] Chatwoot conversation could not be resolved contact_id=%s", contact_id)
                return False

            sent = await client.send_message(conv_id, note, private=True)
            if not sent:
                logger.warning("[CRM] Chatwoot private note was rejected for conversation_id=%s", conv_id)
                return False

            if labels:
                labeled = await client.add_label(conv_id, labels)
                if not labeled:
                    logger.warning("[CRM] Chatwoot labels were not applied for conversation_id=%s", conv_id)

            return True

        except Exception as e:
            logger.error("[CRM] Error registrando nota tenant_id=%s: %s", tenant_id, e)
            return False


# Singleton
notification_service = NotificationService()


async def run_demo_start_notification_task(tenant_id: str, context: dict) -> None:
    """
    Wrapper para invocar notify_demo_start desde BackgroundTasks.

    Abre y cierra su propia sesion de DB (la sesion de la request ya puede
    estar cerrada quando corre este background task), siguiendo el mismo
    patron que run_booking_notification_pipeline_task.
    """
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        await notification_service.notify_demo_start(db, tenant_id, context)
    except Exception as exc:  # noqa: BLE001 - background task must never raise
        logger.error(
            "[Notif] demo_start_task_error tenant_id=%s error_type=%s", tenant_id, type(exc).__name__
        )
    finally:
        db.close()
