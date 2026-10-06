"""Tenant cleanup for the Identity-owned tenant deletion (flush only; the caller commits)."""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.modules.analytics.infrastructure.models import Agent, Call, CallEvent, MetricSnapshotDaily


class AnalyticsMaintenanceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def cleanup_tenant(self, tenant_id: str) -> dict[str, int]:
        """Delete in FK-safe order: events, snapshots, calls, agents. Returns deleted counts."""
        counts: dict[str, int] = {}
        for name, model in (
            ("call_events", CallEvent),
            ("metric_snapshots", MetricSnapshotDaily),
            ("calls", Call),
            ("agents", Agent),
        ):
            result = self.db.execute(delete(model).where(model.tenant_id == tenant_id))
            counts[name] = max(result.rowcount or 0, 0)
        self.db.flush()
        return counts
