from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.analytics import Call
from app.models.crm import CrmActivity, CrmCallContext, CrmLead
from app.models.identity import Tenant
from app.models.integrations import TenantEmailAsset
from app.services.crm_activity_service import CrmActivityService
from app.services.storage_service import StorageService


@dataclass(frozen=True)
class CallSummaryResult:
    status: str
    summary: str | None = None
    short_summary: str | None = None
    call_date: datetime | None = None
    duration_seconds: int | None = None
    source: str | None = None

    @property
    def available(self) -> bool:
        return self.status == "available"


class CallSummaryService:
    def __init__(self, db: Session, storage: StorageService | None = None) -> None:
        self.db = db
        self.storage = storage or StorageService()

    def get_lead(self, tenant_id: str, lead_id: str) -> CrmLead:
        lead = self.db.scalar(
            select(CrmLead)
            .options(joinedload(CrmLead.contact))
            .where(CrmLead.tenant_id == tenant_id, CrmLead.id == lead_id)
        )
        if lead is None:
            raise ValueError("Lead not found")
        return lead

    def get_summary(self, tenant_id: str, lead_id: str) -> CallSummaryResult:
        lead = self.get_lead(tenant_id, lead_id)
        return (
            self._from_latest_activity(tenant_id, lead_id)
            or self._from_last_call(tenant_id, lead)
            or self._from_call_context(tenant_id, lead)
            or self._from_lead(lead)
            or CallSummaryResult(status="not_found")
        )

    def variables_for_lead(self, tenant_id: str, lead_id: str) -> dict[str, str]:
        result = self.get_summary(tenant_id, lead_id)
        if not result.available:
            return {
                "call_summary": "",
                "call_summary_short": "",
                "last_call_date": "",
                "call_duration_seconds": "",
            }
        return {
            "call_summary": result.summary or "",
            "call_summary_short": result.short_summary or result.summary or "",
            "last_call_date": result.call_date.isoformat() if result.call_date else "",
            "call_duration_seconds": str(result.duration_seconds or ""),
        }

    def create_summary_asset(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        uploaded_by_user_id: str | None,
        file_format: str,
    ) -> TenantEmailAsset:
        lead = self.get_lead(tenant_id, lead_id)
        result = self.get_summary(tenant_id, lead_id)
        if not result.available or not result.summary:
            raise ValueError("Call summary is not available for this lead.")
        tenant = self.db.get(Tenant, tenant_id)
        if tenant is None:
            raise ValueError("Tenant not found")
        fmt = file_format.lower().strip()
        if fmt not in {"md", "txt"}:
            raise ValueError("Unsupported call summary asset format.")
        content = self._render_asset_content(lead, result, fmt).encode("utf-8")
        filename = f"resumen-llamada-{lead_id}.{fmt}"
        mime_type = "text/markdown" if fmt == "md" else "text/plain"
        asset = TenantEmailAsset(
            tenant_id=tenant_id,
            uploaded_by_user_id=uploaded_by_user_id,
            original_filename=filename,
            storage_key="pending",
            mime_type=mime_type,
            file_size_bytes=len(content),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
            visibility="private",
            status="uploaded",
        )
        self.db.add(asset)
        self.db.flush()
        storage_key = self.storage.tenant_object_key(tenant.slug, "resumenes-llamada", asset.id, filename)
        self.storage.upload_bytes(storage_key, content)
        asset.storage_key = storage_key
        self.db.commit()
        self.db.refresh(asset)
        CrmActivityService(self.db).create_activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            activity_type="call_summary_attached_to_email",
            title="Resumen de llamada adjuntado",
            payload_json={"email_asset_id": asset.id, "format": fmt},
        )
        return asset

    def record_inserted(self, tenant_id: str, lead_id: str, variant: str) -> None:
        lead = self.get_lead(tenant_id, lead_id)
        CrmActivityService(self.db).create_activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            activity_type="call_summary_inserted_in_email",
            title="Resumen de llamada insertado",
            payload_json={"variant": variant if variant in {"full", "short"} else "full"},
        )

    def _from_latest_activity(self, tenant_id: str, lead_id: str) -> CallSummaryResult | None:
        activities = self.db.scalars(
            select(CrmActivity)
            .where(CrmActivity.tenant_id == tenant_id, CrmActivity.lead_id == lead_id)
            .order_by(CrmActivity.occurred_at.desc())
        ).all()
        for activity in activities:
            payload = activity.payload_json or {}
            call = payload.get("call") if isinstance(payload.get("call"), dict) else {}
            summary = self._string(call.get("summary") or payload.get("summary"))
            short_summary = self._string(
                call.get("shortSummary")
                or call.get("short_summary")
                or payload.get("shortSummary")
                or payload.get("short_summary")
            )
            if summary or short_summary:
                return CallSummaryResult(
                    status="available",
                    summary=summary or short_summary,
                    short_summary=short_summary or summary,
                    call_date=activity.occurred_at,
                    duration_seconds=self._int(
                        call.get("durationSeconds") or call.get("duration_seconds") or payload.get("duration_seconds")
                    ),
                    source="crm_activity",
                )
        return None

    def _from_last_call(self, tenant_id: str, lead: CrmLead) -> CallSummaryResult | None:
        call_ids = [value for value in (lead.last_call_id, lead.created_from_call_id) if value]
        if not call_ids:
            return None
        call = self.db.scalar(
            select(Call)
            .where(Call.tenant_id == tenant_id, Call.id.in_(call_ids))
            .order_by(Call.ended_at.desc().nullslast(), Call.started_at.desc().nullslast())
            .limit(1)
        )
        if call is None or not (call.summary or call.short_summary):
            return None
        return CallSummaryResult(
            status="available",
            summary=call.summary or call.short_summary,
            short_summary=call.short_summary or call.summary,
            call_date=call.ended_at or call.started_at,
            duration_seconds=call.duration_seconds,
            source="call",
        )

    def _from_call_context(self, tenant_id: str, lead: CrmLead) -> CallSummaryResult | None:
        if not lead.context_id:
            return None
        context = self.db.scalar(
            select(CrmCallContext)
            .where(
                CrmCallContext.tenant_id == tenant_id,
                or_(CrmCallContext.id == lead.context_id, CrmCallContext.context_id == lead.context_id),
            )
            .order_by(CrmCallContext.created_at.desc())
            .limit(1)
        )
        if context is None:
            return None
        raw = context.raw_context_json or {}
        summary = self._string(raw.get("summary") or raw.get("call_summary"))
        short_summary = self._string(raw.get("short_summary") or raw.get("shortSummary") or raw.get("call_summary_short"))
        if not (summary or short_summary):
            return None
        return CallSummaryResult(
            status="available",
            summary=summary or short_summary,
            short_summary=short_summary or summary,
            call_date=context.created_at,
            duration_seconds=self._int(raw.get("duration_seconds") or raw.get("durationSeconds")),
            source="crm_call_context",
        )

    def _from_lead(self, lead: CrmLead) -> CallSummaryResult | None:
        if not (lead.summary or lead.short_summary):
            return None
        return CallSummaryResult(
            status="available",
            summary=lead.summary or lead.short_summary,
            short_summary=lead.short_summary or lead.summary,
            call_date=lead.updated_at,
            duration_seconds=None,
            source="crm_lead",
        )

    def _render_asset_content(self, lead: CrmLead, result: CallSummaryResult, fmt: str) -> str:
        contact = lead.contact
        values = {
            "Lead": contact.name if contact else "",
            "Correo": contact.email if contact else "",
            "Empresa": contact.company if contact else "",
            "Fecha de llamada": result.call_date.isoformat() if result.call_date else "",
            "Duracion": str(result.duration_seconds or ""),
        }
        if fmt == "txt":
            header = "\n".join(f"{key}: {value}" for key, value in values.items() if value)
            return (
                "Resumen de llamada\n\n"
                f"{header}\n\n"
                f"Resumen\n{result.summary or ''}\n\n"
                f"Dolor principal\n{lead.pain_point or ''}\n\n"
                f"Interes\n{lead.interest or ''}\n\n"
                f"Caso de uso\n{lead.use_case or ''}\n"
            )
        header = "\n".join(f"**{key}:** {value}  " for key, value in values.items() if value)
        return (
            "# Resumen de llamada\n\n"
            f"{header}\n\n"
            "## Resumen\n\n"
            f"{result.summary or ''}\n\n"
            "## Dolor principal\n\n"
            f"{lead.pain_point or ''}\n\n"
            "## Interes\n\n"
            f"{lead.interest or ''}\n\n"
            "## Caso de uso\n\n"
            f"{lead.use_case or ''}\n"
        )

    def _string(self, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    def _int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value if not isinstance(value, Decimal) else float(value))
        except (TypeError, ValueError):
            return None
