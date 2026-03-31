import httpx
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

CHATWOOT_BASE_URL = "https://crm.serviglobal-ia.com"


class ChatwootService:
    """
    Servicio para interactuar con la API de Chatwoot.

    Flujo para notificaciones salientes (visible en CRM):
        1. get_or_create_contact(phone, name)  → contact_id
        2. get_or_create_conversation(contact_id, inbox_id) → conversation_id
        3. send_message(conversation_id, texto)  → Chatwoot → WhatsApp

    Flujo para responder a mensajes entrantes:
        1. Chatwoot webhook llega a /api/v1/chatwoot/webhook
        2. send_message(conversation_id, respuesta_ia)
    """

    def __init__(self):
        self.api_token   = getattr(settings, "CHATWOOT_API_TOKEN", "")
        self.account_id  = getattr(settings, "CHATWOOT_ACCOUNT_ID", 1)
        self.inbox_id    = getattr(settings, "CHATWOOT_INBOX_ID", 1)   # ID del inbox de WhatsApp
        self.base_url    = CHATWOOT_BASE_URL

    def _headers(self) -> dict:
        return {
            "api_access_token": self.api_token,
            "Content-Type": "application/json",
        }

    def _api(self, path: str) -> str:
        return f"{self.base_url}/api/v1/accounts/{self.account_id}/{path}"

    # ══════════════════════════════════════════════════════════════════════════
    # CONTACTOS
    # ══════════════════════════════════════════════════════════════════════════

    async def search_contact(self, phone: str) -> dict | None:
        """
        Busca un contacto por número de teléfono.
        Retorna el primer resultado o None si no existe.
        """
        phone_clean = phone.strip().replace(" ", "")
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    self._api("contacts/search"),
                    headers=self._headers(),
                    params={"q": phone_clean, "include_contacts": True},
                )
                resp.raise_for_status()
                data = resp.json()
                contacts = data.get("payload", [])
                if contacts:
                    logger.info(f"Contacto encontrado para {phone_clean}: id={contacts[0]['id']}")
                    return contacts[0]
                return None
            except Exception as e:
                logger.error(f"Error buscando contacto {phone}: {e}")
                return None

    async def create_contact(self, phone: str, name: str = "", email: str = "") -> dict | None:
        """
        Crea un contacto nuevo en Chatwoot.
        """
        phone_clean = phone.strip().replace(" ", "")
        payload: dict = {"phone_number": phone_clean}
        if name:
            payload["name"] = name
        if email:
            payload["email"] = email

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    self._api("contacts"),
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                contact = resp.json()
                logger.info(f"Contacto creado: id={contact.get('id')} phone={phone_clean}")
                return contact
            except httpx.HTTPStatusError as e:
                logger.error(f"Error HTTP creando contacto {phone}: {e.response.text}")
                return None
            except Exception as e:
                logger.error(f"Error creando contacto {phone}: {e}")
                return None

    async def get_or_create_contact(self, phone: str, name: str = "", email: str = "") -> int | None:
        """
        Busca el contacto por teléfono; si no existe, lo crea.
        Retorna el contact_id o None si falla.
        """
        contact = await self.search_contact(phone)
        if contact:
            return contact["id"]
        contact = await self.create_contact(phone, name, email)
        return contact["id"] if contact else None

    # ══════════════════════════════════════════════════════════════════════════
    # CONVERSACIONES
    # ══════════════════════════════════════════════════════════════════════════

    async def get_open_conversation(self, contact_id: int) -> int | None:
        """
        Busca si el contacto ya tiene una conversación abierta.
        Si existe, la reutiliza para no crear conversaciones duplicadas.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    self._api(f"contacts/{contact_id}/conversations"),
                    headers=self._headers(),
                )
                resp.raise_for_status()
                convs = resp.json().get("payload", [])
                # Preferir conversación abierta o pendiente
                for conv in convs:
                    if conv.get("status") in ("open", "pending"):
                        logger.info(f"Conversacion abierta reutilizada: id={conv['id']}")
                        return conv["id"]
                return None
            except Exception as e:
                logger.error(f"Error buscando conversaciones del contacto {contact_id}: {e}")
                return None

    async def create_conversation(
        self,
        contact_id: int,
        inbox_id: int | None = None,
        initial_message: str = "",
    ) -> int | None:
        """
        Crea una nueva conversación en Chatwoot para el contacto.
        Opcionalmente envía un primer mensaje.
        """
        payload: dict = {
            "contact_id": contact_id,
            "inbox_id": inbox_id or self.inbox_id,
        }
        if initial_message:
            payload["additional_attributes"] = {}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    self._api("conversations"),
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                conv = resp.json()
                conv_id = conv.get("id")
                logger.info(f"Conversacion creada: id={conv_id} contact_id={contact_id}")
                return conv_id
            except httpx.HTTPStatusError as e:
                logger.error(f"Error HTTP creando conversacion: {e.response.text}")
                return None
            except Exception as e:
                logger.error(f"Error creando conversacion: {e}")
                return None

    async def get_or_create_conversation(
        self,
        contact_id: int,
        inbox_id: int | None = None,
    ) -> int | None:
        """
        Reutiliza conversación abierta o crea una nueva.
        """
        conv_id = await self.get_open_conversation(contact_id)
        if conv_id:
            return conv_id
        return await self.create_conversation(contact_id, inbox_id)

    # ══════════════════════════════════════════════════════════════════════════
    # MENSAJES
    # ══════════════════════════════════════════════════════════════════════════

    async def send_message(
        self,
        conversation_id: int,
        content: str,
        private: bool = False,
    ) -> bool:
        """
        Envía un mensaje de texto en una conversación.
        Chatwoot lo reenvía automáticamente al canal (WhatsApp, etc.).
        """
        if not self.api_token:
            logger.error("CHATWOOT_API_TOKEN no configurado en .env")
            return False

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    self._api(f"conversations/{conversation_id}/messages"),
                    headers=self._headers(),
                    json={
                        "content": content,
                        "message_type": "outgoing",
                        "private": private,
                    },
                )
                resp.raise_for_status()
                logger.info(f"Mensaje enviado → conversacion {conversation_id}")
                return True
            except httpx.HTTPStatusError as e:
                logger.error(f"Error HTTP Chatwoot send_message: {e.response.status_code} — {e.response.text}")
                return False
            except Exception as e:
                logger.error(f"Error enviando mensaje Chatwoot: {e}")
                return False

    # ══════════════════════════════════════════════════════════════════════════
    # NOTIFICACIÓN SALIENTE (todo en uno)
    # ══════════════════════════════════════════════════════════════════════════

    async def send_notification(
        self,
        phone: str,
        message: str,
        name: str = "",
        email: str = "",
        labels: list[str] | None = None,
        inbox_id: int | None = None,
    ) -> bool:
        """
        Envía una notificación saliente a un contacto por WhatsApp
        y la deja registrada en el CRM de Chatwoot.

        Flujo interno:
            1. Busca o crea el contacto por teléfono
            2. Busca o crea la conversación (reutiliza si ya hay una abierta)
            3. Envía el mensaje (Chatwoot → WhatsApp)
            4. Agrega etiquetas opcionales

        Args:
            phone:    Número en formato +573201234567
            message:  Texto del mensaje (puede incluir emojis y saltos de línea)
            name:     Nombre del contacto (para crear si no existe)
            email:    Email opcional del contacto
            labels:   Etiquetas Chatwoot a aplicar (ej. ['notificacion', 'cita'])
            inbox_id: ID del inbox de WhatsApp (usa CHATWOOT_INBOX_ID por defecto)

        Returns:
            True si el mensaje se envió correctamente, False si hubo error.
        """
        if not self.api_token:
            logger.error("CHATWOOT_API_TOKEN no configurado — notificacion cancelada")
            return False

        # 1. Contacto
        contact_id = await self.get_or_create_contact(phone, name, email)
        if not contact_id:
            logger.error(f"No se pudo obtener/crear contacto para {phone}")
            return False

        # 2. Conversación
        conv_id = await self.get_or_create_conversation(contact_id, inbox_id)
        if not conv_id:
            logger.error(f"No se pudo obtener/crear conversacion para contact_id={contact_id}")
            return False

        # 3. Mensaje
        sent = await self.send_message(conv_id, message)

        # 4. Etiquetas (opcional)
        if sent and labels:
            await self.add_label(conv_id, labels)

        return sent

    # ══════════════════════════════════════════════════════════════════════════
    # UTILIDADES
    # ══════════════════════════════════════════════════════════════════════════

    async def assign_conversation(self, conversation_id: int, assignee_id: int) -> bool:
        """Asigna una conversacion a un agente humano."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    self._api(f"conversations/{conversation_id}/assignments"),
                    headers=self._headers(),
                    json={"assignee_id": assignee_id},
                )
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"Error asignando conversacion {conversation_id}: {e}")
                return False

    async def update_conversation_status(self, conversation_id: int, status: str) -> bool:
        """
        Cambia el estado de una conversacion.
        status: 'open' | 'resolved' | 'pending' | 'snoozed'
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.patch(
                    self._api(f"conversations/{conversation_id}"),
                    headers=self._headers(),
                    json={"status": status},
                )
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"Error actualizando estado conversacion {conversation_id}: {e}")
                return False

    async def add_label(self, conversation_id: int, labels: list[str]) -> bool:
        """Agrega etiquetas a una conversacion. Ej: ['lead-caliente', 'agendado']"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    self._api(f"conversations/{conversation_id}/labels"),
                    headers=self._headers(),
                    json={"labels": labels},
                )
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"Error agregando etiqueta a conversacion {conversation_id}: {e}")
                return False

    async def get_conversation(self, conversation_id: int) -> dict | None:
        """Obtiene los detalles de una conversacion."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    self._api(f"conversations/{conversation_id}"),
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.error(f"Error obteniendo conversacion {conversation_id}: {e}")
                return None


# Singleton — importar desde cualquier parte del proyecto
chatwoot_service = ChatwootService()
