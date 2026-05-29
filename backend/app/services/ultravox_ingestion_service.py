from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import Agent, Call, CallEvent
from app.models.identity import Tenant
from app.services.call_persistence_service import (
    CallPersistenceService,
    PersistCallInput,
    PersistEventInput,
)


ULTRAVOX_PROVIDER = "ultravox"
OFFICIAL_ULTRAVOX_EVENTS = {
    "call.started",
    "call.joined",
    "call.ended",
    "call.billed",
}


@dataclass(frozen=True)
class IngestionResult:
    call: Call
    event: CallEvent | None


class UltravoxIngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.call_persistence = CallPersistenceService(db)

    def ingest_event(self, payload: dict[str, Any]) -> IngestionResult:
        tenant = self._resolve_tenant(payload)
        call_input = self._build_call_input(payload, tenant.id)
        call = self.call_persistence.persist_call(call_input)
        event = self.call_persistence.persist_event(
            PersistEventInput(
                tenant_id=tenant.id,
                call_id=call.id,
                event_type=self._event_type(payload),
                provider_event_id=self._first(payload, "eventId", "event_id", "id"),
                payload_json=payload,
                received_at=self._datetime_or_none(
                    self._first(payload, "receivedAt", "received_at", "timestamp", "createdAt")
                ),
            )
        )
        return IngestionResult(call=call, event=event)

    def reconcile_call(self, payload: dict[str, Any]) -> IngestionResult:
        tenant = self._resolve_tenant(payload)
        call_input = self._build_call_input(payload, tenant.id)
        call = self.call_persistence.persist_call(call_input)
        return IngestionResult(call=call, event=None)

    def list_reconciliation_candidates(self, tenant_id: str, limit: int = 100) -> list[Call]:
        return self.call_persistence.list_calls_pending_reconciliation(tenant_id, limit=limit)

    def _build_call_input(self, payload: dict[str, Any], tenant_id: str) -> PersistCallInput:
        call = self._call_object(payload)
        agent = self._agent_object(call)
        metadata = self._metadata(payload)
        external_provider = self._string(
            self._field(payload, "external_provider", "provider")
            or metadata.get("external_provider")
            or ULTRAVOX_PROVIDER
        )
        provider_agent_id = self._string(
            self._first(agent, "agentId", "agent_id", "id")
            or self._field(payload, "provider_agent_id", "agentId", "agent_id")
            or metadata.get("provider_agent_id")
            or metadata.get("agent_id")
        )
        started_at = self._datetime_or_none(
            self._field(payload, "created", "startedAt", "started_at", "startTime", "createdAt")
            or metadata.get("started_at")
        )
        joined_at = self._datetime_or_none(
            self._field(payload, "joined", "joinedAt", "joined_at", "joinTime")
            or metadata.get("joined_at")
        )
        ended_at = self._datetime_or_none(
            self._field(payload, "ended", "endedAt", "ended_at", "endTime")
            or metadata.get("ended_at")
        )
        duration_seconds = self._duration_seconds(payload, started_at, joined_at, ended_at)
        billed_minutes = self._billed_minutes(payload)
        return PersistCallInput(
            tenant_id=tenant_id,
            external_provider=external_provider,
            external_call_id=self._external_call_id(payload),
            agent_id=self._resolve_agent_id(tenant_id, external_provider, provider_agent_id),
            provider_agent_id=provider_agent_id,
            provider_status=self._provider_status(payload),
            normalized_status=self._normalized_status(payload),
            started_at=started_at,
            joined_at=joined_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            billed_minutes=billed_minutes,
            summary=self._string(self._field(payload, "summary") or metadata.get("summary")),
            short_summary=self._string(
                self._field(payload, "shortSummary", "short_summary") or metadata.get("short_summary")
            ),
            recording_url=self._string(
                self._field(payload, "recording_url", "recordingUrl") or metadata.get("recording_url")
            ),
            direction=self._string(self._field(payload, "direction") or metadata.get("direction")),
            customer_phone=self._string(
                self._field(payload, "customer_phone", "customerPhone", "phone")
                or metadata.get("customer_phone")
            ),
            last_synced_at=datetime.now(UTC),
            partial_update=True,
        )

    def _resolve_tenant(self, payload: dict[str, Any]) -> Tenant:
        metadata = self._metadata(payload)
        tenant_id = self._string(
            metadata.get("tenant_id") or self._first(payload, "tenant_id", "tenantId")
        )
        tenant_slug = self._string(
            metadata.get("tenant_slug") or self._first(payload, "tenant_slug", "tenantSlug")
        )
        tenant = None
        if tenant_id:
            tenant = self.db.get(Tenant, tenant_id)
        if tenant is None and tenant_slug:
            tenant = self.db.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to resolve tenant for Ultravox payload",
            )
        return tenant

    def _resolve_agent_id(
        self,
        tenant_id: str,
        external_provider: str,
        provider_agent_id: str | None,
    ) -> str | None:
        if not provider_agent_id:
            return None
        agent = self.db.scalar(
            select(Agent).where(
                Agent.tenant_id == tenant_id,
                Agent.external_provider == external_provider,
                Agent.external_agent_id == provider_agent_id,
            )
        )
        return agent.id if agent is not None else None

    def _external_call_id(self, payload: dict[str, Any]) -> str:
        metadata = self._metadata(payload)
        external_call_id = self._string(
            self._field(payload, "callId", "external_call_id", "call_id", "call_id_external")
            or metadata.get("external_call_id")
            or metadata.get("call_id")
        )
        if not external_call_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ultravox payload is missing external call id",
            )
        return external_call_id

    def _provider_status(self, payload: dict[str, Any]) -> str | None:
        event_type = self._event_type(payload)
        billing_status = self._string(self._field(payload, "billingStatus", "billing_status"))
        if event_type == "call.billed" and billing_status:
            return billing_status

        end_reason = self._string(self._field(payload, "endReason", "end_reason"))
        if end_reason:
            return end_reason

        legacy_status = self._string(
            self._field(payload, "provider_status", "status", "state")
        )
        if legacy_status:
            return legacy_status

        if event_type in OFFICIAL_ULTRAVOX_EVENTS:
            return event_type.rsplit(".", 1)[-1]

        return None

    def _normalized_status(self, payload: dict[str, Any]) -> str | None:
        explicit_status = self._string(self._first(payload, "normalized_status"))
        if explicit_status:
            return explicit_status

        event_type = self._event_type(payload)
        started_at = self._datetime_or_none(
            self._field(payload, "created", "startedAt", "started_at", "startTime", "createdAt")
        )
        joined_at = self._datetime_or_none(
            self._field(payload, "joined", "joinedAt", "joined_at", "joinTime")
        )
        ended_at = self._datetime_or_none(
            self._field(payload, "ended", "endedAt", "ended_at", "endTime")
        )
        end_reason = self._string(self._field(payload, "endReason", "end_reason"))
        billing_status = self._string(self._field(payload, "billingStatus", "billing_status"))
        legacy_status = self._string(
            self._field(payload, "provider_status", "status", "state")
        )

        if end_reason:
            mapped_reason = self._status_from_end_reason(end_reason, joined_at is not None)
            if mapped_reason and mapped_reason != "answered":
                return mapped_reason

        if billing_status and billing_status.upper() == "BILLING_STATUS_FREE_SYSTEM_ERROR":
            return "failed"

        if ended_at:
            if joined_at:
                if self._detect_voicemail(payload):
                    return "voicemail"
                return "answered"
            return "unanswered"

        if legacy_status:
            return legacy_status

        if event_type in {"call.started", "call.joined"}:
            return "in_progress"
        if event_type in {"call.ended", "call.billed"}:
            if joined_at:
                if self._detect_voicemail(payload):
                    return "voicemail"
                return "answered"
            return "unanswered"

        return "in_progress" if started_at else None

    def _status_from_end_reason(self, end_reason: str, has_joined: bool) -> str | None:
        normalized_reason = end_reason.strip().lower()
        if normalized_reason in {"connection_error", "system_error", "failed", "failure"}:
            return "failed"
        if normalized_reason in {"unjoined", "no_answer", "not_answered", "missed"}:
            return "unanswered"
        if normalized_reason == "timeout":
            return "answered" if has_joined else "unanswered"
        if normalized_reason in {"hangup", "agent_hangup", "completed", "ended"}:
            return "answered" if has_joined else "unanswered"
        if normalized_reason in {"cancel", "canceled", "cancelled"}:
            return "cancelled"
        if normalized_reason in {"busy", "declined", "rejected"}:
            return "rejected"
        if normalized_reason in {"human_transfer", "transferred", "transfer"}:
            return "transferred"
        if normalized_reason in {"voicemail", "machine"}:
            return "voicemail"
        return None

    _VOICEMAIL_PATTERNS = frozenset({
        "buzón de voz",
        "buzón de voz automático",
        "contestador automático",
        "mensaje de voz",
        "correo de voz",
        "systema de contestador",
        "sistema de contestador",
        "contestador automatico",
        "contestador automático",
        "machine",
        "voicemail",
        "answering machine",
    })

    def _detect_voicemail(self, payload: dict[str, Any]) -> bool:
        call_obj = self._call_object(payload)
        short_summary = self._string(call_obj.get("shortSummary") or call_obj.get("short_summary"))
        summary = self._string(call_obj.get("summary"))

        text_to_check = " ".join(filter(None, [short_summary, summary])).lower()
        if not text_to_check:
            return False

        return any(pattern in text_to_check for pattern in self._VOICEMAIL_PATTERNS)

    def _event_type(self, payload: dict[str, Any]) -> str:
        return self._string(
            self._first(payload, "event_type", "eventType", "event", "type") or "call.updated"
        )

    def _metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for candidate in (payload.get("metadata"), payload.get("meta")):
            if isinstance(candidate, dict):
                metadata.update(candidate)
        call_metadata = self._call_object(payload).get("metadata")
        if isinstance(call_metadata, dict):
            metadata.update(call_metadata)
        return metadata

    def _call_object(self, payload: dict[str, Any]) -> dict[str, Any]:
        call = payload.get("call")
        return call if isinstance(call, dict) else payload

    def _agent_object(self, call: dict[str, Any]) -> dict[str, Any]:
        agent = call.get("agent")
        return agent if isinstance(agent, dict) else {}

    def _field(self, payload: dict[str, Any], *keys: str) -> Any:
        call = self._call_object(payload)
        value = self._first(call, *keys)
        if value is not None:
            return value
        if call is not payload:
            return self._first(payload, *keys)
        return None

    def _first(self, payload: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in payload and payload[key] is not None:
                return payload[key]
        return None

    def _duration_seconds(
        self,
        payload: dict[str, Any],
        started_at: datetime | None,
        joined_at: datetime | None,
        ended_at: datetime | None,
    ) -> int | None:
        explicit_duration = self._int_or_none(
            self._field(payload, "duration_seconds", "durationSeconds", "duration")
        )
        if explicit_duration is not None:
            return explicit_duration
        if ended_at is None:
            return None
        duration_start = joined_at or started_at
        if duration_start is None:
            return None
        return max(0, int((ended_at - duration_start).total_seconds()))

    def _billed_minutes(self, payload: dict[str, Any]) -> Decimal | None:
        metadata = self._metadata(payload)
        explicit_minutes = self._decimal_or_none(
            self._field(payload, "billed_minutes", "billedMinutes", "billed_duration_minutes")
            or metadata.get("billed_minutes")
        )
        if explicit_minutes is not None:
            return explicit_minutes

        billed_duration = (
            self._field(payload, "billedDuration", "billed_duration")
            or self._nested_field(self._field(payload, "sipDetails", "sip_details"), "billedDuration")
        )
        return self._duration_to_minutes(billed_duration)

    def _duration_to_minutes(self, value: Any) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, (int, float, Decimal)):
            return (Decimal(str(value)) / Decimal("60")).quantize(Decimal("0.01"))
        if not isinstance(value, str):
            return None

        duration = value.strip().lower()
        try:
            if duration.endswith("s"):
                return (Decimal(duration[:-1]) / Decimal("60")).quantize(Decimal("0.01"))
            if duration.endswith("m"):
                return Decimal(duration[:-1]).quantize(Decimal("0.01"))
        except Exception:
            return None
        return None

    def _nested_field(self, value: Any, key: str) -> Any:
        if isinstance(value, dict):
            return value.get(key)
        return None

    def _datetime_or_none(self, value: Any) -> datetime | None:
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, UTC)
        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
        return None

    def _int_or_none(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _decimal_or_none(self, value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    def _string(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)
