from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings

WHATSAPP_GRAPH_VERSION = settings.WHATSAPP_GRAPH_VERSION


class WhatsAppCloudClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class WhatsAppClientConfig:
    access_token: str
    phone_number_id: str


def sanitize_whatsapp_error(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [REDACTED]", value)
    text = re.sub(r"EA[A-Za-z0-9]{20,}", "[REDACTED_TOKEN]", text)
    text = re.sub(r"\+?\d[\d\s().-]{6,}\d", "[REDACTED_PHONE]", text)
    text = re.sub(r"[\w.\-+]+@[\w.\-]+\.\w+", "[REDACTED_EMAIL]", text)
    return text[:500]


class WhatsAppCloudClient:
    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        config: WhatsAppClientConfig,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"https://graph.facebook.com/{WHATSAPP_GRAPH_VERSION}/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {config.access_token}", "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(method, url, headers=headers, json=json, params=params)
        except httpx.HTTPError as exc:
            raise WhatsAppCloudClientError(sanitize_whatsapp_error(str(exc)) or "WhatsApp request failed") from exc

        if response.status_code >= 400:
            raise WhatsAppCloudClientError(sanitize_whatsapp_error(response.text) or "WhatsApp request failed")

        try:
            payload = response.json()
        except ValueError as exc:
            raise WhatsAppCloudClientError("WhatsApp returned an invalid JSON response") from exc
        return payload if isinstance(payload, dict) else {}

    def get_phone_number_info(self, config: WhatsAppClientConfig) -> dict[str, Any]:
        return self._request("GET", config.phone_number_id, config)

    def get_message_templates(
        self,
        config: WhatsAppClientConfig,
        *,
        business_account_id: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        business_account_id = business_account_id.strip()
        if not business_account_id:
            raise ValueError("Business Account ID / WABA ID is required to sync templates.")
        page_size = min(max(limit, 1), 100)
        templates: list[dict[str, Any]] = []
        after: str | None = None
        while len(templates) < 500:
            params: dict[str, Any] = {
                "limit": page_size,
                "fields": "name,status,category,language,components",
            }
            if after:
                params["after"] = after
            payload = self._request(
                "GET",
                f"{business_account_id}/message_templates",
                config,
                params=params,
            )
            data = payload.get("data")
            if isinstance(data, list):
                templates.extend(item for item in data if isinstance(item, dict))
            cursors = (payload.get("paging") or {}).get("cursors") or {}
            next_after = cursors.get("after")
            if not next_after or next_after == after or not (payload.get("paging") or {}).get("next"):
                break
            after = str(next_after)
        return {"data": templates[:500]}

    def send_template_message(
        self,
        config: WhatsAppClientConfig,
        *,
        to_phone: str,
        template_name: str,
        language: str,
        components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
            },
        }
        if components:
            payload["template"]["components"] = components
        return self._request("POST", f"{config.phone_number_id}/messages", config, json=payload)

    def send_text_message(self, config: WhatsAppClientConfig, *, to_phone: str, message: str) -> dict[str, Any]:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }
        return self._request("POST", f"{config.phone_number_id}/messages", config, json=payload)
