from __future__ import annotations

import logging
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.modules.agents.public import AgentCompilerError, AgentsFacade
from app.modules.identity.public import (
    VOICE_RUNTIME_V2,
    FeatureDisabledError,
    FeatureFlags,
)
from app.modules.telephony.public import SipDialError, TelephonyFacade
from app.modules.tools.public import (
    ToolArgumentError,
    ToolDispatchService,
    ToolExecutionError,
    ToolNotAvailableError,
    ToolNotFoundError,
)
from app.modules.voice.api.schemas import (
    ProviderCredentialResponse,
    RuntimeEventAck,
    RuntimeEventV1,
    ToolInvokeRequest,
    ToolInvokeResponse,
    VoiceSessionContextPreviewRequest,
    VoiceSessionContextResponse,
    VoiceSessionCreateRequest,
    VoiceSessionEventResponse,
    VoiceSessionEventsResponse,
    VoiceSessionResponse,
    WebRTCParticipantTokenResponse,
)
from app.modules.voice.application.context_resolution import ContactResolutionService
from app.modules.voice.application.runtime_dispatcher import VoiceRuntimeDispatcher
from app.modules.voice.application.runtime_events import RuntimeEventIngestor
from app.modules.voice.application.session_service import VoiceSessionService
from app.modules.voice.domain.errors import (
    ContactResolutionError,
    InvalidRuntimeEventError,
    VoiceSessionError,
    VoiceSessionNotFoundError,
)
from app.modules.voice.domain.lifecycle import TERMINAL_STATUSES
from app.modules.voice.domain.runtime_contracts import RuntimeSessionSpecV1
from app.modules.voice.domain.session_context import SessionContextV1
from app.modules.voice.infrastructure.models import VoiceSession, VoiceSessionEvent
from app.modules.voice_providers.public import (
    VoiceProviderError,
    VoiceProviderFacade,
    is_known_provider,
)
from app.security.voice_runtime_auth import require_voice_runtime

router = APIRouter(tags=["Voice Runtime"])
WRITE_ROLES = ["platform_admin", "tenant_admin"]
logger = logging.getLogger(__name__)


@router.post("/api/v1/voice/sessions/context-preview", response_model=SessionContextV1)
def preview_voice_session_context(
    body: VoiceSessionContextPreviewRequest,
    context: AuthContext = Depends(require_roles(WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> SessionContextV1:
    try:
        FeatureFlags(db).require_enabled(context.tenant_id, VOICE_RUNTIME_V2)
        return ContactResolutionService(db).resolve(
            tenant_id=context.tenant_id,
            phone=(body.to_phone if body.qa_context_mode == "conversation" and body.channel == "sip" else body.caller_phone),
            contact_id=body.contact_id,
            lead_id=body.lead_id,
            trusted_ids=True,
            source="outbound" if body.channel == "sip" else "webrtc",
            variables=body.variables,
        )
    except FeatureDisabledError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ContactResolutionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
        FeatureFlags(db).require_enabled(context.tenant_id, VOICE_RUNTIME_V2)
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
        if body.channel == "sip":
            # SIP belongs to Telephony: it dials this session through the
            # tenant's route and updates it in this same DB session.
            await TelephonyFacade(db).dial_qa_session(session.id, context.tenant_id, body.to_phone)
        else:
            session = await VoiceRuntimeDispatcher(db).dispatch(session)
        return VoiceSessionResponse.model_validate(session)
    except FeatureDisabledError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (VoiceSessionError, ContactResolutionError, SipDialError, ValueError) as exc:
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


def _is_terminal(db: Session, session: VoiceSession) -> bool:
    if session.status in TERMINAL_STATUSES or session.agent_id is None:
        return True
    return AgentsFacade(db).get_agent_status(session.tenant_id, session.agent_id) == "archived"


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
        FeatureFlags(db).require_enabled(context.tenant_id, VOICE_RUNTIME_V2)
        session = VoiceSessionService(db).get(session_id, tenant_id=context.tenant_id)
        if _is_terminal(db, session):
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
    except FeatureDisabledError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except VoiceSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VoiceSessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/v1/internal/voice-runtime/sessions/{session_id}/spec", response_model=RuntimeSessionSpecV1, dependencies=[Depends(require_voice_runtime)])
def get_runtime_session_spec(session_id: str, db: Session = Depends(get_db)) -> RuntimeSessionSpecV1:
    try:
        session = VoiceSessionService(db).get(session_id)
        if _is_terminal(db, session):
            raise VoiceSessionError("Voice session is terminal.")
        return AgentsFacade(db).compile_runtime_spec(
            session.tenant_id, session.agent_id, session.agent_version_id,
            session_id=session.id, context=session.session_context_json,
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
    if not is_known_provider(provider):
        raise HTTPException(status_code=422, detail="Unsupported voice provider.")
    try:
        session = VoiceSessionService(db).get(session_id)
    except VoiceSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice session not found.") from exc
    if session.provider != provider:
        raise HTTPException(status_code=404, detail="Provider is not associated with this voice session.")
    if _is_terminal(db, session):
        raise HTTPException(status_code=409, detail="Voice session is terminal.")
    # Tenant comes from the session, never from the runtime; Voice Providers
    # owns how the credential is stored and decrypted.
    try:
        credential = VoiceProviderFacade(db).resolve_runtime_credential(session.tenant_id, provider)
    except VoiceProviderError as exc:
        raise HTTPException(status_code=409, detail="provider_credentials_unavailable") from exc
    logger.info(
        "Voice runtime credential resolved",
        extra={"tenant_id": session.tenant_id, "voice_session_id": session.id, "provider": provider},
    )
    return ProviderCredentialResponse(
        provider=credential.provider, api_key=credential.api_key, base_url=credential.base_url
    )


@router.post("/api/v1/internal/voice-runtime/sessions/{session_id}/events", response_model=RuntimeEventAck, dependencies=[Depends(require_voice_runtime)])
def post_runtime_event(session_id: str, body: RuntimeEventV1, db: Session = Depends(get_db)) -> RuntimeEventAck:
    if body.session_id != session_id:
        raise HTTPException(status_code=422, detail="Event session_id does not match path")
    try:
        duplicate = RuntimeEventIngestor(db).ingest(
            session_id, event_type=body.event_type, source=body.source, event_id=body.event_id,
            sequence=body.sequence, payload=body.payload, occurred_at=body.occurred_at,
        )
        return RuntimeEventAck(duplicate=True) if duplicate else RuntimeEventAck()
    except InvalidRuntimeEventError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
        result = ToolDispatchService(db).invoke(session_id, tool_key, body.arguments, body.invocation_id)
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
