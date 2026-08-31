from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import CrmWhatsAppMessage
from app.models.integrations import TenantWhatsAppTemplate
from app.schemas.integrations import WhatsAppTemplateCreateRequest, WhatsAppTemplateUpdateRequest
from app.services.tenant_feature_service import TenantFeatureService, WHATSAPP_BUSINESS_CALLING


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

_ALLOWED_CATEGORIES = {"marketing", "utility", "authentication"}
_NAMED_VARIABLE_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def _render_text(text: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        value = variables.get(key)
        return "" if value is None else str(value)

    return re.sub(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", replace, text)


def _extract_named_variable_keys(*texts: str | None) -> list[str]:
    keys: list[str] = []
    for text in texts:
        if not text:
            continue
        for match in _NAMED_VARIABLE_PATTERN.finditer(text):
            key = match.group(1)
            if key not in keys:
                keys.append(key)
    return keys


def _build_meta_components(
    *, header_text: str | None, body: str, footer_text: str | None, buttons: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    if header_text:
        components.append({"type": "HEADER", "format": "TEXT", "text": header_text})
    components.append({"type": "BODY", "text": body})
    if footer_text:
        components.append({"type": "FOOTER", "text": footer_text})
    if buttons:
        components.append({"type": "BUTTONS", "buttons": buttons})
    return components


def _ensure_voice_call_allowed(db: Session, tenant_id: str, buttons: list[dict[str, Any]]) -> None:
    if not any(button.get("type") == "VOICE_CALL" for button in buttons):
        return
    if not TenantFeatureService(db).is_enabled(tenant_id, WHATSAPP_BUSINESS_CALLING):
        raise ValueError("VOICE_CALL button requires WhatsApp Business Calling to be enabled for this tenant")


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
            self.db.add(
                TenantWhatsAppTemplate(
                    tenant_id=tenant_id,
                    status="draft",
                    source="tenant_authored",
                    parameter_format="NAMED",
                    **item,
                )
            )
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
            template.provider_template_id = str(item.get("id") or template.provider_template_id or "") or None
            template.name = provider_name
            template.category = str(item.get("category") or "transactional").lower()
            template.language = str(item.get("language") or "es")
            template.body = body
            template.variables_json = variables
            template.status = "approved"
            template.meta_status = "APPROVED"
            template.source = "meta_sync"
            template.parameter_format = "POSITIONAL"
            template.components_json = {"components": item.get("components") or []}
            template.last_synced_at = datetime.now(timezone.utc)
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
        if template is None or template.status != "approved":
            raise ValueError("Template must be active and approved by Meta")
        return template

    def get_template(self, tenant_id: str, template_key: str) -> TenantWhatsAppTemplate:
        self.ensure_default_templates(tenant_id)
        template = self.db.scalar(
            select(TenantWhatsAppTemplate).where(
                TenantWhatsAppTemplate.tenant_id == tenant_id,
                TenantWhatsAppTemplate.template_key == template_key,
                TenantWhatsAppTemplate.status != "disabled",
            )
        )
        if template is None:
            raise ValueError("WhatsApp template not found")
        return template

    def get_owned(self, tenant_id: str, template_id: str) -> TenantWhatsAppTemplate:
        template = self.db.scalar(
            select(TenantWhatsAppTemplate).where(
                TenantWhatsAppTemplate.tenant_id == tenant_id,
                TenantWhatsAppTemplate.id == template_id,
            )
        )
        if template is None:
            raise ValueError("WhatsApp template not found")
        return template

    def render_template(self, template: TenantWhatsAppTemplate, variables: dict[str, Any]) -> str:
        return _render_text(template.body, variables)

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
        if template.parameter_format == "NAMED":
            keys = (template.components_json or {}).get("variable_keys")
            return list(keys) if isinstance(keys, list) else []
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

    def variables_payload(self, template: TenantWhatsAppTemplate) -> dict[str, Any]:
        """Wire-format representation of a template's variable keys, unified across
        POSITIONAL (meta_sync) and NAMED (tenant_authored) templates so existing
        consumers (e.g. the notification rule builder) keep reading `variables.parameters`."""
        try:
            keys = self.get_approved_parameter_keys(template)
        except ValueError:
            return template.variables_json or {}
        return {"parameters": [{"key": key, "label": f"Variable {key}"} for key in keys]}

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
        if template.parameter_format == "NAMED":
            return [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "parameter_name": key, "text": str(variables[key])} for key in keys
                    ],
                }
            ]
        return [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": str(variables[key])} for key in keys],
            }
        ]

    def create_draft(
        self,
        tenant_id: str,
        request: WhatsAppTemplateCreateRequest,
        created_by_user_id: str | None,
    ) -> TenantWhatsAppTemplate:
        template_key = request.template_key.strip()
        if not template_key:
            raise ValueError("template_key is required")
        category = request.category.strip().lower()
        if category not in _ALLOWED_CATEGORIES:
            raise ValueError("category must be one of marketing, utility, authentication")
        existing = self.db.scalar(
            select(TenantWhatsAppTemplate).where(
                TenantWhatsAppTemplate.tenant_id == tenant_id,
                TenantWhatsAppTemplate.template_key == template_key,
            )
        )
        if existing is not None:
            raise ValueError(f"A template with key '{template_key}' already exists")

        buttons = [button.model_dump(exclude_none=True) for button in request.buttons]
        _ensure_voice_call_allowed(self.db, tenant_id, buttons)
        components = _build_meta_components(
            header_text=request.header_text, body=request.body, footer_text=request.footer_text, buttons=buttons
        )
        variable_keys = _extract_named_variable_keys(request.header_text, request.body, request.footer_text)

        template = TenantWhatsAppTemplate(
            tenant_id=tenant_id,
            template_key=template_key,
            provider_template_name=template_key,
            name=request.name.strip(),
            category=category,
            language=request.language,
            body=request.body,
            status="draft",
            source="tenant_authored",
            parameter_format="NAMED",
            header_json={"text": request.header_text} if request.header_text else None,
            footer_text=request.footer_text,
            buttons_json=buttons,
            components_json={"components": components, "variable_keys": variable_keys},
            created_by_user_id=created_by_user_id,
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    def update_draft(
        self,
        tenant_id: str,
        template_id: str,
        request: WhatsAppTemplateUpdateRequest,
    ) -> TenantWhatsAppTemplate:
        template = self.get_owned(tenant_id, template_id)
        if template.status not in ("draft", "rejected"):
            raise ValueError("Only draft or rejected templates can be edited; submit a resend instead")

        if request.name is not None:
            template.name = request.name.strip()
        header_text = (
            request.header_text if request.header_text is not None else (template.header_json or {}).get("text")
        )
        body = request.body if request.body is not None else template.body
        footer_text = request.footer_text if request.footer_text is not None else template.footer_text
        buttons = (
            [button.model_dump(exclude_none=True) for button in request.buttons]
            if request.buttons is not None
            else (template.buttons_json or [])
        )
        _ensure_voice_call_allowed(self.db, tenant_id, buttons)

        template.body = body
        template.header_json = {"text": header_text} if header_text else None
        template.footer_text = footer_text
        template.buttons_json = buttons
        components = _build_meta_components(
            header_text=header_text, body=body, footer_text=footer_text, buttons=buttons
        )
        template.components_json = {
            "components": components,
            "variable_keys": _extract_named_variable_keys(header_text, body, footer_text),
        }
        self.db.commit()
        self.db.refresh(template)
        return template

    def delete_draft(self, tenant_id: str, template_id: str) -> None:
        template = self.get_owned(tenant_id, template_id)
        if template.status == "draft":
            referenced = self.db.scalar(
                select(CrmWhatsAppMessage.id).where(CrmWhatsAppMessage.template_id == template.id).limit(1)
            )
            if referenced is not None:
                raise ValueError("Cannot delete a template that has already been used to send messages")
            self.db.delete(template)
        else:
            template.status = "disabled"
        self.db.commit()

    def preview(self, tenant_id: str, template_id: str) -> dict[str, Any]:
        template = self.get_owned(tenant_id, template_id)
        if template.parameter_format == "NAMED":
            keys = (template.components_json or {}).get("variable_keys") or []
        else:
            try:
                keys = self.get_approved_parameter_keys(template)
            except ValueError:
                keys = []
        sample_variables = {key: f"[{key}]" for key in keys}
        header_text = (template.header_json or {}).get("text")
        return {
            "header_text": _render_text(header_text, sample_variables) if header_text else None,
            "body": _render_text(template.body, sample_variables),
            "footer_text": (
                _render_text(template.footer_text, sample_variables) if template.footer_text else None
            ),
            "buttons": template.buttons_json or [],
            "variables": sample_variables,
        }
