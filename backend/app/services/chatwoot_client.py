"""
services/chatwoot_client.py
============================
Cliente HTTP de bajo nivel para la API de Chatwoot CRM, tenant-aware.

RESPONSABILIDAD UNICA: hablar con la API de Chatwoot usando la configuracion
de una Account concreta y devolver el resultado. No sabe nada de tenants,
Meta, ni de logica de notificaciones de negocio — esa resolucion vive en
ChatwootConfigService.

Reemplaza al singleton global `chatwoot_service` (services/chatwoot_service.py),
que leia CHATWOOT_API_TOKEN/CHATWOOT_ACCOUNT_ID/CHATWOOT_INBOX_ID de settings.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


class ChatwootClientError(RuntimeError):
    pass


def sanitize_chatwoot_error(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.lstrip().lower()
    if stripped.startswith("<!doctype html") or stripped.startswith("<html"):
        return "Chatwoot devolvio una pagina HTML en vez de una respuesta de API. Verifica base_url y account_id."
    text = re.sub(r"api_access_token[\"']?\s*[:=]\s*[\"']?[\w.\-]+", "api_access_token=[REDACTED]", value)
    text = re.sub(r"\+?\d[\d\s().-]{6,}\d", "[REDACTED_PHONE]", text)
    text = re.sub(r"[\w.\-+]+@[\w.\-]+\.\w+", "[REDACTED_EMAIL]", text)
    return text[:500]


@dataclass(frozen=True)
class ChatwootClientConfig:
    base_url: str
    account_id: int
    api_token: str
    default_inbox_id: int | None = None


class ChatwootClient:
    """Cliente HTTP para la API de Chatwoot CRM, construido por tenant/Account."""

    def __init__(self, config: ChatwootClientConfig, *, timeout: float = 10.0) -> None:
        self.config = config
        self.timeout = timeout

    # -- Helpers internos -----------------------------------------------------

    def _headers(self) -> dict:
        return {
            "api_access_token": self.config.api_token,
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        base = self.config.base_url.rstrip("/")
        return f"{base}/api/v1/accounts/{self.config.account_id}/{path}"

    def get_account_profile(self) -> dict:
        """Golpea un endpoint liviano para validar que la Account/token son validos.

        Chatwoot no expone /api/v1/accounts/{id}/profile (el profile es global,
        no esta anidado bajo account); se usa el endpoint de Account en su lugar
        para validar token + account_id juntos.
        """
        with httpx.Client(timeout=self.timeout) as client:
            try:
                resp = client.get(self._url(""), headers=self._headers())
            except httpx.HTTPError as exc:
                raise ChatwootClientError(sanitize_chatwoot_error(str(exc)) or "Chatwoot request failed") from exc
            if resp.status_code >= 400:
                raise ChatwootClientError(sanitize_chatwoot_error(resp.text) or "Chatwoot request failed")
            try:
                return resp.json()
            except ValueError as exc:
                raise ChatwootClientError("Chatwoot returned an invalid JSON response") from exc

    # -- Contactos --------------------------------------------------------------

    async def search_contact(self, phone: str) -> dict | None:
        phone_clean = phone.strip().replace(" ", "")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(
                    self._url("contacts/search"),
                    headers=self._headers(),
                    params={"q": phone_clean, "include_contacts": True},
                )
                resp.raise_for_status()
                contacts = resp.json().get("payload", [])
                return contacts[0] if contacts else None
            except Exception as e:
                logger.error("[Chatwoot] Error buscando contacto: %s", e)
                return None

    async def create_contact(self, phone: str, name: str = "", email: str = "") -> dict | None:
        phone_clean = phone.strip().replace(" ", "")
        payload: dict = {"phone_number": phone_clean}
        if name:
            payload["name"] = name
        if email:
            payload["email"] = email

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(self._url("contacts"), headers=self._headers(), json=payload)
                resp.raise_for_status()
                contact_resp = resp.json()
                if "payload" in contact_resp and "contact" in contact_resp["payload"]:
                    return contact_resp["payload"]["contact"]
                return contact_resp.get("payload", contact_resp)
            except httpx.HTTPStatusError as e:
                logger.error("[Chatwoot] Error HTTP creando contacto: %s", sanitize_chatwoot_error(e.response.text))
                return None
            except Exception as e:
                logger.error("[Chatwoot] Error creando contacto: %s", e)
                return None

    async def get_or_create_contact(self, phone: str, name: str = "", email: str = "") -> int | None:
        contact = await self.search_contact(phone)
        if contact:
            return contact["id"]
        contact = await self.create_contact(phone, name, email)
        return contact["id"] if contact else None

    # -- Conversaciones -----------------------------------------------------

    async def get_open_conversation(self, contact_id: int) -> int | None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(self._url(f"contacts/{contact_id}/conversations"), headers=self._headers())
                resp.raise_for_status()
                for conv in resp.json().get("payload", []):
                    if conv.get("status") in ("open", "pending"):
                        return conv["id"]
                return None
            except Exception as e:
                logger.error("[Chatwoot] Error buscando conversaciones del contacto: %s", e)
                return None

    async def create_conversation(self, contact_id: int, inbox_id: int | None = None) -> int | None:
        resolved_inbox_id = inbox_id or self.config.default_inbox_id
        if not resolved_inbox_id:
            logger.error("[Chatwoot] No hay inbox_id configurado para crear conversacion")
            return None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    self._url("conversations"),
                    headers=self._headers(),
                    json={"contact_id": contact_id, "inbox_id": resolved_inbox_id},
                )
                resp.raise_for_status()
                return resp.json().get("id")
            except httpx.HTTPStatusError as e:
                logger.error("[Chatwoot] Error HTTP creando conversacion: %s", sanitize_chatwoot_error(e.response.text))
                return None
            except Exception as e:
                logger.error("[Chatwoot] Error creando conversacion: %s", e)
                return None

    async def get_or_create_conversation(self, contact_id: int, inbox_id: int | None = None) -> int | None:
        conv_id = await self.get_open_conversation(contact_id)
        if conv_id:
            return conv_id
        return await self.create_conversation(contact_id, inbox_id)

    # -- Mensajes -------------------------------------------------------------

    async def send_message(self, conversation_id: int, content: str, private: bool = False) -> bool:
        """
        private=False -> el cliente lo recibe por WhatsApp.
        private=True  -> nota interna, solo visible para agentes en CRM.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    self._url(f"conversations/{conversation_id}/messages"),
                    headers=self._headers(),
                    json={"content": content, "message_type": "outgoing", "private": private},
                )
                resp.raise_for_status()
                return True
            except httpx.HTTPStatusError as e:
                logger.error(
                    "[Chatwoot] Error HTTP send_message conv=%s: %s",
                    conversation_id,
                    sanitize_chatwoot_error(e.response.text),
                )
                return False
            except Exception as e:
                logger.error("[Chatwoot] Error send_message conv=%s: %s", conversation_id, e)
                return False

    # -- Utilidades de conversacion -------------------------------------------

    async def assign_conversation(self, conversation_id: int, assignee_id: int) -> bool:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    self._url(f"conversations/{conversation_id}/assignments"),
                    headers=self._headers(),
                    json={"assignee_id": assignee_id},
                )
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error("[Chatwoot] Error asignando conversacion %s: %s", conversation_id, e)
                return False

    async def update_conversation_status(self, conversation_id: int, status: str) -> bool:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.patch(
                    self._url(f"conversations/{conversation_id}"), headers=self._headers(), json={"status": status}
                )
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error("[Chatwoot] Error actualizando estado conv=%s: %s", conversation_id, e)
                return False

    async def add_label(self, conversation_id: int, labels: list[str]) -> bool:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    self._url(f"conversations/{conversation_id}/labels"),
                    headers=self._headers(),
                    json={"labels": labels},
                )
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error("[Chatwoot] Error agregando etiquetas a conv=%s: %s", conversation_id, e)
                return False

    async def get_conversation(self, conversation_id: int) -> dict | None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(self._url(f"conversations/{conversation_id}"), headers=self._headers())
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.error("[Chatwoot] Error obteniendo conversacion %s: %s", conversation_id, e)
                return None

    async def assign_team(self, conversation_id: int, team_id: int) -> bool:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    self._url(f"conversations/{conversation_id}/assignments"),
                    headers=self._headers(),
                    json={"team_id": team_id},
                )
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error("[Chatwoot] Error asignando team a conv=%s: %s", conversation_id, e)
                return False

    async def list_inboxes(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(self._url("inboxes"), headers=self._headers())
            if resp.status_code >= 400:
                raise ChatwootClientError(sanitize_chatwoot_error(resp.text) or "Chatwoot request failed")
            return resp.json().get("payload", [])

    async def list_teams(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(self._url("teams"), headers=self._headers())
            if resp.status_code >= 400:
                raise ChatwootClientError(sanitize_chatwoot_error(resp.text) or "Chatwoot request failed")
            data = resp.json()
            return data if isinstance(data, list) else []

    async def list_agents(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(self._url("agents"), headers=self._headers())
            if resp.status_code >= 400:
                raise ChatwootClientError(sanitize_chatwoot_error(resp.text) or "Chatwoot request failed")
            data = resp.json()
            return data.get("payload", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

    async def create_inbox(self, *, name: str, webhook_url: str) -> dict:
        """Crea un inbox tipo 'api' con el token propio del tenant (sirve tanto
        para Accounts managed como external, a diferencia del aprovisionamiento
        inicial que usa la Platform API)."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self._url("inboxes"),
                headers=self._headers(),
                json={"name": name, "channel": {"type": "api", "webhook_url": webhook_url}},
            )
            if resp.status_code >= 400:
                raise ChatwootClientError(sanitize_chatwoot_error(resp.text) or "Chatwoot request failed")
            return resp.json()

    async def create_team(self, *, name: str, description: str | None = None) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self._url("teams"),
                headers=self._headers(),
                json={"name": name, "description": description},
            )
            if resp.status_code >= 400:
                raise ChatwootClientError(sanitize_chatwoot_error(resp.text) or "Chatwoot request failed")
            return resp.json()

    async def invite_agent(self, *, name: str, email: str, role: str = "agent") -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self._url("agents"),
                headers=self._headers(),
                json={"name": name, "email": email, "role": role},
            )
            if resp.status_code >= 400:
                raise ChatwootClientError(sanitize_chatwoot_error(resp.text) or "Chatwoot request failed")
            return resp.json()

    async def update_inbox(self, inbox_id: int, *, name: str) -> dict:
        """Chatwoot no expone un DELETE para inboxes en su API publica (solo
        list/create/update); renombrar es lo unico disponible aqui."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.patch(
                self._url(f"inboxes/{inbox_id}"), headers=self._headers(), json={"name": name}
            )
            if resp.status_code >= 400:
                raise ChatwootClientError(sanitize_chatwoot_error(resp.text) or "Chatwoot request failed")
            return resp.json()

    async def update_team(self, team_id: int, *, name: str | None = None, description: str | None = None) -> dict:
        payload = {k: v for k, v in {"name": name, "description": description}.items() if v is not None}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.patch(self._url(f"teams/{team_id}"), headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                raise ChatwootClientError(sanitize_chatwoot_error(resp.text) or "Chatwoot request failed")
            return resp.json()

    async def delete_team(self, team_id: int) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.delete(self._url(f"teams/{team_id}"), headers=self._headers())
            if resp.status_code >= 400:
                raise ChatwootClientError(sanitize_chatwoot_error(resp.text) or "Chatwoot request failed")

    async def update_agent(self, agent_id: int, *, name: str | None = None, role: str | None = None) -> dict:
        payload = {k: v for k, v in {"name": name, "role": role}.items() if v is not None}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.put(self._url(f"agents/{agent_id}"), headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                raise ChatwootClientError(sanitize_chatwoot_error(resp.text) or "Chatwoot request failed")
            return resp.json()

    async def delete_agent(self, agent_id: int) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.delete(self._url(f"agents/{agent_id}"), headers=self._headers())
            if resp.status_code >= 400:
                raise ChatwootClientError(sanitize_chatwoot_error(resp.text) or "Chatwoot request failed")
