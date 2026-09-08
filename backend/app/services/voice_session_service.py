from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agents import TenantAgent, TenantAgentVersion
from app.models.voice_sessions import VoiceSession, VoiceSessionEvent


class VoiceSessionError(ValueError):
    pass


class VoiceSessionNotFoundError(VoiceSessionError):
    pass


TRANSITIONS = {
    "requested": {"dispatching", "failed", "cancelled"},
    "dispatching": {"dispatched", "failed", "cancelled"},
    "dispatched": {"starting", "ended", "failed", "cancelled"},
    "starting": {"connected", "ended", "failed", "cancelled"},
    "connected": {"ending", "ended", "failed"},
    "ending": {"ended", "failed"},
    "ended": set(),
    "failed": set(),
    "cancelled": set(),
}


class VoiceSessionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, tenant_id: str, agent_id: str, *, channel: str, direction: str, idempotency_key: str | None = None) -> VoiceSession:
        if idempotency_key:
            existing = self.db.scalar(select(VoiceSession).where(VoiceSession.tenant_id == tenant_id, VoiceSession.idempotency_key == idempotency_key))
            if existing:
                return existing
        agent = self.db.scalar(select(TenantAgent).where(TenantAgent.id == agent_id, TenantAgent.tenant_id == tenant_id))
        if agent is None or agent.status != "active" or not agent.published_version_id:
            raise VoiceSessionError("An active agent with a published version is required.")
        version = self.db.scalar(select(TenantAgentVersion).where(TenantAgentVersion.id == agent.published_version_id, TenantAgentVersion.agent_id == agent.id, TenantAgentVersion.tenant_id == tenant_id, TenantAgentVersion.status == "published"))
        if version is None:
            raise VoiceSessionError("The agent's published version is invalid.")
        runtime = version.runtime_binding_json
        if runtime.get("pipeline_type") != "realtime" or not isinstance(runtime.get("realtime"), dict):
            raise VoiceSessionError("Published agent is not configured for realtime voice.")
        session = VoiceSession(tenant_id=tenant_id, agent_id=agent.id, agent_version_id=version.id, channel=channel, direction=direction, runtime_engine="livekit", pipeline_type="realtime", provider=runtime["realtime"].get("provider", ""), idempotency_key=idempotency_key)
        self.db.add(session)
        self.db.flush()
        self.record_event(session, "voice.session.requested", source="control-plane", commit=False)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            if not idempotency_key:
                raise
            existing = self.db.scalar(select(VoiceSession).where(VoiceSession.tenant_id == tenant_id, VoiceSession.idempotency_key == idempotency_key))
            if existing is None:
                raise
            return existing
        self.db.refresh(session)
        return session

    def get(self, session_id: str, tenant_id: str | None = None) -> VoiceSession:
        query = select(VoiceSession).where(VoiceSession.id == session_id)
        if tenant_id is not None:
            query = query.where(VoiceSession.tenant_id == tenant_id)
        session = self.db.scalar(query)
        if session is None:
            raise VoiceSessionNotFoundError("Voice session not found.")
        return session

    def transition(self, session: VoiceSession, target: str, *, commit: bool = True) -> VoiceSession:
        if target == session.status:
            return session
        if target not in TRANSITIONS.get(session.status, set()):
            raise VoiceSessionError(f"Invalid voice session transition: {session.status} -> {target}")
        session.status = target
        now = datetime.now(timezone.utc)
        if target == "dispatched": session.dispatched_at = now
        elif target == "starting": session.started_at = now
        elif target == "connected": session.connected_at = now
        elif target in {"ended", "failed", "cancelled"}: session.ended_at = now
        if commit:
            self.db.commit()
            self.db.refresh(session)
        return session

    def record_event(self, session: VoiceSession, event_type: str, *, source: str, event_id: str | None = None, sequence: int | None = None, payload: dict | None = None, occurred_at: datetime | None = None, commit: bool = True) -> tuple[VoiceSessionEvent, bool]:
        if event_id:
            existing = self.db.scalar(select(VoiceSessionEvent).where(VoiceSessionEvent.event_id == event_id))
            if existing:
                if existing.voice_session_id != session.id:
                    raise VoiceSessionError("Event id belongs to another session.")
                return existing, True
        event = VoiceSessionEvent(event_id=event_id, tenant_id=session.tenant_id, voice_session_id=session.id, event_type=event_type, source=source, sequence=sequence, payload_json=payload or {}, occurred_at=occurred_at or datetime.now(timezone.utc))
        self.db.add(event)
        if commit:
            self.db.commit()
            self.db.refresh(event)
        return event, False

    def fail(self, session: VoiceSession, code: str, message: str) -> VoiceSession:
        session.error_code = code[:80]
        session.error_message_sanitized = message[:500]
        if session.status not in {"failed", "ended", "cancelled"}:
            self.transition(session, "failed", commit=False)
        self.record_event(session, "voice.session.failed", source="control-plane", payload={"error_code": session.error_code}, commit=False)
        self.db.commit()
        return session

    def end(self, session: VoiceSession, reason: str) -> VoiceSession:
        session.end_reason = reason[:40]
        if session.status == "connected": self.transition(session, "ending", commit=False)
        self.transition(session, "ended", commit=False)
        self.record_event(session, "voice.session.ended", source="control-plane", payload={"end_reason": session.end_reason}, commit=False)
        self.db.commit()
        return session
