from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.db.session import get_db
from app.schemas.runtime_session import RuntimeSessionSpecV1
from app.schemas.voice_sessions import RuntimeEventAck, RuntimeEventV1, VoiceSessionCreateRequest, VoiceSessionResponse
from app.security.voice_runtime_auth import require_voice_runtime
from app.services.agent_compiler_service import AgentCompilerError, AgentCompilerService
from app.services.tenant_feature_service import TenantFeatureDisabledError, TenantFeatureService, VOICE_RUNTIME_V2
from app.services.voice_runtime_dispatcher import VoiceRuntimeDispatcher
from app.services.voice_session_service import VoiceSessionError, VoiceSessionNotFoundError, VoiceSessionService

router = APIRouter(tags=["Voice Runtime"])
WRITE_ROLES = ["platform_admin", "tenant_admin"]


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


@router.get("/api/v1/internal/voice-runtime/sessions/{session_id}/spec", response_model=RuntimeSessionSpecV1, dependencies=[Depends(require_voice_runtime)])
def get_runtime_session_spec(session_id: str, db: Session = Depends(get_db)) -> RuntimeSessionSpecV1:
    try:
        session = VoiceSessionService(db).get(session_id)
        if session.status in {"ended", "failed", "cancelled"}:
            raise VoiceSessionError("Voice session is terminal.")
        return AgentCompilerService().compile(session.agent, session.agent_version, session_id=session.id)
    except VoiceSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (VoiceSessionError, AgentCompilerError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/v1/internal/voice-runtime/sessions/{session_id}/events", response_model=RuntimeEventAck, dependencies=[Depends(require_voice_runtime)])
def post_runtime_event(session_id: str, body: RuntimeEventV1, db: Session = Depends(get_db)) -> RuntimeEventAck:
    if body.session_id != session_id:
        raise HTTPException(status_code=422, detail="Event session_id does not match path")
    service = VoiceSessionService(db)
    try:
        session = service.get(session_id)
        allowed_payload = {
            key: value for key, value in body.payload.items()
            if key in {"livekit_job_id", "provider_session_id", "end_reason", "error_code", "speaker", "text", "timestamp"}
        }
        _, duplicate = service.record_event(session, body.event_type, source=body.source, event_id=body.event_id, sequence=body.sequence, payload=allowed_payload, occurred_at=body.occurred_at, commit=False)
        if duplicate:
            db.rollback()
            return RuntimeEventAck(duplicate=True)
        if "livekit_job_id" in allowed_payload:
            session.livekit_job_id = str(allowed_payload["livekit_job_id"])[:160]
        if "provider_session_id" in allowed_payload:
            session.provider_session_id = str(allowed_payload["provider_session_id"])[:255]
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
