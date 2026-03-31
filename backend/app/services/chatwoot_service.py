"""
services/chatwoot_service.py
============================
Cliente HTTP de bajo nivel para la API de Chatwoot CRM.

RESPONSABILIDAD ÚNICA: Hablar con Chatwoot API y devolver el resultado.
No sabe nada de Meta, ni de lógica de notificaciones de negocio.

Métodos disponibles:
  Contactos:
    search_contact(phone)                  → dict | None
    create_contact(phone, name, email)     → dict | None
    get_or_create_contact(phone, ...)      → int | None   (retorna contact_id)

  Conversaciones:
    get_open_conversation(contact_id)      → int | None   (retorna conversation_id)
    create_conversation(contact_id, ...)   → int | None
    get_or_create_conversation(contact_id) → int | None

  Mensajes:
    send_message(conversation_id, content, private=False)  → bool
    # private=True → nota interna (solo agentes la ven, cliente NO)
    # private=False → mensaje normal que llega al cliente

  Utilidades:
    assign_conversation(conv_id, assignee_id) → bool
    update_conversation_status(conv_id, status) → bool
    add_label(conv_id, labels) → bool
    get_conversation(conv_id) → dict | None
"""

import httpx
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

CHATWOOT_BASE_URL = "https://crm.serviglobal-ia.com"


