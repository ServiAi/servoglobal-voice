from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, Header, status
from pydantic import BaseModel
import hmac
import hashlib
import os
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.crm import CrmBooking, CrmBookingEvent
from app.services.crm_activity_service import CrmActivityService
from app.services.notification_event_pipeline import run_booking_notification_pipeline_task
from app.services.calcom_service import (
    CalComConfigurationError,
    CalComInputError,
    CalComUpstreamError,
    SlotUnavailableError,
    get_available_slots,
    create_booking,
)
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Cal.com"])


class AvailabilityRequest(BaseModel):
    date: str  # Accepts "YYYY-MM-DD" or full ISO 8601 timestamp
    jornada: str | None = (
        None  # 'mañana' (09:00–11:30) | 'tarde' (12:00–16:30) | None = all
    )


class CreateBookingRequest(BaseModel):
    date_str: str
    time_str: str
    name: str
    email: str
    phone: str | None = None


@router.get("/availability")
async def check_availability_get(date: str, jornada: str | None = None):
    try:
        result = await get_available_slots(date, jornada)
        return result
    except CalComInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (CalComConfigurationError, CalComUpstreamError) as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error al consultar disponibilidad: {str(e)}"
        )


@router.post("/availability")
async def check_availability(request: AvailabilityRequest):
    try:
        result = await get_available_slots(request.date, request.jornada)
        return result
    except CalComInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (CalComConfigurationError, CalComUpstreamError) as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error al consultar disponibilidad: {str(e)}"
        )


@router.post("/bookings")
async def create_new_booking(request: CreateBookingRequest):
    try:
        result = await create_booking(
            date_str=request.date_str,
            time_str=request.time_str,
            name=request.name,
            email=request.email,
            phone=request.phone,
        )
        return result
    except SlotUnavailableError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except CalComInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (CalComConfigurationError, CalComUpstreamError) as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear reserva: {str(e)}")


# ── Webhook Nativo de Cal.com ────────────────────────────────────────────────

def _calcom_webhook_status(trigger_event: str | None, payload: dict) -> str:
    status_value = payload.get("status")
    if status_value:
        return str(status_value).lower()
    return {
        "BOOKING_CREATED": "accepted",
        "BOOKING_CANCELLED": "cancelled",
        "BOOKING_RESCHEDULED": "rescheduled",
    }.get(trigger_event or "", "updated")


def _safe_webhook_metadata(payload: dict) -> dict:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    return {
        "crm_booking_id": str(metadata.get("crm_booking_id") or ""),
        "crm_lead_id": str(metadata.get("crm_lead_id") or ""),
        "source": str(metadata.get("source") or ""),
    }


_CALCOM_TRIGGER_TO_DOMAIN_EVENT = {
    "BOOKING_CREATED": "booking.created",
    "BOOKING_CANCELLED": "booking.cancelled",
    "BOOKING_RESCHEDULED": "booking.rescheduled",
}


