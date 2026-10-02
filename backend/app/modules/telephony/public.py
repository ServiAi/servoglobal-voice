"""Telephony -- public API (minimal; Telephony itself is not migrated yet).

Only what Voice Orchestration needs today: phone normalization for caller
identity and dialing a SIP QA session. SIP routes, LiveKit SIP, trunks and
capacity stay behind this boundary (legacy app.services.* for now).

Import-light on purpose: the SIP service is loaded lazily (it still reaches
Voice through legacy compatibility paths until Telephony migrates).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.voice_phone_service import (
    VoicePhoneValidationError,
    normalize_caller_id,
)

__all__ = ["SipDialError", "SipQaFacade", "VoicePhoneValidationError", "normalize_caller_id"]


class SipDialError(ValueError):
    """``code`` is the stable dial failure (e.g. telephony_capacity_exceeded)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SipQaFacade:
    def __init__(self, db: Session) -> None:
        self.db = db

    async def dial_session(self, session_id: str, to_phone: str) -> None:
        """Dials an already-created SIP QA VoiceSession through the tenant's
        route (capacity, dispatch, agent-ready wait and participant are all
        Telephony's job). Raises SipDialError."""
        from app.services.voice_session_sip_service import (
            VoiceSessionSipDialError,
            VoiceSessionSipService,
        )

        service = VoiceSessionSipService(self.db)
        try:
            await service.dial(service.sessions.get(session_id), to_phone)
        except VoiceSessionSipDialError as exc:
            raise SipDialError(str(exc)) from exc
