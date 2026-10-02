"""Session commands Telephony needs to dial a VoiceSession. Voice keeps
ownership of the session row, its lifecycle and the runtime/room: Telephony
only asks (by id) and receives TelephonySessionView snapshots.

Each command keeps the exact commit boundaries and event payloads the dial
and outbound flows always had.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.voice.application.runtime_dispatcher import VoiceRuntimeDispatcher
from app.modules.voice.application.session_service import VoiceSessionService
from app.modules.voice.domain.errors import VoiceSessionNotFoundError
from app.modules.voice.domain.lifecycle import TERMINAL_STATUSES
from app.modules.voice.domain.views import TelephonySessionView
from app.modules.voice.infrastructure.livekit_runtime import LiveKitRuntimeBackend
from app.modules.voice.infrastructure.models import VoiceSession


def telephony_view(session: VoiceSession) -> TelephonySessionView:
    return TelephonySessionView(
        id=session.id,
        tenant_id=session.tenant_id,
        status=session.status,
        channel=session.channel,
        direction=session.direction,
        agent_id=session.agent_id,
        agent_version_id=session.agent_version_id,
        runtime_ready_at=session.runtime_ready_at,
        livekit_room_name=session.livekit_room_name,
        livekit_sip_trunk_id=session.livekit_sip_trunk_id,
        livekit_sip_participant_identity=session.livekit_sip_participant_identity,
        sip_route_id=session.sip_route_id,
        sip_call_id=session.sip_call_id,
        provider_session_id=session.provider_session_id,
        crm_voice_call_id=session.crm_voice_call_id,
    )


class TelephonySessionOperations:
    def __init__(self, db: Session, runtime_backend: LiveKitRuntimeBackend | None = None) -> None:
        self.db = db
        self.sessions = VoiceSessionService(db)
        self._runtime_backend = runtime_backend

    @property
    def runtime_backend(self) -> LiveKitRuntimeBackend:
        if self._runtime_backend is None:
            self._runtime_backend = LiveKitRuntimeBackend()
        return self._runtime_backend

    # -- reads ---------------------------------------------------------------

    def get_session(self, session_id: str, tenant_id: str, *, refresh: bool = False) -> TelephonySessionView:
        if refresh:
            # Another connection (the runtime posting voice.agent.ready) may
            # have written; drop cached state like the old wait loop did.
            self.db.expire_all()
        return telephony_view(self.sessions.get(session_id, tenant_id))

    def lock_session(self, session_id: str, tenant_id: str) -> TelephonySessionView:
        session = self.db.scalar(
            select(VoiceSession).where(
                VoiceSession.id == session_id, VoiceSession.tenant_id == tenant_id
            ).with_for_update().execution_options(populate_existing=True)
            # populate_existing: a request that lost the idempotency race
            # already holds the row in its identity map; after waiting for the
            # lock it must see the winner's crm_voice_call_id, not a stale None.
        )
        if session is None:
            raise VoiceSessionNotFoundError("Voice session does not belong to this tenant.")
        return telephony_view(session)

    def count_active_telephony_sessions(
        self, tenant_id: str, route_id: str, *, exclude_session_id: str | None = None
    ) -> int:
        query = select(func.count(VoiceSession.id)).where(
            VoiceSession.tenant_id == tenant_id,
            VoiceSession.sip_route_id == route_id,
            VoiceSession.status.not_in(tuple(TERMINAL_STATUSES)),
        )
        if exclude_session_id is not None:
            query = query.where(VoiceSession.id != exclude_session_id)
        return int(self.db.scalar(query) or 0)

    # -- commands ------------------------------------------------------------

    def create_outbound_sip_session(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        idempotency_key: str,
        contact_id: str | None,
        lead_id: str | None,
        caller_phone: str,
    ) -> TelephonySessionView:
        """Idempotent per (tenant, idempotency_key). Raises VoiceSessionError."""
        session = self.sessions.create(
            tenant_id,
            agent_id,
            channel="sip",
            direction="outbound",
            idempotency_key=idempotency_key,
            contact_id=contact_id,
            lead_id=lead_id,
            caller_phone=caller_phone,
        )
        return telephony_view(session)

    def correlate_crm_call(self, session_id: str, tenant_id: str, crm_voice_call_id: str) -> None:
        session = self.sessions.get(session_id, tenant_id)
        session.crm_voice_call_id = crm_voice_call_id
        self.db.flush()

    def cancel_session(self, session_id: str, tenant_id: str, *, end_reason: str) -> None:
        session = self.sessions.get(session_id, tenant_id)
        self.sessions.transition(session, "cancelled", commit=False)
        self.sessions.record_event(
            session,
            "voice.session.cancelled",
            source="control-plane",
            payload={"end_reason": end_reason},
            commit=False,
        )
        self.db.commit()

    def bind_sip_route(self, session_id: str, tenant_id: str, *, route_id: str, livekit_trunk_id: str | None) -> None:
        session = self.sessions.get(session_id, tenant_id)
        session.sip_route_id = route_id
        session.livekit_sip_trunk_id = livekit_trunk_id
        self.sessions.record_event(
            session,
            "voice.outbound.requested",
            source="control-plane",
            payload={"sip_route_id": route_id},
            commit=False,
        )
        self.db.commit()

    async def dispatch_runtime(self, session_id: str, tenant_id: str) -> TelephonySessionView:
        session = self.sessions.get(session_id, tenant_id)
        session = await VoiceRuntimeDispatcher(self.db, backend=self.runtime_backend).dispatch(session)
        return telephony_view(session)

    def begin_sip_dial(self, session_id: str, tenant_id: str, *, route_id: str, participant_identity: str) -> None:
        session = self.sessions.get(session_id, tenant_id)
        session.livekit_sip_participant_identity = participant_identity
        self.sessions.record_event(
            session,
            "voice.sip.dial.started",
            source="control-plane",
            payload={"sip_route_id": route_id},
            commit=False,
        )
        self.db.commit()

    def complete_sip_dial(
        self, session_id: str, tenant_id: str, *, sip_call_id: str, participant_identity: str
    ) -> TelephonySessionView:
        session = self.sessions.get(session_id, tenant_id)
        session.sip_call_id = sip_call_id
        session.livekit_sip_participant_identity = participant_identity
        self.sessions.record_event(
            session,
            "voice.sip.answered",
            source="control-plane",
            payload={"sip_call_id": sip_call_id},
            commit=False,
        )
        self.db.commit()
        self.db.refresh(session)
        return telephony_view(session)

    def fail_session(
        self,
        session_id: str,
        tenant_id: str,
        *,
        code: str,
        sip_status_event: str | None = None,
        skip_if_terminal: bool = False,
    ) -> None:
        """Optionally records ``voice.sip.<status>``, then fails the session
        (``skip_if_terminal`` leaves an already-terminal session untouched
        and only commits)."""
        session = self.sessions.get(session_id, tenant_id)
        if sip_status_event:
            self.sessions.record_event(
                session,
                f"voice.sip.{sip_status_event}",
                source="control-plane",
                payload={"error_code": code},
                commit=False,
            )
        if skip_if_terminal and session.status in TERMINAL_STATUSES:
            self.db.commit()
        else:
            self.sessions.fail(session, code, code)

    async def close_runtime_room(self, session_id: str, tenant_id: str) -> None:
        session = self.sessions.get(session_id, tenant_id)
        try:
            await self.runtime_backend.close_session_room(session.id)
        except Exception:
            self.sessions.record_event(
                session,
                "voice.cleanup.failed",
                source="control-plane",
                payload={"error_code": "livekit_room_close_failed"},
            )
