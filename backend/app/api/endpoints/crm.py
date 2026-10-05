"""CRM aggregator endpoints under ``/api/v1/crm``.

These compose several bounded contexts (Scheduling bookings, WhatsApp/email
actions, call summary = CRM + Analytics + Integrations, the aggregated dashboard)
and therefore stay outside the CRM module. They read and write CRM only through
``crm.public``. The pure CRM endpoints live in ``app.modules.crm.api.router``.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.db.session import get_db
from app.modules.crm.public import CrmFacade, LeadProfile
from app.modules.scheduling.public import (
    BookingOperationInProgressError,
    CreateBookingCommand,
    IdempotencyConflictError,
    SchedulingFacade,
    SlotConflictError,
)
from app.schemas.crm import (
    BookingCreateRequest,
    BookingRescheduleRequest,
    BookingResponse,
    CallSummaryAssetRequest,
    CallSummaryAssetResponse,
    CallSummaryInsertedRequest,
    CallSummaryResponse,
    CrmDashboardResponse,
    EmailActionRequest,
    EmailActionResponse,
)
from app.services.call_summary_service import CallSummaryService
from app.services.crm_dashboard_metrics_service import CrmDashboardMetricsService
from app.modules.integrations.application.email.send_service import EmailSendService

_BOOKING_CONFLICTS = (SlotConflictError, IdempotencyConflictError, BookingOperationInProgressError)

router = APIRouter(prefix="/api/v1/crm", tags=["CRM"])


@router.post("/leads/{lead_id}/bookings", response_model=BookingResponse)
def create_lead_booking(
    lead_id: str,
    body: BookingCreateRequest,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    try:
        return SchedulingFacade(db).create_booking(
            tenant_id=context.tenant.id,
            lead_id=lead_id,
            command=CreateBookingCommand(**body.model_dump()),
            idempotency_key=idempotency_key,
        )
    except _BOOKING_CONFLICTS as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/leads/{lead_id}/bookings/{booking_id}/cancel", response_model=dict)
def cancel_lead_booking(
    lead_id: str,
    booking_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return SchedulingFacade(db).cancel_booking(tenant_id=context.tenant.id, booking_id=booking_id)
    except HTTPException:
        raise
    except _BOOKING_CONFLICTS as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/leads/{lead_id}/bookings/{booking_id}/reschedule", response_model=dict)
def reschedule_lead_booking(
    lead_id: str,
    booking_id: str,
    body: BookingRescheduleRequest,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return SchedulingFacade(db).reschedule_booking(
            tenant_id=context.tenant.id,
            booking_id=booking_id,
            new_start_time=body.new_start_time,
        )
    except HTTPException:
        raise
    except _BOOKING_CONFLICTS as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# --- Outbound Actions ---

def _get_action_lead_or_404(db: Session, tenant_id: str, lead_id: str) -> LeadProfile:
    lead = CrmFacade(db).get_lead_profile(tenant_id, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


def _require_contact_phone(lead: LeadProfile, detail: str) -> None:
    if not lead.contact or not (lead.contact.phone or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


def _require_contact_email(lead: LeadProfile) -> None:
    if not lead.contact or not (lead.contact.email or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Lead does not have an email address.",
        )


def _require_contact_name(lead: LeadProfile) -> None:
    contact_name = (lead.contact.name or "").strip() if lead.contact else ""
    if not contact_name or contact_name.lower() == "lead sin nombre":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Lead does not have a contact name.",
        )


@router.post("/leads/{lead_id}/actions/whatsapp", response_model=dict)
def lead_action_whatsapp(
    lead_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    lead = _get_action_lead_or_404(db, tenant_id, lead_id)
    _require_contact_phone(lead, "Lead does not have a phone number for WhatsApp.")

    # Log action request activity
    CrmFacade(db).record_activity(
        tenant_id=tenant_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        activity_type="whatsapp_action_requested",
        title="WhatsApp enviado (Intento)",
        description="El usuario intentó enviar un mensaje de WhatsApp desde el CRM.",
    )

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="WhatsApp integration is not configured for this tenant. Please contact support to set up Twilio/Meta API.",
    )





@router.post("/leads/{lead_id}/actions/schedule", response_model=dict)
def lead_action_schedule(
    lead_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    lead = _get_action_lead_or_404(db, tenant_id, lead_id)
    _require_contact_name(lead)

    # Log action request activity
    CrmFacade(db).record_activity(
        tenant_id=tenant_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        activity_type="schedule_requested",
        title="Agendamiento de reunión (Intento)",
        description="El usuario intentó agendar una reunión desde el CRM.",
    )

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Cal.com/Google Calendar integration is not configured for this tenant. Please connect your calendar in settings.",
    )


@router.post("/leads/{lead_id}/actions/chatwoot", response_model=dict)
def lead_action_chatwoot(
    lead_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    lead = _get_action_lead_or_404(db, tenant_id, lead_id)

    CrmFacade(db).record_activity(
        tenant_id=tenant_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        activity_type="chatwoot_action_requested",
        title="Apertura Chatwoot solicitada",
        description="El usuario intento abrir o asociar una conversacion de Chatwoot desde el CRM.",
    )

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Chatwoot integration is not configured or this lead has no associated Chatwoot conversation.",
    )


@router.post("/leads/{lead_id}/actions/email", response_model=EmailActionResponse)
def lead_action_email(
    lead_id: str,
    body: EmailActionRequest | None = None,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    body = body or EmailActionRequest()
    service = EmailSendService(db)
    try:
        if body.preview_only:
            result = service.preview_lead_email(
                tenant_id=tenant_id,
                lead_id=lead_id,
                template_key=body.template_key,
                subject=body.subject,
                message=body.message,
                content_format=body.content_format,
                content=body.content,
                asset_ids=body.asset_ids,
                form_token_ids=body.form_token_ids,
            )
        else:
            result = service.send_lead_email(
                tenant_id=tenant_id,
                lead_id=lead_id,
                template_key=body.template_key,
                subject=body.subject,
                message=body.message,
                content_format=body.content_format,
                content=body.content,
                asset_ids=body.asset_ids,
                form_token_ids=body.form_token_ids,
            )
    except ValueError as exc:
        code = status.HTTP_404_NOT_FOUND if str(exc) == "Lead not found" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error_message or "Email send failed.")
    return EmailActionResponse(
        status=result.status,
        email_send_id=result.email_send_id,
        provider_email_id=result.provider_email_id,
        preview=result.preview,
    )


@router.get("/leads/{lead_id}/call-summary", response_model=CallSummaryResponse)
def get_lead_call_summary(
    lead_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    try:
        result = CallSummaryService(db).get_summary(context.tenant.id, lead_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return CallSummaryResponse(
        status=result.status,
        summary=result.summary,
        short_summary=result.short_summary,
        call_date=result.call_date,
        duration_seconds=result.duration_seconds,
        source=result.source,
    )


@router.post("/leads/{lead_id}/call-summary/inserted", status_code=status.HTTP_204_NO_CONTENT)
def record_lead_call_summary_inserted(
    lead_id: str,
    body: CallSummaryInsertedRequest | None = None,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> None:
    try:
        CallSummaryService(db).record_inserted(context.tenant.id, lead_id, (body or CallSummaryInsertedRequest()).variant)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/leads/{lead_id}/call-summary/asset", response_model=CallSummaryAssetResponse)
def create_lead_call_summary_asset(
    lead_id: str,
    body: CallSummaryAssetRequest,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    try:
        asset = CallSummaryService(db).create_summary_asset(
            tenant_id=context.tenant.id,
            lead_id=lead_id,
            uploaded_by_user_id=context.user.id,
            file_format=body.format,
        )
    except ValueError as exc:
        code = status.HTTP_404_NOT_FOUND if str(exc) == "Lead not found" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return CallSummaryAssetResponse(
        asset_id=asset.id,
        filename=asset.original_filename,
        mime_type=asset.mime_type,
        file_size_bytes=asset.file_size_bytes,
    )


# --- Dashboard ---

@router.get("/dashboard", response_model=CrmDashboardResponse)
def get_crm_dashboard(
    range: Optional[str] = Query(default="30d"),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    campaign: Optional[str] = Query(default=None),
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    if range == "custom" and (not date_from or not date_to):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="range=custom requires both date_from and date_to parameters",
        )

    metrics_service = CrmDashboardMetricsService(db)
    dashboard_data = metrics_service.get_dashboard(
        tenant=context.tenant,
        range_val=range,
        date_from_str=date_from,
        date_to_str=date_to,
        source=source,
        campaign=campaign,
    )
    return dashboard_data
