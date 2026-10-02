"""Cal.com HTTP endpoints: the env-configured public availability/booking
helpers and the native webhook. The webhook authenticates and parses; applying
it to the booking is Scheduling's (``reconcile_calcom_webhook``) and the
announcement of the booking fact goes through the booking-event port."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.scheduling.application.calcom_webhook import (
    CALCOM_TRIGGER_TO_BOOKING_EVENT,
    reconcile_calcom_webhook,
)
from app.modules.scheduling.infrastructure.calcom.availability import (
    CalComConfigurationError,
    CalComInputError,
    CalComUpstreamError,
    SlotUnavailableError,
    create_booking,
    get_available_slots,
)
from app.modules.scheduling.wiring import run_booking_event_task

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
        booking = reconcile_calcom_webhook(db, trigger_event, payload)

        domain_event_type = CALCOM_TRIGGER_TO_BOOKING_EVENT.get(trigger_event or "")
        if booking is None:
            return {"status": "ignored", "reason": "booking_unreconciled"}
        if domain_event_type is None:
            return {"status": "ignored", "reason": "not_booking_created"}

        background_tasks.add_task(
            run_booking_event_task,
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
