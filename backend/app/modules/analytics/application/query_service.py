"""Read-only semantic queries over call facts (no generic query builder is exposed)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.analytics.contracts import CallMetricsView, CallSummaryFact
from app.modules.analytics.domain.statuses import ACTIVE_STATUS
from app.modules.analytics.infrastructure.models import Call


class AnalyticsQueryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_call_id(self, tenant_id: str, external_provider: str | None, external_call_id: str) -> str | None:
        return self.db.scalar(
            select(Call.id)
            .where(
                Call.tenant_id == tenant_id,
                Call.external_provider == external_provider,
                Call.external_call_id == external_call_id,
            )
            .limit(1)
        )

    def latest_summary(self, tenant_id: str, call_ids: Sequence[str]) -> CallSummaryFact | None:
        if not call_ids:
            return None
        call = self.db.scalar(
            select(Call)
            .where(Call.tenant_id == tenant_id, Call.id.in_(list(call_ids)))
            .order_by(Call.ended_at.desc().nullslast(), Call.started_at.desc().nullslast())
            .limit(1)
        )
        if call is None:
            return None
        return CallSummaryFact(
            summary=call.summary,
            short_summary=call.short_summary,
            started_at=call.started_at,
            ended_at=call.ended_at,
            duration_seconds=call.duration_seconds,
        )

    def statuses_by_ids(self, tenant_id: str, call_ids: Sequence[str]) -> dict[str, str]:
        if not call_ids:
            return {}
        rows = self.db.execute(
            select(Call.id, Call.normalized_status).where(Call.tenant_id == tenant_id, Call.id.in_(list(call_ids)))
        ).all()
        return {call_id: status for call_id, status in rows}

    def call_metrics(
        self,
        tenant_id: str,
        *,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
        call_ids: Sequence[str] | None = None,
    ) -> CallMetricsView:
        """``call_ids=None`` means no id filter; an empty sequence matches no call."""
        filters = [Call.tenant_id == tenant_id]
        if started_from is not None:
            filters.append(Call.started_at >= started_from)
        if started_to is not None:
            filters.append(Call.started_at <= started_to)
        if call_ids is not None:
            filters.append(Call.id.in_(list(call_ids)))
        rows = self.db.execute(
            select(Call.normalized_status, Call.duration_seconds, Call.billed_minutes).where(*filters)
        ).all()

        durations = [duration for _, duration, _ in rows if duration is not None]
        return CallMetricsView(
            total_calls=len(rows),
            answered_calls=sum(1 for status, _, _ in rows if status == "answered"),
            unanswered_calls=sum(1 for status, _, _ in rows if status == "unanswered"),
            voicemail_calls=sum(1 for status, _, _ in rows if status == "voicemail"),
            failed_calls=sum(1 for status, _, _ in rows if status == "failed"),
            average_duration_seconds=round(sum(durations) / len(durations), 2) if durations else 0.0,
            total_billed_minutes=round(float(sum(billed or 0 for _, _, billed in rows)), 2),
        )

    def billed_minutes(self, tenant_id: str, period_start: datetime, period_end: datetime) -> Decimal:
        """Finished calls with billed minutes whose start lies in [period_start, period_end] (closed)."""
        total = self.db.scalar(
            select(func.coalesce(func.sum(Call.billed_minutes), 0)).where(
                Call.tenant_id == tenant_id,
                Call.billed_minutes.is_not(None),
                Call.normalized_status != ACTIVE_STATUS,
                Call.started_at >= period_start,
                Call.started_at <= period_end,
            )
        )
        return Decimal(str(total or 0))

