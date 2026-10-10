"""Browser (WebRTC) join for a VoiceSession: LiveKit participant token plus
the readiness protocol that dispatches the room exactly once."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.agents.public import AgentsFacade
from app.modules.voice.application.runtime_dispatcher import RuntimeBackend, VoiceRuntimeDispatcher
from app.modules.voice.application.session_service import VoiceSessionService
from app.modules.voice.domain.errors import VoiceSessionError
from app.modules.voice.domain.lifecycle import TERMINAL_STATUSES
from app.modules.voice.domain.views import WebRTCJoinInfo
from app.modules.voice.infrastructure.models import VoiceSession

logger = logging.getLogger(__name__)

DISPATCH_WAIT_SECONDS = 10.0
DISPATCH_POLL_SECONDS = 0.25


WEBRTC_NOT_CONFIGURED = "voice_webrtc_not_configured"


def livekit_webrtc_configured() -> bool:
    return all((settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET))


def ensure_livekit_webrtc_configured() -> None:
    """Preflight, before any session is dispatched: an unconfigured transport must leave the
    session ``requested`` (retryable), not dispatched-and-failed."""
    if not livekit_webrtc_configured():
        raise VoiceSessionError(WEBRTC_NOT_CONFIGURED)


class WebRTCJoinService:
    def __init__(self, db: Session, backend: RuntimeBackend | None = None) -> None:
        self.db = db
        self.backend = backend
        self.sessions = VoiceSessionService(db)

    def _is_terminal(self, session: VoiceSession) -> bool:
        if session.status in TERMINAL_STATUSES or session.agent_id is None:
            return True
        return AgentsFacade(self.db).get_agent_status(session.tenant_id, session.agent_id) == "archived"

    def issue_token(self, session: VoiceSession) -> WebRTCJoinInfo:
        """A fresh, short-lived, microphone-only participant token for the session's room."""
        if self._is_terminal(session):
            raise VoiceSessionError("Voice session is terminal.")
        if session.channel != "webrtc" or session.runtime_engine != "livekit" or not session.livekit_room_name:
            raise VoiceSessionError("Voice session is not ready for LiveKit WebRTC.")
        if not livekit_webrtc_configured():
            raise VoiceSessionError("LiveKit WebRTC is not configured.")  # QA endpoint contract

        from livekit import api

        ttl_seconds = max(30, min(settings.VOICE_WEBRTC_TOKEN_TTL_SECONDS, 600))
        token = (
            api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity(f"web-{uuid4()}")
            .with_ttl(timedelta(seconds=ttl_seconds))
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=session.livekit_room_name,
                    can_subscribe=True,
                    can_publish=True,
                    can_publish_data=False,
                    can_publish_sources=["microphone"],
                    room_create=False,
                    room_admin=False,
                    room_record=False,
                    ingress_admin=False,
                    can_update_own_metadata=False,
                )
            )
            .to_jwt()
        )
        logger.info(
            "Voice WebRTC participant token issued",
            extra={
                "tenant_id": session.tenant_id,
                "voice_session_id": session.id,
                "agent_id": session.agent_id,
                "agent_version_id": session.agent_version_id,
                "livekit_room_name": session.livekit_room_name,
                "runtime_engine": session.runtime_engine,
                "channel": session.channel,
            },
        )
        return WebRTCJoinInfo(
            voice_session_id=session.id,
            server_url=settings.LIVEKIT_URL,
            room_name=session.livekit_room_name,
            participant_token=token,
            expires_in=ttl_seconds,
        )

    async def ensure_join(self, session_id: str, tenant_id: str) -> WebRTCJoinInfo:
        """Dispatch the session's room exactly once (a replay or a concurrent
        caller never dispatches again) and issue a new participant token."""
        ensure_livekit_webrtc_configured()
        session = self.sessions.get(session_id, tenant_id)
        if session.channel != "webrtc":
            raise VoiceSessionError("Voice session is not ready for LiveKit WebRTC.")
        if session.status == "requested":
            await VoiceRuntimeDispatcher(self.db, self.backend).dispatch(session)
        deadline = time.monotonic() + DISPATCH_WAIT_SECONDS
        self.db.refresh(session)
        # Another request won the dispatch claim and is creating the room.
        while session.status == "dispatching" and not session.livekit_room_name and time.monotonic() < deadline:
            await asyncio.sleep(DISPATCH_POLL_SECONDS)
            self.db.refresh(session)
        if session.status == "failed":
            raise VoiceSessionError("voice_session_dispatch_failed")
        if session.status in TERMINAL_STATUSES:
            raise VoiceSessionError("voice_session_terminal")
        join = self.issue_token(session)
        self.db.commit()  # release any read snapshot/locks before returning to the caller
        return join
