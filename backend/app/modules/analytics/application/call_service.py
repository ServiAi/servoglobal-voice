"""Call ledger: persists call facts and the call event ledger.

Transaction rule: ``commit=True`` (default) is the standalone ingestion mode and
Analytics owns the commit; ``commit=False`` only flushes and the caller owns the
transaction."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.analytics.application.views import call_view, event_view
from app.modules.analytics.contracts import (
    CallEventView,
    CallView,
    EventClaim,
    PersistCallCommand,
    PersistCallEventCommand,
)
from app.modules.analytics.domain.errors import (
    AnalyticsAgentTenantMismatchError,
    AnalyticsConflictError,
    CallNotFoundError,
)
from app.modules.analytics.domain.statuses import (
    ACTIVE_STATUS,
    CallStatusNormalizer,
    is_status_regression,
)
from app.modules.analytics.infrastructure.models import Agent, Call, CallEvent

_STATUS_POLICIES = {"derive", "explicit", "settle_open"}


class AnalyticsCallService:
    def __init__(self, db: Session, status_normalizer: CallStatusNormalizer | None = None) -> None:
        self.db = db
        self.status_normalizer = status_normalizer or CallStatusNormalizer()

    def get(self, tenant_id: str, call_id: str) -> CallView | None:
        call = self.db.get(Call, call_id)
        return call_view(call) if call is not None and call.tenant_id == tenant_id else None

    def find_by_external_call(self, tenant_id: str, external_provider: str, external_call_id: str) -> CallView | None:
        call = self._find(tenant_id, external_provider, external_call_id, lock=False)
        return call_view(call) if call is not None else None

    def list_reconciliation_candidates(self, tenant_id: str, limit: int = 100) -> tuple[CallView, ...]:
        rows = self.db.scalars(
            select(Call)
            .where(Call.tenant_id == tenant_id, Call.normalized_status == ACTIVE_STATUS)
            .order_by(Call.started_at.asc())
            .limit(limit)
        )
        return tuple(call_view(call) for call in rows)

    def persist_call(self, command: PersistCallCommand, *, commit: bool = True) -> CallView:
        """Create-or-update the call keyed by (tenant, provider, external_call_id).

        Concurrent creators converge on one row: the loser re-reads the winner through the
        unique constraint and applies its update to it."""
        if not command.tenant_id:
            raise ValueError("tenant_id is required for persisted calls")
        if command.status_policy not in _STATUS_POLICIES:
            raise ValueError(f"unknown status_policy: {command.status_policy}")
        self._validate_agent(command.tenant_id, command.agent_id)

        call = self._find(command.tenant_id, command.external_provider, command.external_call_id, lock=True)
        if call is None:
            call = self._new_call(command)
            self._apply(call, command)
            if command.external_call_id:
                call = self._insert_or_reuse_winner(call, command)
            else:
                self.db.add(call)
        else:
            self._apply(call, command)

        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(call)
        return call_view(call)

    def claim_event(self, command: PersistCallEventCommand, *, commit: bool = True) -> EventClaim:
        """Record an event exactly once per ``dedup_key`` (events without a key always insert)."""
        call = self.db.get(Call, command.call_id)
        if call is None or call.tenant_id != command.tenant_id:
            raise CallNotFoundError("Call not found for tenant")

        if command.dedup_key:
            winner = self._find_event(command.dedup_key)
            if winner is not None:
                return self._existing_claim(winner, command)

        event = CallEvent(
            tenant_id=command.tenant_id,
            call_id=command.call_id,
            event_type=command.event_type,
            provider_event_id=command.provider_event_id,
            dedup_key=command.dedup_key,
            payload_json=dict(command.payload_json),
            received_at=command.received_at or datetime.now(UTC),
        )
        try:
            with self.db.begin_nested():
                self.db.add(event)
                self.db.flush()
        except IntegrityError:
            winner = self._find_event(command.dedup_key) if command.dedup_key else None
            if winner is None:
                raise
            return self._existing_claim(winner, command)

        if commit:
            self.db.commit()
            self.db.refresh(event)
        return EventClaim(event_view(event), created=True)

    def add_event(self, command: PersistCallEventCommand, *, commit: bool = True) -> CallEventView:
        return self.claim_event(command, commit=commit).event

    def _existing_claim(self, winner: CallEvent, command: PersistCallEventCommand) -> EventClaim:
        if winner.tenant_id != command.tenant_id:
            raise AnalyticsConflictError("The event dedup key belongs to another tenant")
        return EventClaim(event_view(winner), created=False)

    def _find_event(self, dedup_key: str) -> CallEvent | None:
        return self.db.scalar(select(CallEvent).where(CallEvent.dedup_key == dedup_key))

    def _find(
        self, tenant_id: str, external_provider: str, external_call_id: str | None, *, lock: bool
    ) -> Call | None:
        if not external_call_id:
            return None
        statement = select(Call).where(
            Call.tenant_id == tenant_id,
            Call.external_provider == external_provider,
            Call.external_call_id == external_call_id,
        )
        return self.db.scalar(statement.with_for_update() if lock else statement)

    def _insert_or_reuse_winner(self, call: Call, command: PersistCallCommand) -> Call:
        try:
            with self.db.begin_nested():
                self.db.add(call)
                self.db.flush()
            return call
        except IntegrityError:
            winner = self._find(command.tenant_id, command.external_provider, command.external_call_id, lock=True)
            if winner is None:
                raise
            self._apply(winner, command)
            return winner

    def _new_call(self, command: PersistCallCommand) -> Call:
        return Call(
            tenant_id=command.tenant_id,
            external_provider=command.external_provider,
            started_at=command.started_at or datetime.now(UTC),
            normalized_status=self._normalized_status(command) or ACTIVE_STATUS,
        )

    def _validate_agent(self, tenant_id: str, agent_id: str | None) -> None:
        if agent_id is None:
            return
        agent = self.db.get(Agent, agent_id)
        if agent is None or agent.tenant_id != tenant_id:
            raise AnalyticsAgentTenantMismatchError("Agent does not belong to tenant")

    def _apply(self, call: Call, command: PersistCallCommand) -> None:
        partial = command.partial_update
        if command.external_call_id is not None:
            call.external_call_id = command.external_call_id
        call.external_provider = command.external_provider
        normalized_status = self._normalized_status(command)
        if command.status_policy == "settle_open" and call.normalized_status != ACTIVE_STATUS:
            normalized_status = None
        regression = is_status_regression(call.normalized_status, normalized_status, partial_update=partial)

        self._assign(call, "agent_id", command.agent_id, partial)
        self._assign(call, "provider_agent_id", command.provider_agent_id, partial)
        if not regression:
            self._assign(call, "provider_status", command.provider_status, partial)
            if normalized_status is not None:
                call.normalized_status = normalized_status
        self._assign(call, "started_at", command.started_at, partial)
        self._assign(call, "joined_at", command.joined_at, partial)
        self._assign(call, "ended_at", command.ended_at, partial)
        self._assign(call, "duration_seconds", command.duration_seconds, partial)
        self._assign(call, "billed_minutes", self._decimal_or_none(command.billed_minutes), partial)
        self._assign(call, "summary", command.summary, partial)
        self._assign(call, "short_summary", command.short_summary, partial)
        self._assign(call, "recording_url", command.recording_url, partial)
        self._assign(call, "direction", command.direction, partial)
        self._assign(call, "customer_phone", command.customer_phone, partial)
        self._assign(call, "last_synced_at", command.last_synced_at, partial)

    @staticmethod
    def _assign(call: Call, field_name: str, value, partial_update: bool) -> None:
        if partial_update and value is None:
            return
        setattr(call, field_name, value)

    def _normalized_status(self, command: PersistCallCommand) -> str | None:
        if command.status_policy == "derive":
            if command.provider_status is None and command.normalized_status is None:
                return None
            if command.normalized_status:
                return self.status_normalizer.normalize(command.normalized_status, fallback=command.normalized_status)
            return self.status_normalizer.normalize(command.provider_status)
        if not command.normalized_status:
            return None
        return self.status_normalizer.normalize(command.normalized_status, fallback=command.normalized_status)

    @staticmethod
    def _decimal_or_none(value: Decimal | int | float | str | None) -> Decimal | None:
        return None if value is None else Decimal(str(value))
