from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.models.crm import CrmVoiceCall
from app.models.voice_sessions import VoiceSessionEvent
from app.domain.voice_registry import get_provider
from app.schemas.runtime_session import RuntimeSessionSpecV1
from app.schemas.session_context import SessionContextV1
from app.schemas.voice_credentials import ProviderCredentialResponse
from app.schemas.voice_sessions import (
    RuntimeEventAck,
    RuntimeEventV1,
    ToolInvokeRequest,
    ToolInvokeResponse,
    VoiceSessionCreateRequest,
    VoiceSessionContextResponse,
    VoiceSessionEventResponse,
    VoiceSessionEventsResponse,
    VoiceSessionResponse,
    WebRTCParticipantTokenResponse,
)
from app.security.voice_runtime_auth import require_voice_runtime
from app.services.agent_compiler_service import AgentCompilerError, AgentCompilerService
from app.services.contact_resolution_service import ContactResolutionError
from app.services.tenant_feature_service import TenantFeatureDisabledError, TenantFeatureService, VOICE_RUNTIME_V2
from app.services.tool_dispatch_service import (
    ToolArgumentError,
    ToolDispatchService,
    ToolExecutionError,
    ToolNotAvailableError,
    ToolNotFoundError,
)
from app.services.voice_config_service import VoiceConfigService
from app.services.voice_runtime_dispatcher import VoiceRuntimeDispatcher
from app.services.voice_session_service import VoiceSessionError, VoiceSessionNotFoundError, VoiceSessionService
from app.services.voice_session_sip_service import VoiceSessionSipDialError, VoiceSessionSipService

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
        if body.channel == "sip":
            if body.purpose != "qa" or body.direction != "outbound" or not body.to_phone:
                raise VoiceSessionError("SIP sessions require purpose=qa, direction=outbound and to_phone.")
        elif body.to_phone is not None or body.direction != "internal":
            raise VoiceSessionError("to_phone/outbound are only valid for SIP QA sessions.")
        TenantFeatureService(db).require_enabled(context.tenant_id, VOICE_RUNTIME_V2)
        caller_phone = (
            body.to_phone
            if body.purpose == "qa" and body.channel == "sip" and body.qa_context_mode == "conversation"
            else body.caller_phone
        )
        session = VoiceSessionService(db).create(
            context.tenant_id, body.agent_id, channel=body.channel, direction=body.direction,
            idempotency_key=body.idempotency_key, contact_id=body.contact_id, lead_id=body.lead_id,
            caller_phone=caller_phone, variables=body.variables, purpose=body.purpose,
            qa_context_mode=body.qa_context_mode,
        )
        session = (
            await VoiceSessionSipService(db).dial(session, body.to_phone)
            if body.channel == "sip"
            else await VoiceRuntimeDispatcher(db).dispatch(session)
        )
        return VoiceSessionResponse.model_validate(session)
    except TenantFeatureDisabledError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (VoiceSessionError, ContactResolutionError, VoiceSessionSipDialError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


_QA_EVENT_FIELDS = {
    "voice.transcript.final": {"speaker", "text", "timestamp"},
    "session.context.resolved": {"contact_resolved", "lead_resolved", "campaign_resolved", "caller_known"},
    "session.context.enriched": {"contact_resolved", "lead_resolved", "source"},
    "session.context.tool_used": {"tool_key", "status", "duration_ms", "summary", "error_code"},
    "voice.session.dispatched": {"runtime_engine"},
    "voice.session.ended": {"end_reason"},
    "voice.session.failed": {"error_code"},
    "voice.session.cancelled": {"end_reason"},
    "voice.sip.dial.started": {"sip_route_id"},
    "voice.sip.answered": {"sip_call_id"},
    "voice.sip.busy": {"error_code"},
    "voice.sip.rejected": {"error_code"},
    "voice.sip.no_answer": {"error_code"},
    "voice.sip.failed": {"error_code"},
}


def _safe_qa_event_payload(event: VoiceSessionEvent) -> dict[str, str | int | bool | None]:
    allowed = _QA_EVENT_FIELDS.get(event.event_type, set())
    return {
        key: value
        for key, value in (event.payload_json or {}).items()
        if key in allowed and (value is None or isinstance(value, (str, int, bool)))
    }


def _mask_phone(value: str | None) -> str | None:
    if not value:
        return None
    return f"***{value[-4:]}"


@router.get("/api/v1/voice/sessions/{session_id}/events", response_model=VoiceSessionEventsResponse)
def list_voice_session_events(
    session_id: str,
    context: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> VoiceSessionEventsResponse:
    try:
        session = VoiceSessionService(db).get(session_id, tenant_id=context.tenant_id)
    except VoiceSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    resolved = SessionContextV1.model_validate(session.session_context_json or {})
    rows = db.scalars(
        select(VoiceSessionEvent)
        .where(
            VoiceSessionEvent.tenant_id == context.tenant_id,
            VoiceSessionEvent.voice_session_id == session.id,
        )
        .order_by(VoiceSessionEvent.occurred_at, VoiceSessionEvent.event_id)
    ).all()
    return VoiceSessionEventsResponse(
        session=VoiceSessionResponse.model_validate(session),
        context=VoiceSessionContextResponse(
            caller_phone=_mask_phone(resolved.caller.phone if resolved.caller else None),
            contact_id=resolved.contact.id if resolved.contact else None,
            lead_id=resolved.lead.id if resolved.lead else None,
            variables=resolved.variables,
        ),
        events=[
            VoiceSessionEventResponse(
                event_id=row.event_id,
                event_type=row.event_type,
                source=row.source,
                sequence=row.sequence,
                payload=_safe_qa_event_payload(row),
                occurred_at=row.occurred_at,
            )
            for row in rows
        ],
    )


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
        return AgentCompilerService(db).compile(
            session.agent, session.agent_version, session_id=session.id,
            context=session.session_context_json,
        )
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
    from app.services.voice_call_projection_service import VoiceCallProjectionService
    from app.services.voice_session_service import TRANSITIONS

    projector = VoiceCallProjectionService(db)
    try:
        session = service.get(session_id)
        allowed_payload = {
            key: value for key, value in body.payload.items()
            if key in {"livekit_job_id", "provider_session_id", "end_reason", "error_code", "speaker", "text", "timestamp", "participant_identity", "track_source"}
        }
        if body.event_type == "voice.transcript.final":
            if (allowed_payload.get("speaker") not in {"user", "assistant"}
                    or not isinstance(allowed_payload.get("text"), str)
                    or not allowed_payload["text"].strip()
                    or len(allowed_payload["text"]) > 10000):
                raise HTTPException(status_code=422, detail="Invalid final transcript")
        event, duplicate = service.record_event(session, body.event_type, source=body.source, event_id=body.event_id, sequence=body.sequence, payload=allowed_payload, occurred_at=body.occurred_at, commit=False)
        if duplicate:
            db.rollback()
            projector.reconcile_session(session_id, tenant_id=session.tenant_id)
            return RuntimeEventAck(duplicate=True)
        if "livekit_job_id" in allowed_payload:
            session.livekit_job_id = str(allowed_payload["livekit_job_id"])[:160]
        if "provider_session_id" in allowed_payload:
            session.provider_session_id = str(allowed_payload["provider_session_id"])[:255]
        if body.event_type == "voice.agent.ready" and session.runtime_ready_at is None:
            session.runtime_ready_at = body.occurred_at or datetime.now(UTC)
        if body.event_type == "voice.session.ended" and session.status == "connected":
            service.transition(session, "ending", commit=False)
        target = {
            "voice.session.started": "starting",
            "voice.session.connected": "connected",
            "voice.session.ended": "ended",
            "voice.session.failed": "failed",
        }.get(body.event_type)
        if target and target in TRANSITIONS.get(session.status, set()):
            service.transition(session, target, commit=False)
        if body.event_type == "voice.session.started" and session.started_at is not None:
            session.started_at = min(projector._utc(session.started_at), projector._utc(body.occurred_at))
        elif body.event_type == "voice.session.connected" and (
                session.ended_at is None or projector._utc(body.occurred_at) <= projector._utc(session.ended_at)):
            session.connected_at = min(projector._utc(session.connected_at), projector._utc(body.occurred_at)) if session.connected_at else projector._utc(body.occurred_at)
        elif body.event_type in {"voice.session.ended", "voice.session.failed"} and session.status in {"ended", "failed"}:
            session.ended_at = min(projector._utc(session.ended_at), projector._utc(body.occurred_at)) if session.ended_at else projector._utc(body.occurred_at)
        if body.event_type == "voice.session.ended":
            session.end_reason = str(allowed_payload.get("end_reason", "unknown"))[:40]
        elif body.event_type == "voice.session.failed":
            session.error_code = str(allowed_payload.get("error_code", "runtime_failed"))[:80]
        if session.crm_voice_call_id:
            call = db.get(CrmVoiceCall, session.crm_voice_call_id)
            if call is not None and call.tenant_id == session.tenant_id:
                now = body.occurred_at or datetime.now(UTC)
                if body.event_type == "voice.session.connected" and call.status == "answered":
                    call.status = "in_progress"
                elif body.event_type == "voice.session.ended" and call.status not in {
                    "busy", "rejected", "no_answer", "failed", "completed"
                }:
                    call.status = "completed" if call.answered_at else "no_answer"
                    call.ended_at = now
                    logger.info(
                        "LiveKit SIP outbound completed | tenant_id=%s | crm_voice_call_id=%s | voice_session_id=%s | livekit_room_name=%s | livekit_dispatch_id=%s | livekit_sip_trunk_id=%s | sip_participant_identity=%s | sip_call_id=%s",
                        session.tenant_id,
                        call.id,
                        session.id,
                        session.livekit_room_name,
                        session.livekit_dispatch_id,
                        session.livekit_sip_trunk_id,
                        session.livekit_sip_participant_identity,
                        session.sip_call_id,
                    )
                elif body.event_type == "voice.session.failed" and call.status not in {
                    "busy", "rejected", "no_answer", "failed", "completed"
                }:
                    call.status = "failed"
                    call.ended_at = now
        db.flush()
        projector.project_event(session_id, event, commit=False)
        db.commit()
        return RuntimeEventAck()
    except VoiceSessionNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VoiceSessionError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/api/v1/internal/voice-runtime/sessions/{session_id}/tools/{tool_key}/invoke",
    response_model=ToolInvokeResponse,
    dependencies=[Depends(require_voice_runtime)],
)
def invoke_runtime_tool(
    session_id: str, tool_key: str, body: ToolInvokeRequest, db: Session = Depends(get_db)
) -> ToolInvokeResponse:
    """Executes one tool call on behalf of a live VoiceSession. Re-resolves
    the session's own published binding from the database rather than
    trusting the compiled RuntimeSessionSpecV1 the runtime already holds --
    see ToolDispatchService for why."""
    try:
        result = ToolDispatchService(db).invoke(session_id, tool_key, body.arguments)
        db.commit()
        return ToolInvokeResponse(result=result)
    except VoiceSessionNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VoiceSessionError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ToolNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=f"tool_not_found:{exc}") from exc
    except ToolNotAvailableError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"tool_not_available:{exc}") from exc
    except ToolArgumentError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"tool_argument_invalid:{exc}") from exc
    except ToolExecutionError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"tool_execution_failed:{exc}") from exc
