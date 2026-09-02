"""
services/chatwoot_platform_client.py
=====================================
Cliente de la Platform API (Super Admin) de Chatwoot.

RESPONSABILIDAD UNICA: aprovisionar Accounts nuevas contra la instancia
compartida de Chatwoot para el modo "managed" de TenantChatwootConfig.
No confundir con ChatwootClient (API por Account, usada en runtime por
tenant una vez que la Account ya existe).

La Platform API usa un token de Super Admin (`CHATWOOT_PLATFORM_API_TOKEN`,
global, no por tenant) contra `/platform/api/v1/*`. Crear recursos dentro de
la Account (inbox, asociar el Agent Bot) requiere en cambio el
`access_token` del Agent Bot recien creado contra `/api/v1/accounts/*`.
"""

from __future__ import annotations

import httpx

from app.services.chatwoot_client import sanitize_chatwoot_error


class ChatwootPlatformError(RuntimeError):
    pass


class ChatwootPlatformClient:
    def __init__(self, base_url: str, platform_token: str, *, timeout: float = 15.0) -> None:
        if not platform_token:
            raise ChatwootPlatformError("Chatwoot platform API token is not configured")
        self.base_url = base_url.rstrip("/")
        self.platform_token = platform_token
        self.timeout = timeout

    def _request(self, method: str, path: str, *, headers: dict, json: dict) -> dict:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            try:
                resp = client.request(method, url, headers=headers, json=json)
            except httpx.HTTPError as exc:
                raise ChatwootPlatformError(
                    sanitize_chatwoot_error(str(exc)) or "Chatwoot platform request failed"
                ) from exc
            if resp.status_code >= 400:
                raise ChatwootPlatformError(
                    sanitize_chatwoot_error(resp.text) or f"Chatwoot platform request failed ({resp.status_code})"
                )
            if not resp.content:
                return {}
            try:
                return resp.json()
            except ValueError as exc:
                raise ChatwootPlatformError("Chatwoot platform returned an invalid JSON response") from exc

    def _platform_headers(self) -> dict:
        return {"api_access_token": self.platform_token, "Content-Type": "application/json"}

    def create_account(self, *, name: str) -> dict:
        """POST /platform/api/v1/accounts -> {"id": int, "name": str}."""
        return self._request(
            "POST", "/platform/api/v1/accounts", headers=self._platform_headers(), json={"name": name}
        )

    def create_agent_bot(self, *, name: str, account_id: int, outgoing_url: str) -> dict:
        """POST /platform/api/v1/agent_bots -> incluye "access_token" del bot para esa Account."""
        return self._request(
            "POST",
            "/platform/api/v1/agent_bots",
            headers=self._platform_headers(),
            json={"name": name, "account_id": account_id, "outgoing_url": outgoing_url, "bot_type": 0},
        )

    def create_api_inbox(self, *, account_id: int, agent_bot_token: str, name: str, webhook_url: str) -> dict:
        """POST /api/v1/accounts/{account_id}/inboxes con canal tipo 'api'."""
        headers = {"api_access_token": agent_bot_token, "Content-Type": "application/json"}
        return self._request(
            "POST",
            f"/api/v1/accounts/{account_id}/inboxes",
            headers=headers,
            json={"name": name, "channel": {"type": "api", "webhook_url": webhook_url}},
        )

    def set_inbox_agent_bot(self, *, account_id: int, agent_bot_token: str, inbox_id: int, agent_bot_id: int) -> None:
        """POST /api/v1/accounts/{account_id}/inboxes/{inbox_id}/set_agent_bot."""
        headers = {"api_access_token": agent_bot_token, "Content-Type": "application/json"}
        self._request(
            "POST",
            f"/api/v1/accounts/{account_id}/inboxes/{inbox_id}/set_agent_bot",
            headers=headers,
            json={"agent_bot": agent_bot_id},
        )