def _sync_crm_booking_from_calcom_webhook(
    db: Session, trigger_event: str | None, payload: dict
) -> CrmBooking | None:
    metadata = _safe_webhook_metadata(payload)
    if metadata.get("source") != "serviglobal_crm":
        return None

    crm_booking_id = metadata.get("crm_booking_id")
    if not crm_booking_id:
        return None

    booking = db.scalar(
        select(CrmBooking).where(
            CrmBooking.id == crm_booking_id,
            CrmBooking.provider == "calcom",
        )
    )
    if booking is None:
        return None

    crm_lead_id = metadata.get("crm_lead_id")
    if crm_lead_id and crm_lead_id != (booking.lead_id or ""):
        return None

    incoming_provider_id = str(payload.get("id") or "").strip()
    incoming_provider_uid = str(payload.get("uid") or payload.get("bookingUid") or "").strip()

    if (
        booking.provider_booking_id
        and incoming_provider_id
        and str(booking.provider_booking_id) != incoming_provider_id
    ):
        return None
    if (
        booking.provider_booking_uid
        and incoming_provider_uid
        and str(booking.provider_booking_uid) != incoming_provider_uid
    ):
        return None

    if trigger_event == "BOOKING_CANCELLED":
        booking.status = "cancelled"
    elif trigger_event == "BOOKING_RESCHEDULED":
        start_iso = payload.get("startTime")
        end_iso = payload.get("endTime")
        if start_iso:
            booking.start_at = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        if end_iso:
            booking.end_at = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        booking.status = _calcom_webhook_status(trigger_event, payload)
    elif trigger_event == "BOOKING_CREATED":
        booking.status = _calcom_webhook_status(trigger_event, payload)

    booking.provider_booking_id = incoming_provider_id or booking.provider_booking_id
    booking.provider_booking_uid = incoming_provider_uid or booking.provider_booking_uid
    booking.meeting_url = payload.get("meetingUrl") or payload.get("meeting_url") or payload.get("videoCallUrl") or booking.meeting_url

    safe_summary = {
        "trigger_event": trigger_event,
        "provider_booking_id": booking.provider_booking_id,
        "provider_booking_uid": booking.provider_booking_uid,
        "source": metadata.get("source"),
    }
    db.add(
        CrmBookingEvent(
            tenant_id=booking.tenant_id,
            booking_id=booking.id,
            provider="calcom",
            event_type=(trigger_event or "calcom_webhook").lower(),
            status=booking.status,
            payload_summary_json=safe_summary,
        )
    )
    db.commit()
    if booking.contact_id:
        CrmActivityService(db).create_activity(
            tenant_id=booking.tenant_id,
            lead_id=booking.lead_id,
            contact_id=booking.contact_id,
            activity_type="booking_webhook",
            title="Webhook Cal.com",
            description=f"Cal.com {trigger_event or 'webhook'}",
            payload_json=safe_summary,
        )
    return booking



@router.post("/calcom/webhook")
async def receive_calcom_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_cal_signature_256: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """
    Recibe el Webhook nativo desde Cal.com.
    Sincroniza la reserva del CRM y programa las notificaciones multiempresa en background.
    """
    # --- VALIDACIÓN CRIPTOGRÁFICA DE SEGURIDAD (Bypass BFM) ---
    calcom_secret = os.getenv("CALCOM_WEBHOOK_SECRET")
    
    if calcom_secret:
        if not x_cal_signature_256:
            logger.warning("[Cal.com] Rechazado: Falta la firma X-Cal-Signature-256")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing cryptographic signature"
            )

        raw_body = await request.body()
        expected_signature = hmac.new(
            key=calcom_secret.encode('utf-8'),
            msg=raw_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, x_cal_signature_256):
            logger.warning("[Cal.com] Rechazado: Firma HMAC de webhook inválida")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid signature integrity"
            )
    else:
        logger.warning("[Cal.com] SEGURO INACTIVO: CALCOM_WEBHOOK_SECRET no configurado en entorno.")

    try:
        payload_data = await request.json()
        trigger_event = payload_data.get("triggerEvent")
        logger.debug("[Cal.com] Webhook recibido trigger=%s", trigger_event)
        payload = payload_data.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        booking = _sync_crm_booking_from_calcom_webhook(db, trigger_event, payload)

        domain_event_type = _CALCOM_TRIGGER_TO_DOMAIN_EVENT.get(trigger_event or "")
        if booking is None:
            return {"status": "ignored", "reason": "booking_unreconciled"}
        if domain_event_type is None:
            return {"status": "ignored", "reason": "not_booking_created"}

        background_tasks.add_task(
            run_booking_notification_pipeline_task,
            tenant_id=booking.tenant_id,
            booking_id=booking.id,
            event_type=domain_event_type,
        )
        return {"status": "processing_notifications"}

    except Exception as exc:
        # Retornamos 200 igual para que Cal.com no reintente con errores de parseo.
        logger.error(
            "calcom_webhook_processing_error error_type=%s",
            type(exc).__name__,
        )
        return {
            "status": "error",
            "reason": "webhook_processing_failed",
        }
