"""Analytics (+ CRM call projections) -- public API (minimal, not migrated).

Only the projection of voice sessions into call history and, when linked,
the CRM call/activity. Implementation still lives in legacy
app.services.voice_call_projection_service; it splits between Analytics
and CRM when those modules migrate.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

__all__ = ["VoiceCallProjectionFacade"]


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
