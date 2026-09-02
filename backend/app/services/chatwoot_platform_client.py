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
la Account (inbox, webhook) requiere en cambio el `access_token` de un
usuario real de esa Account contra `/api/v1/accounts/*`.

Nota (verificado contra la instancia real): los tokens de Agent Bot NO
sirven para nada en `/api/v1/accounts/*` — Chatwoot responde
"Access to this endpoint is not authorized for bots" incluso para acciones
tan basicas como crear un contacto. Por eso el aprovisionamiento crea un
Usuario real (via Platform API) y lo vincula como administrator, en vez de
usar un Agent Bot.
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

    def _request(self, method: str, path: str, *, headers: dict, json: dict | None) -> dict:
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

    def _user_headers(self, user_token: str) -> dict:
        return {"api_access_token": user_token, "Content-Type": "application/json"}

    def create_account(self, *, name: str) -> dict:
        """POST /platform/api/v1/accounts -> {"id": int, "name": str}."""
        return self._request(
            "POST", "/platform/api/v1/accounts", headers=self._platform_headers(), json={"name": name}
        )

    def create_user(self, *, name: str, email: str, password: str) -> dict:
        """POST /platform/api/v1/users -> incluye "access_token" del usuario, ya confirmado."""
        return self._request(
            "POST",
            "/platform/api/v1/users",
            headers=self._platform_headers(),
            json={"name": name, "email": email, "password": password},
        )

    def link_account_user(self, *, account_id: int, user_id: int, role: str = "administrator") -> dict:
        """POST /platform/api/v1/accounts/{account_id}/account_users."""
        return self._request(
            "POST",
            f"/platform/api/v1/accounts/{account_id}/account_users",
            headers=self._platform_headers(),
            json={"user_id": user_id, "role": role},
        )

    def create_api_inbox(self, *, account_id: int, user_token: str, name: str, webhook_url: str) -> dict:
        """POST /api/v1/accounts/{account_id}/inboxes con canal tipo 'api'."""
        return self._request(
            "POST",
            f"/api/v1/accounts/{account_id}/inboxes",
            headers=self._user_headers(user_token),
            json={"name": name, "channel": {"type": "api", "webhook_url": webhook_url}},
        )

    def create_account_webhook(self, *, account_id: int, user_token: str, url: str) -> dict:
        """POST /api/v1/accounts/{account_id}/webhooks — mismo mecanismo que el operador
        configura a mano en modo 'external' (Settings -> Integrations -> Webhooks)."""
        return self._request(
            "POST",
            f"/api/v1/accounts/{account_id}/webhooks",
            headers=self._user_headers(user_token),
            json={"url": url, "subscriptions": ["message_created"]},
        )
