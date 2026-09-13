from __future__ import annotations

import logging
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.domain.voice_registry import get_provider
from app.schemas.runtime_session import RuntimeSessionSpecV1
from app.schemas.voice_credentials import ProviderCredentialResponse
from app.schemas.voice_sessions import RuntimeEventAck, RuntimeEventV1, VoiceSessionCreateRequest, VoiceSessionResponse, WebRTCParticipantTokenResponse
from app.security.voice_runtime_auth import require_voice_runtime
from app.services.agent_compiler_service import AgentCompilerError, AgentCompilerService
from app.services.tenant_feature_service import TenantFeatureDisabledError, TenantFeatureService, VOICE_RUNTIME_V2
from app.services.voice_config_service import VoiceConfigService
from app.services.voice_runtime_dispatcher import VoiceRuntimeDispatcher
from app.services.voice_session_service import VoiceSessionError, VoiceSessionNotFoundError, VoiceSessionService

router = APIRouter(tags=["Voice Runtime"])
WRITE_ROLES = ["platform_admin", "tenant_admin"]
logger = logging.getLogger(__name__)


@router.post("/api/v1/voice/sessions", response_model=VoiceSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_voice_session(
    body: VoiceSessionCreateRequest,
    context: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> VoiceSessionResponse:
    try:
        TenantFeatureService(db).require_enabled(context.tenant_id, VOICE_RUNTIME_V2)
        session = VoiceSessionService(db).create(context.tenant_id, body.agent_id, channel=body.channel, direction=body.direction, idempotency_key=body.idempotency_key)
        session = await VoiceRuntimeDispatcher(db).dispatch(session)
        return VoiceSessionResponse.model_validate(session)
    except TenantFeatureDisabledError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except VoiceSessionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/v1/voice/sessions/{session_id}/webrtc-token", response_model=WebRTCParticipantTokenResponse)
def create_webrtc_participant_token(
    session_id: str,
    context: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> WebRTCParticipantTokenResponse:
    try:
        TenantFeatureService(db).require_enabled(context.tenant_id, VOICE_RUNTIME_V2)
        session = VoiceSessionService(db).get(session_id, tenant_id=context.tenant_id)
        if session.status in {"ended", "failed", "cancelled"} or session.agent_id is None or session.agent.status == "archived":
            raise VoiceSessionError("Voice session is terminal.")
        if session.channel != "webrtc" or session.runtime_engine != "livekit" or not session.livekit_room_name:
            raise VoiceSessionError("Voice session is not ready for LiveKit WebRTC.")
        if not all((settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)):
            raise VoiceSessionError("LiveKit WebRTC is not configured.")

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
        return WebRTCParticipantTokenResponse(
            voice_session_id=session.id,
            server_url=settings.LIVEKIT_URL,
            room_name=session.livekit_room_name,
            participant_token=token,
            expires_in=ttl_seconds,
        )
    except TenantFeatureDisabledError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except VoiceSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VoiceSessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/v1/internal/voice-runtime/sessions/{session_id}/spec", response_model=RuntimeSessionSpecV1, dependencies=[Depends(require_voice_runtime)])
def get_runtime_session_spec(session_id: str, db: Session = Depends(get_db)) -> RuntimeSessionSpecV1:
    try:
        session = VoiceSessionService(db).get(session_id)
        if session.status in {"ended", "failed", "cancelled"} or session.agent_id is None or session.agent.status == "archived":
            raise VoiceSessionError("Voice session is terminal.")
        return AgentCompilerService().compile(session.agent, session.agent_version, session_id=session.id)
    except VoiceSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (VoiceSessionError, AgentCompilerError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/api/v1/internal/voice-runtime/sessions/{session_id}/credentials/{provider}",
    response_model=ProviderCredentialResponse,
    dependencies=[Depends(require_voice_runtime)],
)
def get_runtime_provider_credential(session_id: str, provider: str, db: Session = Depends(get_db)) -> ProviderCredentialResponse:
    """Resolve the tenant-scoped provider credential for one VoiceSession.

    Credential resolution is bound to session_id, not a bare tenant_id: the
    caller cannot request an arbitrary tenant's key, only the key for the
    provider already recorded on this specific session. The API key never
    appears in RuntimeSessionSpecV1, LiveKit metadata, or logs -- only in
    this response, over the authenticated internal channel.
    """
    if get_provider(provider) is None:
        raise HTTPException(status_code=422, detail="Unsupported voice provider.")
    try:
        session = VoiceSessionService(db).get(session_id)
    except VoiceSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice session not found.") from exc
    if session.provider != provider:
        raise HTTPException(status_code=404, detail="Provider is not associated with this voice session.")
    if session.status in {"ended", "failed", "cancelled"} or session.agent_id is None or session.agent.status == "archived":
        raise HTTPException(status_code=409, detail="Voice session is terminal.")
    voice_config_service = VoiceConfigService(db)
    try:
        config = voice_config_service.get_active_provider_config(session.tenant_id, provider)
        api_key = voice_config_service.decrypt_api_key(config)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="provider_credentials_unavailable") from exc
    logger.info(
        "Voice runtime credential resolved",
        extra={"tenant_id": session.tenant_id, "voice_session_id": session.id, "provider": provider},
    )
    return ProviderCredentialResponse(provider=provider, api_key=api_key, base_url=None)


@router.post("/api/v1/internal/voice-runtime/sessions/{session_id}/events", response_model=RuntimeEventAck, dependencies=[Depends(require_voice_runtime)])
def post_runtime_event(session_id: str, body: RuntimeEventV1, db: Session = Depends(get_db)) -> RuntimeEventAck:
    if body.session_id != session_id:
        raise HTTPException(status_code=422, detail="Event session_id does not match path")
    service = VoiceSessionService(db)
    try:
        session = service.get(session_id)
        allowed_payload = {
            key: value for key, value in body.payload.items()
            if key in {"livekit_job_id", "provider_session_id", "end_reason", "error_code", "speaker", "text", "timestamp", "participant_identity", "track_source"}
        }
        _, duplicate = service.record_event(session, body.event_type, source=body.source, event_id=body.event_id, sequence=body.sequence, payload=allowed_payload, occurred_at=body.occurred_at, commit=False)
        if duplicate:
            db.rollback()
            return RuntimeEventAck(duplicate=True)
        if "livekit_job_id" in allowed_payload:
            session.livekit_job_id = str(allowed_payload["livekit_job_id"])[:160]
        if "provider_session_id" in allowed_payload:
            session.provider_session_id = str(allowed_payload["provider_session_id"])[:255]
        if body.event_type == "voice.session.ended" and session.status == "connected":
            service.transition(session, "ending", commit=False)
        target = {
            "voice.session.started": "starting",
            "voice.session.connected": "connected",
            "voice.session.ended": "ended",
            "voice.session.failed": "failed",
        }.get(body.event_type)
        if target and target != session.status:
            service.transition(session, target, commit=False)
        if body.event_type == "voice.session.ended":
            session.end_reason = str(allowed_payload.get("end_reason", "unknown"))[:40]
        elif body.event_type == "voice.session.failed":
            session.error_code = str(allowed_payload.get("error_code", "runtime_failed"))[:80]
        db.commit()
        return RuntimeEventAck()
    except VoiceSessionNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VoiceSessionError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
