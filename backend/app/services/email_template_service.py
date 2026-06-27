from __future__ import annotations

import html
from dataclasses import dataclass
from string import Template

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import CrmLead
from app.models.integrations import TenantEmailTemplate

ALLOWED_VARIABLES = [
    "contact_name",
    "contact_email",
    "company",
    "interest",
    "industry",
    "use_case",
    "volume",
    "pain_point",
    "source",
    "campaign",
    "lead_id",
    "message",
]

DEFAULT_TEMPLATES = {
    "lead_proposal": {
        "name": "Propuesta comercial",
        "subject": "Propuesta comercial ServiGlobal IA",
        "category": "proposal",
        "html_body": "<p>Hola ${contact_name},</p><p>${message}</p><p>Quedo atento.</p>",
        "text_body": "Hola ${contact_name},\n\n${message}\n\nQuedo atento.",
    },
    "call_summary": {
        "name": "Resumen de llamada",
        "subject": "Resumen de nuestra conversacion",
        "category": "call_summary",
        "html_body": "<p>Hola ${contact_name},</p><p>${message}</p><p>Resumen: ${pain_point}</p>",
        "text_body": "Hola ${contact_name},\n\n${message}\n\nResumen: ${pain_point}",
    },
    "lead_follow_up": {
        "name": "Seguimiento comercial",
        "subject": "Seguimiento ServiGlobal IA",
        "category": "follow_up",
        "html_body": "<p>Hola ${contact_name},</p><p>${message}</p><p>Interes registrado: ${interest}</p>",
        "text_body": "Hola ${contact_name},\n\n${message}\n\nInteres registrado: ${interest}",
    },
}


@dataclass(frozen=True)
class RenderedEmailTemplate:
    template: TenantEmailTemplate
    subject: str
    html: str
    text: str


class EmailTemplateService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_default_templates(self, tenant_id: str) -> list[TenantEmailTemplate]:
        existing = {
            template.template_key: template
            for template in self.db.scalars(
                select(TenantEmailTemplate).where(TenantEmailTemplate.tenant_id == tenant_id)
            ).all()
        }
        for key, values in DEFAULT_TEMPLATES.items():
            if key not in existing:
                self.db.add(
                    TenantEmailTemplate(
                        tenant_id=tenant_id,
                        template_key=key,
                        name=values["name"],
                        subject=values["subject"],
                        html_body=values["html_body"],
                        text_body=values["text_body"],
                        variables_schema={"allowed": ALLOWED_VARIABLES},
                        category=values["category"],
                        status="active",
                        is_marketing=False,
                    )
                )
        self.db.commit()
        return self.list_templates(tenant_id)

    def list_templates(self, tenant_id: str) -> list[TenantEmailTemplate]:
        return list(
            self.db.scalars(
                select(TenantEmailTemplate)
                .where(TenantEmailTemplate.tenant_id == tenant_id)
                .order_by(TenantEmailTemplate.template_key.asc())
            ).all()
        )

    def get_template(self, tenant_id: str, template_key: str) -> TenantEmailTemplate:
        self.ensure_default_templates(tenant_id)
        template = self.db.scalar(
            select(TenantEmailTemplate).where(
                TenantEmailTemplate.tenant_id == tenant_id,
                TenantEmailTemplate.template_key == template_key,
                TenantEmailTemplate.status == "active",
            )
        )
        if template is None:
            raise ValueError("Email template is not available.")
        return template

    def render_template(
        self,
        *,
        tenant_id: str,
        template_key: str,
        lead: CrmLead,
        variables: dict | None = None,
        subject_override: str | None = None,
        message_override: str | None = None,
    ) -> RenderedEmailTemplate:
        template = self.get_template(tenant_id, template_key)
        context = self._lead_context(lead)
        context.update({k: str(v or "") for k, v in (variables or {}).items() if k in ALLOWED_VARIABLES})
        if message_override is not None:
            context["message"] = message_override.strip()
        safe_html_context = {key: html.escape(value) for key, value in context.items()}
        subject = (subject_override or template.subject).strip()
        return RenderedEmailTemplate(
            template=template,
            subject=Template(subject).safe_substitute(context),
            html=Template(template.html_body).safe_substitute(safe_html_context),
            text=Template(template.text_body).safe_substitute(context),
        )

    def _lead_context(self, lead: CrmLead) -> dict[str, str]:
        contact = lead.contact
        return {
            "contact_name": (contact.name if contact else "") or "",
            "contact_email": (contact.email if contact else "") or "",
            "company": (contact.company if contact else "") or "",
            "interest": lead.interest or "",
            "industry": lead.industry or "",
            "use_case": lead.use_case or "",
            "volume": lead.volume or "",
            "pain_point": lead.pain_point or lead.summary or lead.short_summary or "",
            "source": lead.source or "",
            "campaign": lead.campaign or "",
            "lead_id": lead.id,
            "message": "",
        }
