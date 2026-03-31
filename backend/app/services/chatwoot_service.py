import httpx
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

CHATWOOT_BASE_URL = "https://crm.serviglobal-ia.com"
ACCOUNT_ID = 1  # Settings → General en tu Chatwoot


class ChatwootService:
    """
    Servicio para interactuar con la API de Chatwoot.
    Úsalo para enviar mensajes, asignar conversaciones y escalar a humanos.
    """

    def __init__(self):
        # Obtén este token en: crm.serviglobal-ia.com → Profile → Access Token
        self.api_token = getattr(settings, "CHATWOOT_API_TOKEN", "")
        self.base_url  = CHATWOOT_BASE_URL
        self.account_id = ACCOUNT_ID

    def _headers(self) -> dict:
        return {
            "api_access_token": self.api_token,
            "Content-Type": "application/json",
        }

    # ─── Mensajes ──────────────────────────────────────────────────────────────

    async def send_message(self, conversation_id: int, content: str, private: bool = False) -> bool:
        """
        Envía un mensaje en una conversación de Chatwoot.
        Chatwoot lo reenvía automáticamente al canal (WhatsApp, etc.).
        """
        if not self.api_token:
            logger.error("CHATWOOT_API_TOKEN no configurado en .env")
            return False

        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages"

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    url,
                    headers=self._headers(),
                    json={
                        "content": content,
                        "message_type": "outgoing",
                        "private": private,
                    },
                )
                response.raise_for_status()
                logger.info(f"Mensaje enviado a conversación {conversation_id}")
                return True

            except httpx.HTTPStatusError as e:
                logger.error(f"Error HTTP Chatwoot: {e.response.status_code} — {e.response.text}")
                return False
            except Exception as e:
                logger.error(f"Error enviando mensaje a Chatwoot: {str(e)}")
                return False

    # ─── Conversaciones ────────────────────────────────────────────────────────

    async def assign_conversation(self, conversation_id: int, assignee_id: int) -> bool:
        """
        Asigna una conversación a un agente humano específico.
        Útil para escalar desde el bot.
        """
        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/assignments"

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    url,
                    headers=self._headers(),
                    json={"assignee_id": assignee_id},
                )
                response.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"Error asignando conversación {conversation_id}: {str(e)}")
                return False

    async def update_conversation_status(self, conversation_id: int, status: str) -> bool:
        """
        Cambia el estado de una conversación.
        status: 'open' | 'resolved' | 'pending' | 'snoozed'
        """
        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.patch(
                    url,
                    headers=self._headers(),
                    json={"status": status},
                )
                response.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"Error actualizando estado conversación {conversation_id}: {str(e)}")
                return False

    async def add_label(self, conversation_id: int, labels: list[str]) -> bool:
        """
        Agrega etiquetas a una conversación. Ej: ['lead-caliente', 'agendado']
        """
        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/labels"

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    url,
                    headers=self._headers(),
                    json={"labels": labels},
                )
                response.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"Error agregando etiqueta a conversación {conversation_id}: {str(e)}")
                return False

    async def get_conversation(self, conversation_id: int) -> dict | None:
        """
        Obtiene los detalles de una conversación.
        """
        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(url, headers=self._headers())
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Error obteniendo conversación {conversation_id}: {str(e)}")
                return None


# Singleton — importar desde cualquier parte del proyecto
chatwoot_service = ChatwootService()
