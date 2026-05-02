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
        metadata = self._metadata(payload)
        external_provider = self._string(
            self._first(payload, "external_provider", "provider")
            or metadata.get("external_provider")
            or ULTRAVOX_PROVIDER
        )
        provider_agent_id = self._string(
            self._first(payload, "provider_agent_id", "agentId", "agent_id")
            or metadata.get("provider_agent_id")
            or metadata.get("agent_id")
        )
        started_at = self._datetime_or_none(
            self._first(payload, "startedAt", "started_at", "startTime", "createdAt")
            or metadata.get("started_at")
        )
        joined_at = self._datetime_or_none(
            self._first(payload, "joinedAt", "joined_at", "joinTime") or metadata.get("joined_at")
        )
        ended_at = self._datetime_or_none(
            self._first(payload, "endedAt", "ended_at", "endTime") or metadata.get("ended_at")
        )
        return PersistCallInput(
            tenant_id=tenant_id,
            external_provider=external_provider,
            external_call_id=self._external_call_id(payload),
            agent_id=self._resolve_agent_id(tenant_id, external_provider, provider_agent_id),
            provider_agent_id=provider_agent_id,
            provider_status=self._provider_status(payload),
            normalized_status=self._string(self._first(payload, "normalized_status")),
            started_at=started_at,
            joined_at=joined_at,
            ended_at=ended_at,
            duration_seconds=self._int_or_none(
                self._first(payload, "duration_seconds", "durationSeconds", "duration")
            ),
            billed_minutes=self._decimal_or_none(
                self._first(payload, "billed_minutes", "billedMinutes", "billed_duration_minutes")
            ),
            summary=self._string(self._first(payload, "summary") or metadata.get("summary")),
            short_summary=self._string(
                self._first(payload, "short_summary", "shortSummary") or metadata.get("short_summary")
            ),
            recording_url=self._string(
                self._first(payload, "recording_url", "recordingUrl") or metadata.get("recording_url")
            ),
            direction=self._string(self._first(payload, "direction") or metadata.get("direction")),
            customer_phone=self._string(
                self._first(payload, "customer_phone", "customerPhone", "phone")
                or metadata.get("customer_phone")
            ),
            last_synced_at=datetime.now(UTC),
            partial_update=True,
        )

    def _resolve_tenant(self, payload: dict[str, Any]) -> Tenant:
        metadata = self._metadata(payload)
        tenant_id = self._string(self._first(payload, "tenant_id", "tenantId") or metadata.get("tenant_id"))
        tenant_slug = self._string(
            self._first(payload, "tenant_slug", "tenantSlug") or metadata.get("tenant_slug")
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
            self._first(payload, "external_call_id", "callId", "call_id", "call_id_external")
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
        return self._string(
            self._first(payload, "provider_status", "status", "state")
        )

    def _event_type(self, payload: dict[str, Any]) -> str:
        return self._string(
            self._first(payload, "event_type", "eventType", "event", "type") or "call.updated"
        )

    def _metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = payload.get("metadata") or payload.get("meta") or {}
        return metadata if isinstance(metadata, dict) else {}

    def _first(self, payload: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in payload and payload[key] is not None:
                return payload[key]
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
