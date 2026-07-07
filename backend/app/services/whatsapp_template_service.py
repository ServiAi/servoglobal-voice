from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import TenantWhatsAppTemplate


DEFAULT_WHATSAPP_TEMPLATES = [
    {
        "template_key": "lead_follow_up",
        "provider_template_name": "lead_follow_up",
        "name": "Seguimiento comercial",
        "category": "transactional",
        "language": "es",
        "body": "Hola {{contact_name}}, soy {{agent_name}} de ServiGlobal AI. Te escribo para dar seguimiento a tu interes en {{interest}}.",
        "variables_json": {"required": ["contact_name", "agent_name", "interest"]},
    },
    {
        "template_key": "meeting_reminder",
        "provider_template_name": "meeting_reminder",
        "name": "Recordatorio de reunion",
        "category": "transactional",
        "language": "es",
        "body": "Hola {{contact_name}}, te recordamos tu reunion sobre {{interest}}. Si necesitas moverla, respondeme por este chat.",
        "variables_json": {"required": ["contact_name", "interest"]},
    },
]


class WhatsAppTemplateService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_default_templates(self, tenant_id: str) -> None:
        existing = {
            item.template_key
            for item in self.db.scalars(
                select(TenantWhatsAppTemplate).where(TenantWhatsAppTemplate.tenant_id == tenant_id)
            ).all()
        }
        created = False
        for item in DEFAULT_WHATSAPP_TEMPLATES:
            if item["template_key"] in existing:
                continue
            self.db.add(TenantWhatsAppTemplate(tenant_id=tenant_id, **item))
            created = True
        if created:
            self.db.commit()

    def list_templates(self, tenant_id: str) -> list[TenantWhatsAppTemplate]:
        self.ensure_default_templates(tenant_id)
        return self.db.scalars(
            select(TenantWhatsAppTemplate)
            .where(TenantWhatsAppTemplate.tenant_id == tenant_id)
            .order_by(TenantWhatsAppTemplate.template_key)
        ).all()

    def get_template(self, tenant_id: str, template_key: str) -> TenantWhatsAppTemplate:
        self.ensure_default_templates(tenant_id)
        template = self.db.scalar(
            select(TenantWhatsAppTemplate).where(
                TenantWhatsAppTemplate.tenant_id == tenant_id,
                TenantWhatsAppTemplate.template_key == template_key,
                TenantWhatsAppTemplate.status == "active",
            )
        )
        if template is None:
            raise ValueError("WhatsApp template not found")
        return template

    def render_template(self, template: TenantWhatsAppTemplate, variables: dict[str, Any]) -> str:
        def replace(match: re.Match[str]) -> str:
            key = match.group(1).strip()
            value = variables.get(key)
            return "" if value is None else str(value)

        return re.sub(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", replace, template.body)

    def build_components(self, template: TenantWhatsAppTemplate, variables: dict[str, Any]) -> list[dict[str, Any]]:
        required = (template.variables_json or {}).get("required") or []
        parameters = [
            {"type": "text", "text": str(variables.get(key) or "")}
            for key in required
        ]
        if not parameters:
            return []
        return [{"type": "body", "parameters": parameters}]
