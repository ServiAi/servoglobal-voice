from __future__ import annotations

import hmac
import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import CrmVoiceCall, CrmVoiceCallEvent
from app.models.integrations import TenantVoiceProviderConfig
from app.services.voice_config_service import VoiceConfigService
from app.services.crm_activity_service import CrmActivityService
from app.services.integration_event_service import IntegrationEventService

logger = logging.getLogger(__name__)


class VoiceWebhookService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.config_service = VoiceConfigService(db)
        self.activity_service = CrmActivityService(db)
        self.integration_event_service = IntegrationEventService(db)

    def verify_webhook_signature(
        self,
        request: Request,
        raw_body: bytes,
        secret: str,
    ) -> None:
        timestamp = request.headers.get("x-ultravox-webhook-timestamp")
        signature_header = request.headers.get("x-ultravox-webhook-signature")

        if not timestamp or not signature_header:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing webhook validation headers",
            )

        try:
            parsed_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed_time.tzinfo is None:
                parsed_time = parsed_time.replace(tzinfo=UTC)
            else:
                parsed_time = parsed_time.astimezone(UTC)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid timestamp format",
            ) from exc

        age_seconds = abs((datetime.now(UTC) - parsed_time).total_seconds())
        if age_seconds > 300:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Expired webhook timestamp",
            )

        expected_signature = hmac.new(
            secret.encode(),
            raw_body + timestamp.encode(),
            hashlib.sha256,
        ).hexdigest()

        signatures = [sig.strip() for sig in signature_header.split(",")]
        if not any(hmac.compare_digest(sig, expected_signature) for sig in signatures):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    def handle_provider_event(self, provider: str, payload: dict[str, Any]) -> dict[str, Any]:
        call = self.resolve_call_by_metadata_or_provider_id(payload)
        if not call:
            self.integration_event_service.record_event(
                tenant_id="platform",
                provider=provider,
                event_type="webhook_unreconciled",
                status="warning",
                message="Received voice webhook event for unrecognized call.",
                metadata={"provider": provider},
            )
            return {"status": "unreconciled"}

        tenant_id = call.tenant_id
        event_type = payload.get("event") or payload.get("event_type") or payload.get("type") or "call.updated"

        mapped_status, ended_at, duration, recording_url, transcript_url, summary = self._parse_ultravox_event(payload)

        call.status = mapped_status
        if ended_at:
            call.ended_at = ended_at
        if duration is not None:
            call.duration_seconds = duration
        if recording_url:
            call.recording_url = recording_url
        if transcript_url:
            call.transcript_url = transcript_url
        if summary:
            call.summary = summary
        
        call.updated_at = datetime.now(UTC)
        self.db.commit()

        self.record_call_event(
            tenant_id=tenant_id,
            voice_call_id=call.id,
            provider=provider,
            event_type=event_type,
            status="success",
            payload_summary={
                "status": mapped_status,
                "duration_seconds": duration,
                "has_recording": bool(recording_url),
                "has_summary": bool(summary),
            },
        )

        activity_type = self._activity_type_from_status(mapped_status, event_type)
        if activity_type:
            title = self._activity_title_from_status(mapped_status)
            description = self._activity_desc_from_status(mapped_status, duration, summary)
            
            self.activity_service.create_activity(
                tenant_id=tenant_id,
                lead_id=call.lead_id,
                contact_id=call.contact_id,
                activity_type=activity_type,
                title=title,
                description=description,
                payload_json={
                    "voice_call_id": call.id,
                    "provider": provider,
                    "provider_call_id": call.provider_call_id,
                    "status": mapped_status,
                    "duration_seconds": duration,
                },
            )

        self.integration_event_service.record_event(
            tenant_id=tenant_id,
            provider=provider,
            event_type="call_status",
            status="success",
            resource_type="call",
            resource_id=call.id,
            metadata={"status": mapped_status, "voice_call_id": call.id, "provider_call_id": call.provider_call_id},
        )

        return {
            "status": "processed",
            "voice_call_id": call.id,
            "call_status": call.status,
        }

    def resolve_call_by_metadata_or_provider_id(self, payload: dict[str, Any]) -> CrmVoiceCall | None:
        call_obj = payload.get("call") or payload
        metadata = payload.get("metadata") or call_obj.get("metadata") or {}

        voice_call_id = metadata.get("voice_call_id")
        if voice_call_id:
            call = self.db.get(CrmVoiceCall, voice_call_id)
            if call:
                return call

        provider_call_id = call_obj.get("callId") or call_obj.get("id")
        if provider_call_id:
            call = self.db.scalar(
                select(CrmVoiceCall).where(CrmVoiceCall.provider_call_id == provider_call_id)
            )
            if call:
                return call

        provider_session_id = call_obj.get("sessionId") or call_obj.get("session_id")
        if provider_session_id:
            call = self.db.scalar(
                select(CrmVoiceCall).where(CrmVoiceCall.provider_session_id == provider_session_id)
            )
            if call:
                return call

        return None

    def record_call_event(
        self,
        tenant_id: str,
        voice_call_id: str,
        provider: str,
        event_type: str,
        status: str,
        payload_summary: dict[str, Any],
    ) -> CrmVoiceCallEvent:
        event = CrmVoiceCallEvent(
            tenant_id=tenant_id,
            voice_call_id=voice_call_id,
            provider=provider,
            event_type=event_type,
            status=status,
            payload_summary_json=payload_summary,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def _parse_ultravox_event(self, payload: dict[str, Any]) -> tuple[str, datetime | None, int | None, str | None, str | None, str | None]:
        event_type = payload.get("event") or payload.get("event_type") or payload.get("type") or "call.updated"
        call_obj = payload.get("call") or payload

        status_str = call_obj.get("status") or call_obj.get("state") or "in_progress"
        mapped_status = "in_progress"

        status_upper = status_str.upper()
        if status_upper in ("NEW", "REQUESTED", "QUEUED"):
            mapped_status = "queued"
        elif status_upper in ("RINGING", "CONNECTING"):
            mapped_status = "ringing"
        elif status_upper in ("LEAVING", "ENDED", "COMPLETED"):
            mapped_status = "completed"
        elif status_upper in ("FAILED", "ERROR"):
            mapped_status = "failed"
        elif status_upper == "CANCELLED":
            mapped_status = "cancelled"

        end_reason = call_obj.get("endReason")
        if end_reason:
            reason_lower = end_reason.lower()
            if any(term in reason_lower for term in ("error", "fail", "system")):
                mapped_status = "failed"
            elif any(term in reason_lower for term in ("no_answer", "timeout", "missed", "no-answer")):
                mapped_status = "no_answer"
            elif any(term in reason_lower for term in ("busy", "decline", "reject")):
                mapped_status = "busy"
            elif any(term in reason_lower for term in ("cancel", "abandon")):
                mapped_status = "cancelled"

        if event_type == "call.ended":
            if mapped_status not in ("completed", "failed", "cancelled", "no_answer", "busy"):
                mapped_status = "completed"

        ended_at = None
        ended_str = call_obj.get("ended")
        if ended_str:
            try:
                ended_at = datetime.fromisoformat(ended_str.replace("Z", "+00:00")).astimezone(UTC)
            except Exception:
                pass

        duration = None
        dur_val = call_obj.get("duration")
        if dur_val is not None:
            try:
                if isinstance(dur_val, str) and dur_val.endswith("s"):
                    duration = int(float(dur_val[:-1]))
                else:
                    duration = int(float(dur_val))
            except Exception:
                pass

        recording_url = call_obj.get("recordingUrl")
        transcript_url = None
        summary = call_obj.get("summary")

        return mapped_status, ended_at, duration, recording_url, transcript_url, summary

    def _activity_type_from_status(self, status: str, event_type: str) -> str | None:
        if status == "queued":
            return "voice_call_queued"
        elif status == "ringing":
            return "voice_call_ringing"
        elif status == "in_progress":
            return "voice_call_started"
        elif status == "completed":
            if event_type == "call.ended" or "summary" in event_type:
                return "voice_call_completed"
            return "voice_call_started"
        elif status == "failed":
            return "voice_call_failed"
        elif status == "cancelled":
            return "voice_call_cancelled"
        elif status == "no_answer":
            return "voice_call_no_answer"
        elif status == "busy":
            return "voice_call_busy"
        return None

    def _activity_title_from_status(self, status: str) -> str:
        titles = {
            "queued": "Llamada en cola",
            "ringing": "Llamando...",
            "in_progress": "Llamada conectada",
            "completed": "Llamada finalizada",
            "failed": "Llamada fallida",
            "cancelled": "Llamada cancelada",
            "no_answer": "Sin respuesta",
            "busy": "Línea ocupada",
        }
        return titles.get(status, "Llamada actualizada")

    def _activity_desc_from_status(self, status: str, duration: int | None, summary: str | None) -> str:
        if status == "completed":
            dur_str = f"{duration} segundos" if duration else "duración desconocida"
            desc = f"Llamada completada exitosamente. Duración: {dur_str}."
            if summary:
                desc += f"\nResumen: {summary}"
            return desc
        elif status == "failed":
            return "El intento de llamada falló en el proveedor."
        elif status == "no_answer":
            return "El cliente no contestó la llamada."
        elif status == "busy":
            return "El número de destino se encuentra ocupado."
        elif status == "ringing":
            return "El teléfono de destino está timbrando."
        elif status == "queued":
            return "La llamada está en cola de espera para discar."
        return "Llamada en curso."
