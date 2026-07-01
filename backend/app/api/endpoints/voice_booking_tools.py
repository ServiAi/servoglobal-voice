from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.crm import BookingCreateRequest, VoiceAvailabilityRequest, VoiceBookingRequest
from app.services.booking_service import BookingService
from app.services.voice_booking_context_service import VoiceBookingContextService

router = APIRouter(prefix="/api/v1/voice/tools", tags=["Voice Booking Tools"])


@router.post("/availability")
def voice_availability(body: VoiceAvailabilityRequest, db: Session = Depends(get_db)) -> Any:
    try:
        context = VoiceBookingContextService(db).resolve(
            call_context_id=body.call_context_id,
            agent_id=body.agent_id,
            did=body.did,
        )
        return BookingService(db).get_available_slots_for_tenant(
            tenant_id=context.tenant_id,
            date_input=body.date,
            jornada=body.jornada,
            reference_datetime=body.reference_datetime,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/bookings")
def voice_booking(body: VoiceBookingRequest, db: Session = Depends(get_db)) -> Any:
    try:
        context = VoiceBookingContextService(db).resolve(
            call_context_id=body.call_context_id,
            agent_id=body.agent_id,
            did=body.did,
        )
        if not context.lead_id:
            raise ValueError("Unable to resolve lead for voice booking tool.")
        booking = BookingService(db).create_lead_booking(
            tenant_id=context.tenant_id,
            lead_id=context.lead_id,
            body=BookingCreateRequest(
                start=body.start,
                attendee_name=body.attendee_name,
                attendee_email=body.attendee_email,
                attendee_phone=body.attendee_phone,
                booking_fields_responses={"source": "voice"},
                notes="Reserva creada desde agente de voz",
            ),
        )
        return {
            "status": booking.status,
            "booking_id": booking.id,
            "summary": f"Reserva creada para {booking.attendee_name}.",
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
