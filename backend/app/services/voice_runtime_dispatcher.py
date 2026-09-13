from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.models.voice_sessions import VoiceSession
from app.services.livekit_runtime_backend import LiveKitRuntimeBackend, RuntimeDispatchResult
from app.services.voice_session_service import VoiceSessionService


class RuntimeBackend(Protocol):
    async def dispatch(self, session_id: str) -> RuntimeDispatchResult: ...


class VoiceRuntimeDispatcher:
    def __init__(self, db: Session, backend: RuntimeBackend | None = None) -> None:
        self.sessions = VoiceSessionService(db)
        self.backend = backend or LiveKitRuntimeBackend()

    async def dispatch(self, session: VoiceSession) -> VoiceSession:
        self.sessions.db.refresh(session)
        if session.agent is not None:
            self.sessions.db.refresh(session.agent)
        if session.status != "requested" or session.agent is None or session.agent.status != "active":
            return session
        self.sessions.transition(session, "dispatching")
        try:
            result = await self.backend.dispatch(session.id)
        except Exception:
            self.sessions.fail(session, "livekit_dispatch_failed", "LiveKit dispatch failed")
            return session
        self.sessions.db.refresh(session)
        if session.agent is not None:
            self.sessions.db.refresh(session.agent)
        if session.status != "dispatching" or session.agent is None or session.agent.status != "active":
            # Archival may win while LiveKit creates the room. Never leave that room running.
            session.livekit_room_name = result.room_name
            session.livekit_dispatch_id = result.dispatch_id
            self.sessions.db.commit()
            await self.backend.close_session_room(session.id)
            if session.status not in {"ended", "failed", "cancelled"}:
                self.sessions.transition(session, "cancelled", commit=False)
                self.sessions.record_event(
                    session, "voice.session.cancelled", source="control-plane",
                    payload={"end_reason": "agent_archived"}, commit=False,
                )
                self.sessions.db.commit()
            return session
        try:
            session.livekit_room_name = result.room_name
            session.livekit_dispatch_id = result.dispatch_id
            self.sessions.transition(session, "dispatched", commit=False)
            self.sessions.record_event(session, "voice.session.dispatched", source="control-plane", payload={"runtime_engine": "livekit"}, commit=False)
            self.sessions.db.commit()
            self.sessions.db.refresh(session)
            return session
        except Exception:
            self.sessions.fail(session, "livekit_dispatch_failed", "LiveKit dispatch failed")
            return session
