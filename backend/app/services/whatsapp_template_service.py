from __future__ import annotations

import re
from dataclasses import dataclass
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


@dataclass(frozen=True)
class WhatsAppTemplateSyncResult:
    fetched_count: int
    approved_count: int
    synced_count: int
    ignored_count: int


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

    def sync_approved_templates_from_meta(
        self,
        tenant_id: str,
        provider_templates: list[dict[str, Any]],
    ) -> WhatsAppTemplateSyncResult:
        approved = [item for item in provider_templates if str(item.get("status", "")).upper() == "APPROVED"]
        synced = 0
        for item in approved:
            provider_name = str(item.get("name") or "").strip()
            if not provider_name:
                continue
            template_key = re.sub(r"[^a-z0-9_]+", "_", provider_name.lower()).strip("_")[:80]
            if not template_key:
                continue
            body = ""
            for component in item.get("components") or []:
                if isinstance(component, dict) and str(component.get("type", "")).upper() == "BODY":
                    body = str(component.get("text") or "")
                    break
            parameter_keys = list(dict.fromkeys(re.findall(r"\{\{\s*(\d+)\s*\}\}", body)))
            variables = {
                "parameters": [{"key": key, "label": f"Variable {key}"} for key in parameter_keys],
                "meta_status": "APPROVED",
                "source": "meta_sync",
            }
            template = self.db.scalar(
                select(TenantWhatsAppTemplate).where(
                    TenantWhatsAppTemplate.tenant_id == tenant_id,
                    TenantWhatsAppTemplate.template_key == template_key,
                )
            )
            if template is None:
                template = TenantWhatsAppTemplate(tenant_id=tenant_id, template_key=template_key)
                self.db.add(template)
            template.provider_template_name = provider_name
            template.name = provider_name
            template.category = str(item.get("category") or "transactional").lower()
            template.language = str(item.get("language") or "es")
            template.body = body
            template.variables_json = variables
            template.status = "active"
            synced += 1
        self.db.commit()
        return WhatsAppTemplateSyncResult(
            fetched_count=len(provider_templates),
            approved_count=len(approved),
            synced_count=synced,
            ignored_count=len(provider_templates) - len(approved),
        )

    def get_synced_template(
        self,
        tenant_id: str,
        *,
        template_key: str | None,
        provider_template_name: str | None,
    ) -> TenantWhatsAppTemplate:
        if not template_key and not provider_template_name:
            raise ValueError("Template is required")
        conditions = []
        if template_key:
            conditions.append(TenantWhatsAppTemplate.template_key == template_key)
        if provider_template_name:
            conditions.append(TenantWhatsAppTemplate.provider_template_name == provider_template_name)
        template = self.db.scalar(
            select(TenantWhatsAppTemplate).where(
                TenantWhatsAppTemplate.tenant_id == tenant_id,
                *conditions,
            )
        )
        metadata = template.variables_json if template else {}
        if (
            template is None
            or template.status != "active"
            or metadata.get("source") != "meta_sync"
            or metadata.get("meta_status") != "APPROVED"
        ):
            raise ValueError("Template must be active and approved by Meta")
        return template

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

    def get_approved_parameter_keys(self, template: TenantWhatsAppTemplate) -> list[str]:
        parameters = (template.variables_json or {}).get("parameters")
        if parameters is None:
            return []
        if not isinstance(parameters, list):
            raise ValueError("Template parameters are malformed")
        keys: list[str] = []
        for item in parameters:
            if not isinstance(item, dict) or not item.get("key"):
                raise ValueError("Template parameters are malformed")
            keys.append(str(item["key"]))
        return keys

    def build_approved_template_components(
        self,
        template: TenantWhatsAppTemplate,
        variables: dict[str, str],
    ) -> list[dict[str, Any]]:
        keys = self.get_approved_parameter_keys(template)
        if not keys:
            return []
        missing = [key for key in keys if key not in variables]
        if missing:
            raise ValueError(f"Missing template variables: {', '.join(missing)}")
        return [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": str(variables[key])} for key in keys],
            }
        ]
