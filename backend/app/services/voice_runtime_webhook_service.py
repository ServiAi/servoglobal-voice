from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.analytics import Call, CallEvent
from app.models.crm import CrmVoiceCall, CrmVoiceCallEvent
from app.models.voice_submissions import TenantVoiceRuntimeCall
from app.services.crm_activity_service import CrmActivityService
from app.services.voice_config_service import VoiceConfigService

OFFICIAL_EVENTS = {"call.started", "call.joined", "call.ended", "call.billed"}


class RuntimeWebhookTarget:
    def __init__(self, call: CrmVoiceCall, runtime: TenantVoiceRuntimeCall) -> None:
        self.call = call
        self.runtime = runtime


class VoiceRuntimeWebhookService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.config_service = VoiceConfigService(db)

    def resolve_target(self, provider: str, payload: dict[str, Any]) -> RuntimeWebhookTarget | None:
        call_obj = payload.get("call") or payload
        metadata = payload.get("metadata") or call_obj.get("metadata") or {}
        voice_call_id = metadata.get("voice_call_id")
        call = self.db.get(CrmVoiceCall, str(voice_call_id)) if voice_call_id else None
        if call is None:
            provider_call_id = call_obj.get("callId") or call_obj.get("id")
            if provider_call_id:
                call = self.db.scalar(select(CrmVoiceCall).where(CrmVoiceCall.provider_call_id == str(provider_call_id)))
        if call is None:
            return None
        runtime = self.db.scalar(select(TenantVoiceRuntimeCall).where(TenantVoiceRuntimeCall.crm_voice_call_id == call.id))
        if runtime is None:
            return None
        config = self.config_service.get_provider_config(runtime.tenant_id, provider)
        if not config or provider != call.provider or provider != runtime.provider or config.provider != provider:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook validation failed")
        return RuntimeWebhookTarget(call, runtime)

    def runtime_secret(self, target: RuntimeWebhookTarget) -> str:
        config = self.config_service.get_provider_config(target.runtime.tenant_id, target.runtime.provider)
        secret = self.config_service.decrypt_webhook_secret(config) if config else None
        if not secret:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook validation failed")
        return secret

    def process(self, provider: str, payload: dict[str, Any], target: RuntimeWebhookTarget) -> dict[str, Any]:
        event_type = str(payload.get("event") or payload.get("event_type") or payload.get("type") or "")
        if event_type not in OFFICIAL_EVENTS:
            return {"status": "ignored", "processed": False}
        call_obj = payload.get("call") or payload
        provider_call_id = call_obj.get("callId") or call_obj.get("id") or target.runtime.provider_call_id
        if not provider_call_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook call identifier missing")
        provider_call_id = str(provider_call_id)
        dedup_key = f"ultravox:{provider_call_id}:{event_type}"
        now = datetime.now(UTC)
        call_id = target.call.id
        runtime_id = target.runtime.id
        tenant_id = target.runtime.tenant_id
        contact_id = target.call.contact_id
        lead_id = target.call.lead_id
        self.db.rollback()
        with self.db.begin():
            call = self.db.get(CrmVoiceCall, call_id)
            runtime = self.db.get(TenantVoiceRuntimeCall, runtime_id)
            if call is None or runtime is None or call.tenant_id != runtime.tenant_id:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook validation failed")
            insert = sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
            claimed = self.db.execute(
                insert(CrmVoiceCallEvent)
                .values(
                    tenant_id=runtime.tenant_id,
                    voice_call_id=call.id,
                    provider=provider,
                    event_type=event_type,
                    status="success",
                    dedup_key=dedup_key,
                    payload_summary_json={"event_type": event_type},
                    created_at=now,
                )
                .on_conflict_do_nothing(index_elements=["dedup_key"])
                .returning(CrmVoiceCallEvent.id)
            ).scalar_one_or_none()
            if claimed is None:
                return {"status": "processed", "processed": False, "voice_call_id": call.id, "call_status": call.status}

            analytics = self.db.scalar(select(Call).where(Call.tenant_id == runtime.tenant_id, Call.external_provider == provider, Call.external_call_id == provider_call_id))
            if analytics is None:
                analytics = Call(tenant_id=runtime.tenant_id, external_provider=provider, external_call_id=provider_call_id, normalized_status="in_progress", started_at=now)
                self.db.add(analytics)
                self.db.flush()
            analytics.provider_status = str(call_obj.get("status") or call_obj.get("state") or event_type)
            analytics.provider_agent_id = str(call_obj.get("agentId")) if call_obj.get("agentId") else analytics.provider_agent_id
            analytics.duration_seconds = self._integer(call_obj.get("duration") or call_obj.get("durationSeconds")) or analytics.duration_seconds
            if event_type == "call.joined":
                analytics.joined_at = now
            if event_type == "call.ended":
                analytics.ended_at = now
                analytics.normalized_status = "answered" if runtime.connected_at else "unanswered"
            if event_type == "call.billed":
                analytics.billed_minutes = self._decimal(call_obj.get("billedMinutes") or payload.get("billedMinutes"))
                if analytics.billed_minutes is None:
                    analytics.billed_minutes = self._duration_minutes(
                        call_obj.get("billedDuration") or payload.get("billedDuration")
                    )
                if analytics.normalized_status == "in_progress":
                    analytics.normalized_status = "answered" if runtime.connected_at else "unanswered"
            self.db.add(CallEvent(tenant_id=runtime.tenant_id, call_id=analytics.id, event_type=event_type, provider_event_id=None, dedup_key=dedup_key, payload_json={"event_type": event_type}, received_at=now))

            call.provider_call_id = provider_call_id
            crm_terminal = call.status in {"completed", "failed", "cancelled", "no_answer", "busy"}
            if event_type == "call.started":
                if not crm_terminal:
                    call.status = "queued"
                origins, target_status = {"starting", "unknown"}, "ready"
            elif event_type == "call.joined":
                if not crm_terminal:
                    call.status = "in_progress"
                    call.answered_at = call.answered_at or now
                origins, target_status = {"starting", "unknown", "ready"}, "connected"
            elif event_type == "call.ended":
                if not crm_terminal:
                    call.status = "completed"
                call.ended_at = call.ended_at or now
                origins, target_status = {"starting", "unknown", "ready", "connected"}, "ended"
            else:
                origins, target_status = set(), runtime.status
            if origins:
                values: dict[str, Any] = {"status": target_status, "provider_call_id": provider_call_id}
                if target_status == "connected":
                    values["connected_at"] = now
                if target_status == "ended":
                    values["ended_at"] = now
                self.db.execute(update(TenantVoiceRuntimeCall).where(TenantVoiceRuntimeCall.id == runtime.id, TenantVoiceRuntimeCall.status.in_(origins)).values(**values))

        if contact_id:
            try:
                CrmActivityService(self.db).create_activity(
                    tenant_id=tenant_id,
                    lead_id=lead_id,
                    contact_id=contact_id,
                    activity_type="voice_call_updated",
                    title="Voice experience call updated",
                    call_id=call_id,
                    deduplication_key=f"voice_runtime:{dedup_key}",
                    payload_json={"voice_call_id": call_id, "event_type": event_type},
                )
            except Exception:
                self.db.rollback()
        return {"status": "processed", "processed": True, "voice_call_id": call_id, "call_status": call.status}

    @staticmethod
    def _integer(value: Any) -> int | None:
        try:
            return int(float(str(value).removesuffix("s"))) if value is not None else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        try:
            return Decimal(str(value)) if value is not None else None
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _duration_minutes(value: Any) -> Decimal | None:
        from app.services.ultravox_ingestion_service import UltravoxIngestionService

        return UltravoxIngestionService._duration_to_minutes(value)
