"""Public callback request (POST /callback-requests) over the canonical runtime.

The request is still asynchronous: it validates, records ONE ``CrmVoiceCall`` (provider
``livekit_sip``: Telephony will place it) and consumes the one-shot token, then answers 202. The
call itself is placed later by the callback worker through Telephony, against the
ExperienceVersion's exact AgentVersion.

Rollout: with ``VOICE_RUNTIME_V2`` and ``LIVEKIT_SIP_OUTBOUND_V2`` both on for the tenant this
service handles the request; otherwise the request goes, unchanged, to the temporary legacy
runtime (removed in PR #137). The two paths are never mixed for one request.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.billing.public import BillingAccessGate, BillingError
from app.modules.crm.public import (
    VOICE_EXPERIENCE_CALLBACK_ORIGIN,
    CreateVoiceCallCommand,
    CrmFacade,
    CrmVoiceCalls,
)
from app.modules.identity.public import (
    LIVEKIT_SIP_OUTBOUND_V2,
    VOICE_EXPERIENCES,
    VOICE_RUNTIME_V2,
    FeatureFlags,
    TenantDirectory,
)
from app.modules.telephony.public import (
    CANONICAL_SIP_PROVIDER,
    CapacityFacade,
    SipRouteFacade,
    VoicePhoneValidationError,
    normalize_outbound_phone,
)
from app.modules.voice_experiences.application.launch_context import trusted_variables
from app.modules.voice_experiences.application.ports import VoiceRuntimePort
from app.modules.voice_experiences.domain.errors import PublicCallFailure, VoiceRuntimeUnavailable
from app.modules.voice_experiences.infrastructure.context_models import TenantVoiceContextField
from app.modules.voice_experiences.infrastructure.experience_models import (
    TenantVoiceExperience,
    TenantVoiceExperienceVersion,
)
from app.modules.voice_experiences.infrastructure.submission_models import (
    TenantVoiceContextSession,
    TenantVoiceExperienceSubmission,
    TenantVoiceExperienceSubmissionValue,
)

logger = logging.getLogger(__name__)


class _CapacityReached(Exception):
    def __init__(self, tenant_id: str, route_id: str, active_calls: int, limit: int) -> None:
        self.tenant_id = tenant_id
        self.route_id = route_id
        self.active_calls = active_calls
        self.limit = limit


def canonical_callbacks_enabled(db: Session, tenant_id: str) -> bool:
    flags = FeatureFlags(db)
    return flags.is_enabled(tenant_id, VOICE_RUNTIME_V2) and flags.is_enabled(tenant_id, LIVEKIT_SIP_OUTBOUND_V2)


class PublicCallbackService:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        runtime_factory: Callable[[Session], VoiceRuntimePort],
    ) -> None:
        self.session_factory = session_factory
        self.runtime_factory = runtime_factory

    def resolve_tenant(self, slug: str, context_token: str) -> str:
        token_hash = hashlib.sha256(context_token.encode()).hexdigest()
        with self.session_factory() as db:
            session = db.scalar(
                select(TenantVoiceContextSession).where(TenantVoiceContextSession.token_hash == token_hash)
            )
            experience = db.get(TenantVoiceExperience, session.experience_id) if session else None
            if session is None or experience is None or experience.slug != slug:
                raise PublicCallFailure(404, "experience_unavailable")
            return session.tenant_id

    def request(self, slug: str, context_token: str) -> dict[str, str]:
        tenant_id = self.resolve_tenant(slug, context_token)
        with self.session_factory() as db:
            enabled = canonical_callbacks_enabled(db, tenant_id)
        if not enabled:
            # Kill switch: calling is off. There is no other runtime to fall back to, and nothing
            # (token, call record, session) is consumed or created.
            raise PublicCallFailure(503, "call_unavailable")
        return self._request_canonical(slug, context_token, tenant_id)

    # -- canonical request ------------------------------------------------------------------------

    def _request_canonical(self, slug: str, context_token: str, tenant_id: str) -> dict[str, str]:
        token_hash = hashlib.sha256(context_token.encode()).hexdigest()
        now = datetime.now(UTC)
        self._precheck(tenant_id, token_hash)
        with self.session_factory() as db:
            try:
                with db.begin():
                    context_session = db.scalar(
                        select(TenantVoiceContextSession)
                        .where(TenantVoiceContextSession.token_hash == token_hash)
                        .with_for_update()
                    )
                    if context_session is None:
                        raise PublicCallFailure(404, "experience_unavailable")
                    experience = db.get(TenantVoiceExperience, context_session.experience_id)
                    version = db.get(TenantVoiceExperienceVersion, context_session.experience_version_id)
                    submission = db.get(TenantVoiceExperienceSubmission, context_session.submission_id)
                    if (
                        experience is None
                        or experience.slug != slug
                        or experience.status != "published"
                        or experience.published_version_id != context_session.experience_version_id
                        or version is None
                        or version.call_settings_json.get("mode") not in ("callback", "both")
                    ):
                        raise PublicCallFailure(404, "experience_unavailable")

                    calls = CrmVoiceCalls(db)
                    if calls.find_by_source_submission(context_session.submission_id, for_update=True) is not None:
                        return {"status": "accepted"}  # replay: one submission, one call record
                    if context_session.status != "active":
                        raise PublicCallFailure(409, "context_session_unavailable")
                    if self._utc(context_session.expires_at) <= now:
                        raise PublicCallFailure(410, "context_session_expired")
                    if submission is None or not submission.consent_accepted:
                        raise PublicCallFailure(409, "context_session_unavailable")
                    if not FeatureFlags(db).is_enabled(context_session.tenant_id, VOICE_EXPERIENCES):
                        raise PublicCallFailure(404, "experience_unavailable")
                    try:
                        route = SipRouteFacade(db).get_active_route(
                            context_session.tenant_id, for_update=True, require_livekit=True
                        )
                    except ValueError:
                        raise PublicCallFailure(503, "call_unavailable") from None

                    phone = self._destination(db, version, submission, route)
                    active_count = CapacityFacade(db).route_load(
                        tenant_id=context_session.tenant_id, route_id=route.id
                    )
                    if active_count >= route.max_concurrent_calls:
                        raise _CapacityReached(
                            context_session.tenant_id, route.id, active_count, route.max_concurrent_calls
                        )

                    call = calls.create(
                        CreateVoiceCallCommand(
                            tenant_id=context_session.tenant_id,
                            lead_id=submission.crm_lead_id,
                            contact_id=submission.crm_contact_id,
                            source_submission_id=submission.id,
                            sip_route_id=route.id,
                            provider=CANONICAL_SIP_PROVIDER,
                            origin=VOICE_EXPERIENCE_CALLBACK_ORIGIN,
                            direction="outbound",
                            status="requested",
                            to_phone=phone,
                            from_number=route.caller_id,
                        ),
                        flush=True,
                    )
                    if submission.crm_contact_id:
                        CrmFacade(db).stage_activity(
                            tenant_id=context_session.tenant_id,
                            lead_id=submission.crm_lead_id,
                            contact_id=submission.crm_contact_id,
                            activity_type="voice_call_requested",
                            title="Llamada saliente solicitada",
                            description="Solicitud creada desde una experiencia de voz publicada.",
                            occurred_at=now,
                            deduplication_key=f"voice-callback-request:{submission.id}",
                            payload={"voice_call_id": call.id, "provider": CANONICAL_SIP_PROVIDER, "status": "requested"},
                        )
                    if not context_session.mark_consumed(db, now=now, commit=False):
                        raise PublicCallFailure(409, "context_session_unavailable")
            except _CapacityReached as exc:
                CapacityFacade(db).record_capacity_reached(
                    tenant_id=exc.tenant_id,
                    route_id=exc.route_id,
                    active_calls=exc.active_calls,
                    max_concurrent_calls=exc.limit,
                )
                raise PublicCallFailure(429, "call_capacity_reached") from None
            except IntegrityError:
                db.rollback()
                if CrmVoiceCalls(db).find_by_source_submission(context_session.submission_id) is None:
                    raise
        return {"status": "accepted"}

    def _precheck(self, tenant_id: str, token_hash: str) -> None:
        """Everything that can be refused WITHOUT consuming the one-shot token: billing, an executable
        exact AgentVersion and a context that fits the runtime contract."""
        with self.session_factory() as db:
            tenant = TenantDirectory(db).get(tenant_id)
            if tenant is None:
                raise PublicCallFailure(503, "call_unavailable")
            try:
                BillingAccessGate(db).ensure_call_allowed_by_slug(tenant.slug)
            except BillingError:
                raise PublicCallFailure(503, "call_unavailable") from None
            context_session = db.scalar(
                select(TenantVoiceContextSession).where(TenantVoiceContextSession.token_hash == token_hash)
            )
            if context_session is None:
                raise PublicCallFailure(404, "experience_unavailable")
            if CrmVoiceCalls(db).find_by_source_submission(context_session.submission_id) is not None:
                return  # replay: the first request already validated and recorded it
            version = db.get(TenantVoiceExperienceVersion, context_session.experience_version_id)
            submission = db.get(TenantVoiceExperienceSubmission, context_session.submission_id)
            if version is None or submission is None or submission.tenant_id != tenant_id:
                raise PublicCallFailure(503, "call_unavailable")
            runtime = self.runtime_factory(db)
            try:
                runtime.require_runnable_agent(tenant_id, version.agent_id, version.agent_version_id)
                variables = trusted_variables(db, version, submission)
                runtime.validate_session_variables(dict(variables))
            except VoiceRuntimeUnavailable as exc:
                if exc.code == "invalid_context":
                    logger.warning(
                        "Voice experience callback context does not fit the runtime contract",
                        extra={
                            "error_code": "session_context_invalid",
                            "experience_version_id": version.id,
                            "field_count": len(variables),
                            "serialized_size": len(json.dumps(variables, default=str).encode()),
                        },
                    )
                raise PublicCallFailure(503, "call_unavailable") from None

    @staticmethod
    def _destination(db: Session, version, submission, route) -> str:
        phone_key = version.call_settings_json.get("phone_field_key")
        field = db.scalar(
            select(TenantVoiceContextField).where(
                TenantVoiceContextField.schema_id == version.context_schema_id,
                TenantVoiceContextField.key == phone_key,
                TenantVoiceContextField.field_type == "phone",
            )
        )
        value = db.scalar(
            select(TenantVoiceExperienceSubmissionValue.value_json).where(
                TenantVoiceExperienceSubmissionValue.submission_id == submission.id,
                TenantVoiceExperienceSubmissionValue.field_key == phone_key,
            )
        )
        if field is None or not isinstance(value, str):
            raise PublicCallFailure(422, "phone_unavailable")
        try:
            return normalize_outbound_phone(
                value,
                default_country=version.call_settings_json.get("default_country"),
                allowed_countries=set(route.allowed_countries),
            ).e164
        except VoicePhoneValidationError:
            raise PublicCallFailure(422, "destination_not_allowed") from None

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
