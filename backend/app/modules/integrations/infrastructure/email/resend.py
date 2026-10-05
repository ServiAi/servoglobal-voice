from __future__ import annotations

import logging
from typing import Any

import httpx

from app.modules.integrations.domain.email import mask_email as _mask_email
from app.modules.integrations.domain.email import (
    sanitize_resend_error as _sanitize_resend_error,
)
from app.modules.integrations.domain.errors import ProviderRejected

logger = logging.getLogger(__name__)


class ResendServiceError(ProviderRejected):
    pass


class ResendService:
    base_url = "https://api.resend.com"

    def send_email(
        self,
        *,
        api_key: str,
        from_email: str,
        to_email: str,
        subject: str,
        html: str,
        text: str | None = None,
        reply_to: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        idempotency_key: str | None = None,
        tenant_id: str | None = None,
        lead_id: str | None = None,
        template_key: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
        }
        if text:
            payload["text"] = text
        if reply_to:
            payload["reply_to"] = reply_to
        if attachments:
            payload["attachments"] = attachments

        headers = {"Authorization": f"Bearer {api_key}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        logger.info(
            "Sending transactional email provider=resend tenant_id=%s lead_id=%s status=pending template_key=%s has_attachments=%s attachment_count=%s to=%s",
            tenant_id,
            lead_id,
            template_key,
            bool(attachments),
            len(attachments or []),
            _mask_email(to_email),
        )
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(f"{self.base_url}/emails", headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise ResendServiceError(_sanitize_resend_error(str(exc))) from exc

        if response.status_code >= 400:
            raise ResendServiceError(_sanitize_resend_error(response.text))

        data = response.json()
        provider_id = data.get("id")
        if not provider_id:
            raise ResendServiceError("Resend response did not include email id.")
        return str(provider_id)

    def send_test_email(
        self,
        *,
        api_key: str,
        from_email: str,
        to_email: str,
        reply_to: str | None = None,
        tenant_id: str | None = None,
    ) -> str:
        return self.send_email(
            api_key=api_key,
            from_email=from_email,
            to_email=to_email,
            reply_to=reply_to,
            subject="Prueba Resend ServiGlobal IA",
            html="<p>La integracion transaccional de Resend esta activa.</p>",
            text="La integracion transaccional de Resend esta activa.",
            tenant_id=tenant_id,
            template_key="test_email",
        )
