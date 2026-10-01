"""Voice Orchestration -- public API.

Boundary only: the implementation still lives in the legacy layers
(app.services.voice_session_service, app.schemas.session_context) until
this module is migrated. Other modules import from here, never from those.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.schemas.session_context import SessionContextV1
from app.services import voice_session_service as _sessions
from app.services.voice_session_service import (
    SessionContextEnrichmentError,
    VoiceSessionError,
    VoiceSessionNotFoundError,
)

__all__ = [
    "SessionContextEnrichmentError",
    "SessionContextV1",
    "VoiceSessionError",
    "VoiceSessionFacade",
    "VoiceSessionNotFoundError",
]


class VoiceSessionFacade:
    """The three VoiceSession operations other modules may perform. The
    session row returned by ``get`` is an opaque handle: pass it back to
    this facade, do not mutate it."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, session_id: str) -> Any:
        return _sessions.VoiceSessionService(self.db).get(session_id)

    def record_event(self, session: Any, event_type: str, *, source: str, payload: dict[str, Any]) -> None:
        _sessions.VoiceSessionService(self.db).record_event(session, event_type, source=source, payload=payload)

    def enrich_context(self, session: Any, *, contact: Any, lead: Any, event_source: str) -> None:
        _sessions.VoiceSessionService(self.db).enrich_context(
            session, contact=contact, lead=lead, event_source=event_source
        )
