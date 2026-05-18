from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import NORMALIZED_CALL_STATUSES, Agent, Call, CallEvent
from app.services.call_status_normalizer import CallStatusNormalizer


TERMINAL_CALL_STATUSES = set(NORMALIZED_CALL_STATUSES) - {"in_progress"}


@dataclass(frozen=True)
class PersistCallInput:
    tenant_id: str
    external_provider: str
    started_at: datetime | None = None
    external_call_id: str | None = None
    agent_id: str | None = None
    provider_agent_id: str | None = None
    provider_status: str | None = None
    normalized_status: str | None = None
    joined_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    billed_minutes: Decimal | int | float | str | None = None
    summary: str | None = None
    short_summary: str | None = None
    recording_url: str | None = None
    direction: str | None = None
    customer_phone: str | None = None
    last_synced_at: datetime | None = None
    partial_update: bool = False


@dataclass(frozen=True)
class PersistEventInput:
    tenant_id: str
    call_id: str
    event_type: str
    payload_json: dict[str, Any]
    provider_event_id: str | None = None
    received_at: datetime | None = None


class CallPersistenceService:
    def __init__(
        self,
        db: Session,
        status_normalizer: CallStatusNormalizer | None = None,
    ) -> None:
        self.db = db
        self.status_normalizer = status_normalizer or CallStatusNormalizer()

    def persist_call(self, payload: PersistCallInput) -> Call:
        if not payload.tenant_id:
            raise ValueError("tenant_id is required for persisted calls")

        self._validate_agent(payload.tenant_id, payload.agent_id)
        call = self._find_existing_call(payload)
        if call is None:
            call = Call(
                tenant_id=payload.tenant_id,
                external_provider=payload.external_provider,
                started_at=payload.started_at or datetime.now(UTC),
                normalized_status=self._normalized_status(payload),
            )
            self.db.add(call)

        self._apply_call_payload(call, payload)
        self.db.commit()
        self.db.refresh(call)
        return call

    def persist_event(self, payload: PersistEventInput) -> CallEvent:
        call = self.db.get(Call, payload.call_id)
        if call is None or call.tenant_id != payload.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call not found for tenant",
            )

        event = CallEvent(
            tenant_id=payload.tenant_id,
            call_id=payload.call_id,
            event_type=payload.event_type,
            provider_event_id=payload.provider_event_id,
            payload_json=payload.payload_json,
            received_at=payload.received_at or datetime.now(UTC),
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_calls_pending_reconciliation(self, tenant_id: str, limit: int = 100) -> list[Call]:
        return list(
            self.db.scalars(
                select(Call)
                .where(Call.tenant_id == tenant_id)
                .where(Call.normalized_status == "in_progress")
                .order_by(Call.started_at.asc())
                .limit(limit)
            )
        )

    def _find_existing_call(self, payload: PersistCallInput) -> Call | None:
        if not payload.external_call_id:
            return None
        return self.db.scalar(
            select(Call).where(
                Call.tenant_id == payload.tenant_id,
                Call.external_provider == payload.external_provider,
                Call.external_call_id == payload.external_call_id,
            )
        )

    def _validate_agent(self, tenant_id: str, agent_id: str | None) -> None:
        if agent_id is None:
            return
        agent = self.db.get(Agent, agent_id)
        if agent is None or agent.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Agent does not belong to tenant",
            )

    def _apply_call_payload(self, call: Call, payload: PersistCallInput) -> None:
        if payload.external_call_id is not None:
            call.external_call_id = payload.external_call_id
        call.external_provider = payload.external_provider
        should_update_status = payload.provider_status is not None or payload.normalized_status is not None
        normalized_status = self._normalized_status(payload) if should_update_status else None
        is_status_regression = (
            payload.partial_update
            and call.normalized_status in TERMINAL_CALL_STATUSES
            and normalized_status == "in_progress"
        )

        self._assign(call, "agent_id", payload.agent_id, payload.partial_update)
        self._assign(call, "provider_agent_id", payload.provider_agent_id, payload.partial_update)
        if not is_status_regression:
            self._assign(call, "provider_status", payload.provider_status, payload.partial_update)
            if normalized_status is not None:
                call.normalized_status = normalized_status
        self._assign(call, "started_at", payload.started_at, payload.partial_update)
        self._assign(call, "joined_at", payload.joined_at, payload.partial_update)
        self._assign(call, "ended_at", payload.ended_at, payload.partial_update)
        self._assign(call, "duration_seconds", payload.duration_seconds, payload.partial_update)
        self._assign(
            call,
            "billed_minutes",
            self._decimal_or_none(payload.billed_minutes),
            payload.partial_update,
        )
        self._assign(call, "summary", payload.summary, payload.partial_update)
        self._assign(call, "short_summary", payload.short_summary, payload.partial_update)
        self._assign(call, "recording_url", payload.recording_url, payload.partial_update)
        self._assign(call, "direction", payload.direction, payload.partial_update)
        self._assign(call, "customer_phone", payload.customer_phone, payload.partial_update)
        self._assign(call, "last_synced_at", payload.last_synced_at, payload.partial_update)

    def _assign(self, call: Call, field_name: str, value, partial_update: bool) -> None:
        if partial_update and value is None:
            return
        setattr(call, field_name, value)

    def _normalized_status(self, payload: PersistCallInput) -> str:
        if payload.normalized_status:
            return self.status_normalizer.normalize(
                payload.normalized_status,
                fallback=payload.normalized_status,
            )
        return self.status_normalizer.normalize(payload.provider_status)

    def _decimal_or_none(self, value: Decimal | int | float | str | None) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))
