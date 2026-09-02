from __future__ import annotations

import logging
from typing import Any

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.crm import CrmLead
from app.models.integrations import TenantVoiceAgentConfig
from app.schemas.crm import BookingCreateRequest, VoiceAvailabilityRequest, VoiceBookingRequest, VoiceHandoffRequest
from app.schemas.integrations import HANDOFF_TRIGGER_CUSTOMER_REQUEST
from app.services.booking_service import BookingService
from app.services.voice_booking_context_service import VoiceBookingContextService
from app.services.voice_handoff_service import VoiceHandoffService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice/tools", tags=["Voice Booking Tools"])


def require_voice_tool_secret(x_voice_tool_secret: str | None = Header(None)) -> None:
    if (
        not settings.VOICE_TOOL_SHARED_SECRET
        or not x_voice_tool_secret
        or not hmac.compare_digest(x_voice_tool_secret, settings.VOICE_TOOL_SHARED_SECRET)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid voice tool secret.")


async def _check_lead_score_handoff(db: Session, tenant_id: str, agent_id: str | None, lead_id: str | None) -> None:
    """Handoff automatico por lead_score alto, revisado en cada invocacion de
    una tool de voz (no hay analisis en vivo de la llamada fuera de estos
    puntos). Nunca debe interrumpir el flujo de la tool que lo invoca."""
    if not agent_id or not lead_id:
        return
    try:
        agent = db.scalar(
            select(TenantVoiceAgentConfig).where(
                TenantVoiceAgentConfig.tenant_id == tenant_id,
                TenantVoiceAgentConfig.provider_agent_id == agent_id,
            )
        )
        if agent is None or not agent.handoff_enabled:
            return
        lead = db.get(CrmLead, lead_id)
        if lead is None:
            return
        await VoiceHandoffService(db).maybe_handoff_for_lead_score(tenant_id, agent=agent, lead=lead)
    except Exception:
        logger.exception(
            "[VoiceHandoff] lead_score check failed tenant_id=%s agent_id=%s lead_id=%s",
            tenant_id,
            agent_id,
            lead_id,
        )


@router.post("/availability")
async def voice_availability(
    body: VoiceAvailabilityRequest,
    _: None = Depends(require_voice_tool_secret),
    db: Session = Depends(get_db),
) -> Any:
    try:
        context = VoiceBookingContextService(db).resolve(
            call_context_id=body.call_context_id,
            agent_id=body.agent_id,
            did=body.did,
        )
        result = BookingService(db).get_available_slots_for_tenant(
            tenant_id=context.tenant_id,
            date_input=body.date,
            jornada=body.jornada,
            reference_datetime=body.reference_datetime,
            booking_config_id=context.booking_config_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    await _check_lead_score_handoff(db, context.tenant_id, body.agent_id, context.lead_id)
    return result


@router.post("/bookings")
async def voice_booking(
    body: VoiceBookingRequest,
    _: None = Depends(require_voice_tool_secret),
    db: Session = Depends(get_db),
) -> Any:
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
            booking_config_id=context.booking_config_id,
        )
        result = {
            "status": booking.status,
            "booking_id": booking.id,
            "summary": f"Reserva creada para {booking.attendee_name}.",
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    await _check_lead_score_handoff(db, context.tenant_id, body.agent_id, context.lead_id)
    return result


@router.post("/request-human-handoff")
async def voice_request_human_handoff(
    body: VoiceHandoffRequest,
    _: None = Depends(require_voice_tool_secret),
    db: Session = Depends(get_db),
) -> Any:
    """Tool explicita que el agente de voz invoca cuando el cliente pide
    hablar con un humano. El system prompt del agente decide cuando llamarla;
    aqui solo se ejecuta el handoff si el tenant lo tiene habilitado."""
    try:
        context = VoiceBookingContextService(db).resolve(
            call_context_id=body.call_context_id,
            agent_id=body.agent_id,
            did=body.did,
        )
        if not context.lead_id:
            raise ValueError("Unable to resolve lead for voice handoff tool.")
        if not body.agent_id:
            raise ValueError("agent_id is required for voice handoff tool.")
        agent = db.scalar(
            select(TenantVoiceAgentConfig).where(
                TenantVoiceAgentConfig.tenant_id == context.tenant_id,
                TenantVoiceAgentConfig.provider_agent_id == body.agent_id,
            )
        )
        if agent is None:
            raise ValueError("Voice agent config not found for handoff tool.")
        lead = db.get(CrmLead, context.lead_id)
        if lead is None:
            raise ValueError("Lead not found for handoff tool.")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    result = await VoiceHandoffService(db).trigger_handoff(
        context.tenant_id, agent=agent, lead=lead, trigger=HANDOFF_TRIGGER_CUSTOMER_REQUEST
    )
    if result["status"] == "success":
        return {"status": "ok", "summary": "Un agente humano se pondra en contacto por WhatsApp en breve."}
    return {"status": "ignored", "reason": result.get("reason", "unknown")}