class ChatwootService:
    """Cliente HTTP para la API de Chatwoot CRM."""

    def __init__(self):
        self.api_token  = getattr(settings, "CHATWOOT_API_TOKEN", "")
        self.account_id = getattr(settings, "CHATWOOT_ACCOUNT_ID", 1)
        self.inbox_id   = getattr(settings, "CHATWOOT_INBOX_ID", 1)
        self.base_url   = CHATWOOT_BASE_URL

    # ── Helpers internos ─────────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            "api_access_token": self.api_token,
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1/accounts/{self.account_id}/{path}"

    def _ready(self) -> bool:
        if not self.api_token:
            logger.error("[Chatwoot] CHATWOOT_API_TOKEN no configurado en .env")
            return False
        return True

    # ══════════════════════════════════════════════════════════════════════════
    # CONTACTOS
    # ══════════════════════════════════════════════════════════════════════════

    async def search_contact(self, phone: str) -> dict | None:
        """Busca un contacto por teléfono. Retorna el primer resultado o None."""
        phone_clean = phone.strip().replace(" ", "")
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    self._url("contacts/search"),
                    headers=self._headers(),
                    params={"q": phone_clean, "include_contacts": True},
                )
                resp.raise_for_status()
                contacts = resp.json().get("payload", [])
                if contacts:
                    logger.info(f"[Chatwoot] Contacto encontrado: id={contacts[0]['id']} phone={phone_clean}")
                    return contacts[0]
                return None
            except Exception as e:
                logger.error(f"[Chatwoot] Error buscando contacto {phone}: {e}")
                return None

    async def create_contact(self, phone: str, name: str = "", email: str = "") -> dict | None:
        """Crea un contacto nuevo en Chatwoot."""
        phone_clean = phone.strip().replace(" ", "")
        payload: dict = {"phone_number": phone_clean}
        if name:
            payload["name"] = name
        if email:
            payload["email"] = email

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    self._url("contacts"),
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                contact = resp.json()
                logger.info(f"[Chatwoot] Contacto creado: id={contact.get('id')} phone={phone_clean}")
                return contact
            except httpx.HTTPStatusError as e:
                logger.error(f"[Chatwoot] Error HTTP creando contacto {phone}: {e.response.text}")
                return None
            except Exception as e:
                logger.error(f"[Chatwoot] Error creando contacto {phone}: {e}")
                return None

    async def get_or_create_contact(
        self, phone: str, name: str = "", email: str = ""
    ) -> int | None:
        """Busca el contacto; si no existe, lo crea. Retorna contact_id o None."""
        contact = await self.search_contact(phone)
        if contact:
            return contact["id"]
        contact = await self.create_contact(phone, name, email)
        return contact["id"] if contact else None

    # ══════════════════════════════════════════════════════════════════════════
    # CONVERSACIONES
    # ══════════════════════════════════════════════════════════════════════════

    async def get_open_conversation(self, contact_id: int) -> int | None:
        """Busca una conversación abierta o pendiente del contacto."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    self._url(f"contacts/{contact_id}/conversations"),
                    headers=self._headers(),
                )
                resp.raise_for_status()
                for conv in resp.json().get("payload", []):
                    if conv.get("status") in ("open", "pending"):
                        logger.info(f"[Chatwoot] Conversación abierta reutilizada: id={conv['id']}")
                        return conv["id"]
                return None
            except Exception as e:
                logger.error(f"[Chatwoot] Error buscando conversaciones del contacto {contact_id}: {e}")
                return None

    async def create_conversation(
        self,
        contact_id: int,
        inbox_id: int | None = None,
    ) -> int | None:
        """Crea una nueva conversación en Chatwoot para el contacto."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    self._url("conversations"),
                    headers=self._headers(),
                    json={
                        "contact_id": contact_id,
                        "inbox_id": inbox_id or self.inbox_id,
                    },
                )
                resp.raise_for_status()
                conv = resp.json()
                conv_id = conv.get("id")
                logger.info(f"[Chatwoot] Conversación creada: id={conv_id} contact_id={contact_id}")
                return conv_id
            except httpx.HTTPStatusError as e:
                logger.error(f"[Chatwoot] Error HTTP creando conversación: {e.response.text}")
                return None
            except Exception as e:
                logger.error(f"[Chatwoot] Error creando conversación: {e}")
                return None

    async def get_or_create_conversation(
        self,
        contact_id: int,
        inbox_id: int | None = None,
    ) -> int | None:
        """Reutiliza conversación abierta; si no hay, crea una nueva."""
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
        Envía un mensaje en una conversación.

        Args:
            conversation_id: ID de la conversación en Chatwoot
            content:         Texto del mensaje (soporta markdown básico)
            private:         False → el cliente lo recibe por WhatsApp
                             True  → nota interna, solo visible para agentes en CRM

        Returns:
            True si Chatwoot aceptó el mensaje.
        """
        if not self._ready():
            return False

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    self._url(f"conversations/{conversation_id}/messages"),
                    headers=self._headers(),
                    json={
                        "content": content,
                        "message_type": "outgoing",
                        "private": private,
                    },
                )
                resp.raise_for_status()
                tipo = "nota interna" if private else "mensaje"
                logger.info(f"[Chatwoot] {tipo.capitalize()} enviado → conversación {conversation_id}")
                return True
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"[Chatwoot] Error HTTP send_message conv={conversation_id}: "
                    f"{e.response.status_code} — {e.response.text}"
                )
                return False
            except Exception as e:
                logger.error(f"[Chatwoot] Error send_message conv={conversation_id}: {e}")
                return False

    # ══════════════════════════════════════════════════════════════════════════
    # UTILIDADES DE CONVERSACIÓN
    # ══════════════════════════════════════════════════════════════════════════

    async def assign_conversation(self, conversation_id: int, assignee_id: int) -> bool:
        """Asigna una conversación a un agente humano (por su ID en Chatwoot)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    self._url(f"conversations/{conversation_id}/assignments"),
                    headers=self._headers(),
                    json={"assignee_id": assignee_id},
                )
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"[Chatwoot] Error asignando conversación {conversation_id}: {e}")
                return False

    async def update_conversation_status(self, conversation_id: int, status: str) -> bool:
        """
        Cambia el estado de una conversación.
        status: 'open' | 'resolved' | 'pending' | 'snoozed'
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.patch(
                    self._url(f"conversations/{conversation_id}"),
                    headers=self._headers(),
                    json={"status": status},
                )
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"[Chatwoot] Error actualizando estado conv={conversation_id}: {e}")
                return False

    async def add_label(self, conversation_id: int, labels: list[str]) -> bool:
        """Agrega etiquetas a una conversación. Ej: ['lead-caliente', 'cita-confirmada']"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    self._url(f"conversations/{conversation_id}/labels"),
                    headers=self._headers(),
                    json={"labels": labels},
                )
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"[Chatwoot] Error agregando etiquetas a conv={conversation_id}: {e}")
                return False

    async def get_conversation(self, conversation_id: int) -> dict | None:
        """Obtiene los detalles completos de una conversación."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    self._url(f"conversations/{conversation_id}"),
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.error(f"[Chatwoot] Error obteniendo conversación {conversation_id}: {e}")
                return None


# Singleton — importar desde cualquier parte del proyecto
chatwoot_service = ChatwootService()
