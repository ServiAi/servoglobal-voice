import asyncio
from time import monotonic

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.voice_sessions import VoiceSession
from app.services.livekit_runtime_backend import LiveKitRuntimeBackend
from app.services.livekit_sip_service import LiveKitSipDialError, LiveKitSipService
from app.services.voice_phone_service import normalize_outbound_phone
from app.services.voice_runtime_dispatcher import VoiceRuntimeDispatcher
from app.services.voice_session_service import VoiceSessionService
from app.services.voice_sip_route_service import VoiceSipRouteService


class VoiceSessionSipDialError(ValueError):
    def __init__(self, code: str, call_status: str = "failed") -> None:
        super().__init__(code)
        self.code = code
        self.call_status = call_status


class VoiceSessionSipService:
    """Dials one tenant-scoped SIP VoiceSession without creating CRM records."""

    def __init__(
        self,
        db: Session,
        *,
        sip_service: LiveKitSipService | None = None,
        runtime_backend: LiveKitRuntimeBackend | None = None,
    ) -> None:
        self.db = db
        self.sessions = VoiceSessionService(db)
        self.routes = VoiceSipRouteService(db)
        self.sip = sip_service or LiveKitSipService()
        self.runtime_backend = runtime_backend or LiveKitRuntimeBackend()

    async def dial(
        self, session: VoiceSession, to_phone: str, *, manage_failure: bool = True
    ) -> VoiceSession:
        if session.channel != "sip" or session.direction != "outbound":
            raise VoiceSessionSipDialError("invalid_sip_session")
        if session.status != "requested":
            return session
        route = self.routes.get_active_route(
            session.tenant_id, for_update=True, require_livekit=True
        )
        number = normalize_outbound_phone(
            to_phone,
            default_country=route.default_country,
            allowed_countries=set(route.allowed_countries_json),
        )
        active = int(
            self.db.scalar(
                select(func.count(VoiceSession.id)).where(
                    VoiceSession.tenant_id == session.tenant_id,
                    VoiceSession.sip_route_id == route.id,
                    VoiceSession.id != session.id,
                    VoiceSession.status.not_in(("ended", "failed", "cancelled")),
                )
            )
            or 0
        )
        if active >= route.max_concurrent_calls:
            self.sessions.transition(session, "cancelled", commit=False)
            self.sessions.record_event(
                session,
                "voice.session.cancelled",
                source="control-plane",
                payload={"end_reason": "telephony_capacity_exceeded"},
                commit=False,
            )
            self.db.commit()
            raise VoiceSessionSipDialError("telephony_capacity_exceeded", "cancelled")

        session.sip_route_id = route.id
        session.livekit_sip_trunk_id = route.livekit_outbound_trunk_id
        self.sessions.record_event(
            session,
            "voice.outbound.requested",
            source="control-plane",
            payload={"sip_route_id": route.id},
            commit=False,
        )
        self.db.commit()

        session = await VoiceRuntimeDispatcher(
            self.db, backend=self.runtime_backend
        ).dispatch(session)
        if session.status == "failed":
            raise VoiceSessionSipDialError("runtime_dispatch_failed")
        try:
            session = await self.wait_until_runtime_ready(session.id, session.tenant_id)
        except TimeoutError:
            if manage_failure:
                self.sessions.fail(session, "runtime_not_ready", "runtime_not_ready")
                await self._close_room(session)
            raise VoiceSessionSipDialError("runtime_not_ready") from None

        participant_identity = f"sip-{session.id}"
        session.livekit_sip_participant_identity = participant_identity
        self.sessions.record_event(
            session,
            "voice.sip.dial.started",
            source="control-plane",
            payload={"sip_route_id": route.id},
            commit=False,
        )
        self.db.commit()
        try:
            result = await self.sip.dial(
                trunk_id=route.livekit_outbound_trunk_id,
                to_phone=number.e164,
                from_number=route.caller_id,
                room_name=session.livekit_room_name,
                participant_identity=participant_identity,
            )
        except LiveKitSipDialError as exc:
            if manage_failure:
                self.sessions.record_event(
                    session,
                    f"voice.sip.{exc.call_status}",
                    source="control-plane",
                    payload={"error_code": exc.code},
                    commit=False,
                )
                self.sessions.fail(session, exc.code, exc.code)
                await self._close_room(session)
            raise VoiceSessionSipDialError(exc.code, exc.call_status) from None

        session.sip_call_id = result.sip_call_id
        session.livekit_sip_participant_identity = result.participant_identity
        self.sessions.record_event(
            session,
            "voice.sip.answered",
            source="control-plane",
            payload={"sip_call_id": result.sip_call_id},
            commit=False,
        )
        self.db.commit()
        self.db.refresh(session)
        return session

    async def wait_until_runtime_ready(self, session_id: str, tenant_id: str) -> VoiceSession:
        deadline = monotonic() + settings.LIVEKIT_SIP_RUNTIME_READY_TIMEOUT_SECONDS
        while monotonic() < deadline:
            self.db.expire_all()
            session = self.sessions.get(session_id, tenant_id)
            if session.runtime_ready_at is not None:
                return session
            if session.status in {"failed", "ended", "cancelled"}:
                raise TimeoutError
            await asyncio.sleep(0.2)
        raise TimeoutError

    async def _close_room(self, session: VoiceSession) -> None:
        try:
            await self.runtime_backend.close_session_room(session.id)
        except Exception:
            self.sessions.record_event(
                session,
                "voice.cleanup.failed",
                source="control-plane",
                payload={"error_code": "livekit_room_close_failed"},
            )
