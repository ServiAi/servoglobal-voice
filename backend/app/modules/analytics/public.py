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
