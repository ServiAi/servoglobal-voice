from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.crm import CrmLead
from app.models.integrations import (
    TenantForm,
    TenantFormField,
    TenantFormSubmission,
    TenantFormSubmissionAnswer,
    TenantFormToken,
)
from app.schemas.forms import FormCreateRequest
from app.services.crm_activity_service import CrmActivityService
from app.services.integration_event_service import IntegrationEventService


FIELD_TYPES = {"text", "email", "phone", "textarea", "select", "checkbox"}
DEFAULT_FIELDS = [
    ("nombre", "Nombre", "text", True),
    ("empresa", "Empresa", "text", False),
    ("telefono", "Telefono", "phone", False),
    ("correo", "Correo", "email", False),
    ("necesidad_principal", "Necesidad principal", "textarea", True),
    ("presupuesto_estimado", "Presupuesto estimado", "text", False),
    ("comentarios", "Comentarios", "textarea", False),
]


class FormService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.activity_service = CrmActivityService(db)
        self.event_service = IntegrationEventService(db)

    def list_forms(self, tenant_id: str) -> list[TenantForm]:
        self.ensure_default_form(tenant_id)
        return list(
            self.db.scalars(
                select(TenantForm)
                .options(joinedload(TenantForm.fields))
                .where(TenantForm.tenant_id == tenant_id)
                .order_by(TenantForm.created_at.desc())
            )
            .unique()
            .all()
        )

    def get_form(self, tenant_id: str, form_id: str) -> TenantForm:
        form = self.db.scalar(
            select(TenantForm)
            .options(joinedload(TenantForm.fields))
            .where(TenantForm.tenant_id == tenant_id, TenantForm.id == form_id)
        )
        if form is None:
            raise ValueError("Form not found")
        return form

    def create_form(self, tenant_id: str, body: FormCreateRequest) -> TenantForm:
        fields = body.fields or [
            {"key": key, "label": label, "field_type": field_type, "required": required, "position": index}
            for index, (key, label, field_type, required) in enumerate(DEFAULT_FIELDS)
        ]
        form = TenantForm(
            tenant_id=tenant_id,
            name=body.name,
            description=body.description,
            status=body.status,
        )
        self.db.add(form)
        self.db.flush()
        for index, item in enumerate(fields):
            data = item.model_dump() if hasattr(item, "model_dump") else item
            field_type = data["field_type"]
            if field_type not in FIELD_TYPES:
                raise ValueError("Unsupported form field type.")
            self.db.add(
                TenantFormField(
                    tenant_id=tenant_id,
                    form_id=form.id,
                    key=data["key"],
                    label=data["label"],
                    field_type=field_type,
                    required=data["required"],
                    options_json=data.get("options", []),
                    position=data.get("position", index),
                )
            )
        self.db.commit()
        return self.get_form(tenant_id, form.id)

    def ensure_default_form(self, tenant_id: str) -> TenantForm:
        existing = self.db.scalar(select(TenantForm).where(TenantForm.tenant_id == tenant_id))
        if existing:
            return existing
        return self.create_form(
            tenant_id,
            FormCreateRequest(
                name="Diagnostico comercial",
                description="Formulario inicial para calificar oportunidades comerciales.",
            ),
        )

    def create_token(self, tenant_id: str, form_id: str, lead_id: str, expires_in_days: int) -> tuple[TenantFormToken, str]:
        form = self.get_form(tenant_id, form_id)
        if form.status != "active":
            raise ValueError("Form is not active.")
        lead = self._get_lead(tenant_id, lead_id)
        token = secrets.token_urlsafe(32)
        form_token = TenantFormToken(
            tenant_id=tenant_id,
            form_id=form.id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            token_hash=self._hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
            status="active",
        )
        self.db.add(form_token)
        self.db.commit()
        self.db.refresh(form_token)
        return form_token, self._public_link(token)

    def load_public_form(self, token: str) -> tuple[TenantFormToken, TenantForm]:
        form_token = self._get_valid_token(token, mark_opened=True)
        form = self.get_form(form_token.tenant_id, form_token.form_id)
        return form_token, form

    def submit_public_form(self, token: str, answers: dict[str, str | bool | None], hp: str | None = None) -> TenantFormSubmission:
        if hp:
            raise ValueError("Invalid submission.")
        form_token = self._get_valid_token(token)
        form = self.get_form(form_token.tenant_id, form_token.form_id)
        field_map = {field.key: field for field in form.fields}
        for field in form.fields:
            if field.required and not str(answers.get(field.key) or "").strip():
                raise ValueError(f"Field {field.key} is required.")
        submission = TenantFormSubmission(
            tenant_id=form_token.tenant_id,
            form_id=form.id,
            lead_id=form_token.lead_id,
            contact_id=form_token.contact_id,
            token_id=form_token.id,
            status="submitted",
            metadata_json={"field_count": len(answers)},
        )
        self.db.add(submission)
        self.db.flush()
        for key, value in answers.items():
            field = field_map.get(key)
            if not field:
                continue
            self.db.add(
                TenantFormSubmissionAnswer(
                    tenant_id=form_token.tenant_id,
                    submission_id=submission.id,
                    field_id=field.id,
                    field_key=field.key,
                    value_text=str(value) if value is not None else None,
                )
            )
        form_token.status = "used"
        form_token.used_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(submission)
        self.activity_service.create_activity(
            tenant_id=form_token.tenant_id,
            lead_id=form_token.lead_id,
            contact_id=form_token.contact_id,
            activity_type="form_submitted",
            title="Formulario enviado",
            payload_json={"form_id": form.id, "submission_id": submission.id},
        )
        self.event_service.record_event(
            tenant_id=form_token.tenant_id,
            provider="forms",
            event_type="form_submitted",
            status="success",
            resource_type="form_submission",
            resource_id=submission.id,
            metadata={"form_id": form.id},
        )
        return submission

    def _get_valid_token(self, token: str, mark_opened: bool = False) -> TenantFormToken:
        form_token = self.db.scalar(
            select(TenantFormToken).where(TenantFormToken.token_hash == self._hash_token(token))
        )
        if form_token is None:
            raise ValueError("Form link is invalid or expired.")
        expires_at = form_token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if form_token.status != "active" or expires_at <= datetime.now(UTC):
            raise ValueError("Form link is invalid or expired.")
        if mark_opened:
            self.activity_service.create_activity(
                tenant_id=form_token.tenant_id,
                lead_id=form_token.lead_id,
                contact_id=form_token.contact_id,
                activity_type="form_opened",
                title="Formulario abierto",
                payload_json={"form_id": form_token.form_id},
            )
        return form_token

    def _get_lead(self, tenant_id: str, lead_id: str) -> CrmLead:
        lead = self.db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant_id, CrmLead.id == lead_id))
        if lead is None:
            raise ValueError("Lead not found")
        return lead

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _public_link(self, token: str) -> str:
        return f"{settings.PUBLIC_FORM_BASE_URL.rstrip('/')}/es/forms/public/{token}"
