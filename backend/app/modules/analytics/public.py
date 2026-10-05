"""Analytics (+ CRM call projections) -- public API (minimal, not migrated).

Only the projection of voice sessions into call history and, when linked,
the CRM call/activity. Implementation still lives in legacy
app.services.voice_call_projection_service; it splits between Analytics
and CRM when those modules migrate.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

__all__ = ["CallLookup", "VoiceCallProjectionFacade"]


class VoiceCallProjectionFacade:
    """Satisfies Voice's VoiceProjectionPort."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def on_runtime_event(self, session_id: str, tenant_id: str, event_type: str, occurred_at: datetime | None) -> None:
        from app.services.voice_call_projection_service import (
            VoiceCallProjectionService,
        )

        VoiceCallProjectionService(self.db).apply_runtime_event(session_id, tenant_id, event_type, occurred_at)

    def reconcile(self, session_id: str, tenant_id: str) -> None:
        from app.services.voice_call_projection_service import (
            VoiceCallProjectionService,
        )

        VoiceCallProjectionService(self.db).reconcile_session(session_id, tenant_id=tenant_id)

    def project_session(self, session_id: str, tenant_id: str, *, commit: bool = True) -> None:
        from app.services.voice_call_projection_service import (
            VoiceCallProjectionService,
        )

        VoiceCallProjectionService(self.db).project_session(session_id, tenant_id=tenant_id, commit=commit)

    def is_real_call(self, session_id: str, tenant_id: str | None = None) -> bool:
        """Whether the session carries real call evidence (read-only; holds
        no row locks)."""
        from app.services.voice_call_projection_service import (
            VoiceCallProjectionService,
        )

        return VoiceCallProjectionService(self.db).is_real_call(session_id, tenant_id)

    def projection_exists(self, session_id: str, tenant_id: str) -> bool:
        from app.services.voice_call_projection_service import (
            VoiceCallProjectionService,
        )

        return VoiceCallProjectionService(self.db).projection_exists(session_id, tenant_id)


class CallLookup:
    """Read-only lookup of Analytics' call ids (used by CRM's lead resolution)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def find_call_id(self, tenant_id: str, external_provider: str | None, external_call_id: str) -> str | None:
        from sqlalchemy import select

        from app.models.analytics import Call

        return self.db.scalar(
            select(Call.id)
            .where(
                Call.tenant_id == tenant_id,
                Call.external_provider == external_provider,
                Call.external_call_id == external_call_id,
            )
            .limit(1)
        )
