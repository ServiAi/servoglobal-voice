"""Voice Experiences -> canonical Voice runtime, only through ``voice.public``."""

from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.modules.agents.public import AgentRuntimeTargetUnavailableError, AgentsFacade
from app.modules.voice.public import (
    ContactResolutionError,
    VoiceSessionError,
    VoiceSessionFacade,
)
from app.modules.voice_experiences.domain.errors import VoiceRuntimeUnavailable
from app.modules.voice_experiences.domain.views import LaunchSession, WebRTCJoin

_JOIN_CODES = {
    "voice_session_terminal": "terminal",
    "voice_session_dispatch_failed": "dispatch_failed",
}


class VoiceRuntimeAdapter:
    def __init__(self, db: Session, *, runtime_backend: object = None) -> None:
        self.db = db
        self.sessions = VoiceSessionFacade(db, runtime_backend=runtime_backend)

    def require_runnable_agent(self, tenant_id: str, agent_id: str, agent_version_id: str) -> str:
        try:
            target = AgentsFacade(self.db).resolve_runtime_target(tenant_id, agent_id, agent_version_id)
        except AgentRuntimeTargetUnavailableError as exc:
            raise VoiceRuntimeUnavailable("unavailable") from exc
        if not target.is_realtime or not target.realtime_provider:
            raise VoiceRuntimeUnavailable("unavailable")
        return target.realtime_provider

    def create_exact_session(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        agent_version_id: str,
        idempotency_key: str,
        contact_id: str | None,
        lead_id: str | None,
        variables: dict[str, object],
    ) -> LaunchSession:
        try:
            ref = self.sessions.create_session_from_agent_version(
                tenant_id,
                agent_id,
                agent_version_id,
                channel="webrtc",
                direction="internal",
                purpose="production",
                idempotency_key=idempotency_key,
                contact_id=contact_id,
                lead_id=lead_id,
                caller_phone=None,  # a browser participant is not a PSTN caller
                variables=variables,
            )
        except (VoiceSessionError, ContactResolutionError, ValidationError, ValueError) as exc:
            raise VoiceRuntimeUnavailable("unavailable") from exc
        return LaunchSession(session_id=ref.session_id, provider=ref.provider)

    def attach_crm_call(self, session_id: str, tenant_id: str, crm_voice_call_id: str) -> None:
        try:
            self.sessions.attach_crm_call(session_id, tenant_id, crm_voice_call_id)
        except (VoiceSessionError, ValueError) as exc:
            raise VoiceRuntimeUnavailable("unavailable") from exc

    async def ensure_webrtc_join(self, session_id: str, tenant_id: str) -> WebRTCJoin:
        try:
            join = await self.sessions.ensure_webrtc_join(session_id, tenant_id)
        except VoiceSessionError as exc:
            raise VoiceRuntimeUnavailable(_JOIN_CODES.get(str(exc), "unavailable")) from exc
        return WebRTCJoin(
            server_url=join.server_url,
            participant_token=join.participant_token,
            expires_in=join.expires_in,
        )
