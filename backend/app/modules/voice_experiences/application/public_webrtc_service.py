"""Public WebRTC launch over the canonical runtime (VoiceSession + realtime room).

``context_token`` -> exact ExperienceVersion -> VoiceSession pinned to the
version's AgentVersion -> realtime room -> browser participant token.

The ledger row (TenantVoiceRuntimeCall) only holds the one-shot claim and the
correlation (CRM call, VoiceSession). It is created in a short transaction; no
network I/O (VoiceSession creation, room dispatch) ever runs under its row locks, and
every later step is idempotent so a crash at any point converges on one session.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.modules.billing.public import BillingAccessGate, BillingError
from app.modules.crm.public import CreateVoiceCallCommand, CrmVoiceCalls
from app.modules.identity.public import VOICE_EXPERIENCES, VOICE_RUNTIME_V2, FeatureFlags, TenantDirectory
from app.modules.voice_experiences.application.ports import VoiceRuntimePort
from app.modules.voice_experiences.domain.errors import PublicCallFailure, VoiceRuntimeUnavailable
from app.modules.voice_experiences.domain.limits import (
    LAUNCH_RUNTIME_CANONICAL,
    PUBLIC_CONTEXT_COLLECTION_MODES,
)
from app.modules.voice_experiences.domain.views import WebRTCJoin
from app.modules.voice_experiences.infrastructure.context_models import TenantVoiceContextField
from app.modules.voice_experiences.infrastructure.experience_models import (
    TenantVoiceExperience,
    TenantVoiceExperienceVersion,
)
from app.modules.voice_experiences.infrastructure.submission_models import (
    TenantVoiceContextSession,
    TenantVoiceExperienceSubmission,
    TenantVoiceExperienceSubmissionValue,
    TenantVoiceRuntimeCall,
)

logger = logging.getLogger(__name__)

_OPEN_STATES = ("reserved", "starting", "ready")


@dataclass(frozen=True, slots=True)
class PreparedLaunch:
    """What a launch will use, computed once and validated BEFORE the one-shot token is consumed."""

    provider: str
    variables: Mapping[str, object]


class PublicWebRTCService:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        runtime_factory: Callable[[Session], VoiceRuntimePort],
    ) -> None:
        self.session_factory = session_factory
        self.runtime_factory = runtime_factory

    # -- public API ----------------------------------------------------------

    def resolve_tenant(self, slug: str, context_token: str) -> str:
        session, runtime = self._resolve_session_and_runtime(slug, context_token)
        return runtime.tenant_id if runtime else session.tenant_id

    async def launch(self, slug: str, context_token: str) -> WebRTCJoin:
        session, runtime = self._resolve_session_and_runtime(slug, context_token)
        if runtime is not None:
            return await self._start(runtime.id)
        prepared = self._precheck(session)
        runtime_id, _owner = self._claim(slug, session.id, prepared.provider)
        return await self._start(runtime_id)

    # -- resolution / precheck ----------------------------------------------

    def _resolve_session_and_runtime(
        self, slug: str, token: str
    ) -> tuple[TenantVoiceContextSession, TenantVoiceRuntimeCall | None]:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.session_factory() as db:
            context_session = db.scalar(
                select(TenantVoiceContextSession).where(TenantVoiceContextSession.token_hash == token_hash)
            )
            if context_session is None:
                raise PublicCallFailure(404, "experience_unavailable")
            experience = db.get(TenantVoiceExperience, context_session.experience_id)
            if experience is None or experience.slug != slug:
                raise PublicCallFailure(404, "experience_unavailable")
            runtime = db.scalar(
                select(TenantVoiceRuntimeCall).where(
                    TenantVoiceRuntimeCall.context_session_id == context_session.id
                )
            )
            db.expunge(context_session)
            if runtime:
                db.expunge(runtime)
            return context_session, runtime

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def _precheck(self, context_session: TenantVoiceContextSession) -> PreparedLaunch:
        """Everything that must hold BEFORE the one-shot token is consumed: billing, flags, an
        executable agent and a submission that fits the runtime context contract."""
        if context_session.status != "active":
            raise PublicCallFailure(409, "context_session_unavailable")
        if self._utc(context_session.expires_at) <= datetime.now(UTC):
            raise PublicCallFailure(410, "context_session_expired")
        with self.session_factory() as db:
            tenant = TenantDirectory(db).get(context_session.tenant_id)
            if tenant is None:
                raise PublicCallFailure(503, "call_unavailable")
            flags = FeatureFlags(db)
            # Fail closed: the canonical runtime is the only WebRTC path (no legacy fallback).
            if not flags.is_enabled(tenant.id, VOICE_RUNTIME_V2):
                raise PublicCallFailure(503, "call_unavailable")
            try:
                BillingAccessGate(db).ensure_call_allowed_by_slug(tenant.slug)
            except BillingError:
                raise PublicCallFailure(503, "call_unavailable") from None
            version = db.get(TenantVoiceExperienceVersion, context_session.experience_version_id)
            submission = db.get(TenantVoiceExperienceSubmission, context_session.submission_id)
            if version is None or submission is None or submission.tenant_id != tenant.id:
                raise PublicCallFailure(503, "call_unavailable")
            runtime = self.runtime_factory(db)
            try:
                provider = runtime.require_runnable_agent(tenant.id, version.agent_id, version.agent_version_id)
                variables = self._trusted_variables(db, version, submission)
                runtime.validate_session_variables(dict(variables))
            except VoiceRuntimeUnavailable as exc:
                if exc.code == "invalid_context":
                    logger.warning(
                        "Voice experience context does not fit the runtime contract",
                        extra={
                            "error_code": "session_context_invalid",
                            "experience_version_id": version.id,
                            "field_count": len(variables),
                            "serialized_size": len(json.dumps(variables, default=str).encode()),
                        },
                    )
                raise PublicCallFailure(503, "call_unavailable") from None
            return PreparedLaunch(provider=provider, variables=variables)

    # -- claim ----------------------------------------------------------------

    def _claim(self, slug: str, session_id: str, provider: str) -> tuple[str, bool]:
        now = datetime.now(UTC)
        with self.session_factory() as db:
            try:
                with db.begin():
                    context_session = db.scalar(
                        select(TenantVoiceContextSession)
                        .where(TenantVoiceContextSession.id == session_id)
                        .with_for_update()
                    )
                    if context_session is None:
                        raise PublicCallFailure(404, "experience_unavailable")
                    experience = db.scalar(
                        select(TenantVoiceExperience)
                        .where(TenantVoiceExperience.id == context_session.experience_id)
                        .with_for_update()
                    )
                    version = db.get(TenantVoiceExperienceVersion, context_session.experience_version_id)
                    if context_session.status == "consumed":
                        runtime_id = db.scalar(
                            select(TenantVoiceRuntimeCall.id).where(
                                TenantVoiceRuntimeCall.context_session_id == context_session.id
                            )
                        )
                        if runtime_id:
                            return runtime_id, False
                        raise PublicCallFailure(409, "context_session_unavailable")
                    if context_session.status != "active":
                        raise PublicCallFailure(409, "context_session_unavailable")
                    if self._utc(context_session.expires_at) <= now:
                        raise PublicCallFailure(410, "context_session_expired")
                    if experience is None or experience.slug != slug or experience.status != "published":
                        raise PublicCallFailure(404, "experience_unavailable")
                    if experience.published_version_id != context_session.experience_version_id:
                        raise PublicCallFailure(409, "experience_version_changed")
                    if (
                        version is None
                        or version.tenant_id != context_session.tenant_id
                        or version.experience_id != experience.id
                    ):
                        raise PublicCallFailure(409, "experience_version_changed")
                    flags = FeatureFlags(db)
                    if not flags.is_enabled(context_session.tenant_id, VOICE_EXPERIENCES):
                        raise PublicCallFailure(404, "experience_unavailable")
                    if not flags.is_enabled(context_session.tenant_id, VOICE_RUNTIME_V2):
                        raise PublicCallFailure(503, "call_unavailable")
                    submission = db.get(TenantVoiceExperienceSubmission, context_session.submission_id)
                    if submission is None or submission.tenant_id != context_session.tenant_id:
                        raise PublicCallFailure(409, "context_session_unavailable")
                    crm_id, runtime_id = str(uuid4()), str(uuid4())
                    CrmVoiceCalls(db).create(
                        CreateVoiceCallCommand(
                            id=crm_id,
                            tenant_id=context_session.tenant_id,
                            lead_id=submission.crm_lead_id,
                            contact_id=submission.crm_contact_id,
                            provider=provider,
                            direction="webrtc",
                            status="requested",
                        ),
                        flush=True,
                    )
                    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
                    inserted = db.execute(
                        insert(TenantVoiceRuntimeCall)
                        .values(
                            id=runtime_id,
                            tenant_id=context_session.tenant_id,
                            context_session_id=context_session.id,
                            submission_id=submission.id,
                            experience_id=experience.id,
                            experience_version_id=version.id,
                            agent_config_id=version.agent_config_id,
                            crm_voice_call_id=crm_id,
                            provider=provider,
                            status="reserved",
                            launch_runtime=LAUNCH_RUNTIME_CANONICAL,
                            created_at=now,
                        )
                        .on_conflict_do_nothing(index_elements=["context_session_id"])
                        .returning(TenantVoiceRuntimeCall.id)
                    ).scalar_one_or_none()
                    if inserted is None:
                        raise RuntimeError("claim_lost")
                    if not context_session.mark_consumed(db, now=now, commit=False):
                        raise PublicCallFailure(409, "context_session_unavailable")
                return runtime_id, True
            except RuntimeError as exc:
                db.rollback()
                if str(exc) != "claim_lost":
                    raise
        with self.session_factory() as db:
            runtime_id = db.scalar(
                select(TenantVoiceRuntimeCall.id).where(TenantVoiceRuntimeCall.context_session_id == session_id)
            )
            if not runtime_id:
                raise PublicCallFailure(409, "call_state_conflict")
            return runtime_id, False

    # -- start / recover ------------------------------------------------------

    async def _start(self, runtime_id: str) -> WebRTCJoin:
        """Create-or-recover the VoiceSession, then make the room ready. Safe to run any
        number of times, concurrently or after a crash at any step."""
        with self.session_factory() as db:
            runtime = db.get(TenantVoiceRuntimeCall, runtime_id)
            if runtime is None:
                raise PublicCallFailure(409, "call_state_conflict")
            if runtime.launch_runtime != LAUNCH_RUNTIME_CANONICAL:
                # Explicit rollout discriminator: a pre-#135 direct-provider launch may have a provider
                # call in flight whatever its status says. It is never promoted to a VoiceSession.
                raise PublicCallFailure(409, "call_already_started")
            if runtime.status in {"failed", "unknown"}:
                raise PublicCallFailure(503, "call_provider_unavailable")
            tenant_id, crm_call_id = runtime.tenant_id, runtime.crm_voice_call_id
            voice_session_id = runtime.voice_session_id
            context_session_id = runtime.context_session_id

        creating = voice_session_id is None
        try:
            if creating:
                voice_session_id = self._create_session(runtime_id, context_session_id)
            creating = False
            self._attach_crm(voice_session_id, tenant_id, crm_call_id)
            with self.session_factory() as db:
                join = await self.runtime_factory(db).ensure_webrtc_join(voice_session_id, tenant_id)
        except VoiceRuntimeUnavailable as exc:
            # The ledger fails permanently only when the launch can never succeed: the
            # session cannot be created, or its room could not be dispatched. A transient
            # runtime problem (e.g. the room service unconfigured) leaves it retryable.
            if creating or exc.code == "dispatch_failed":
                self._fail(runtime_id, exc.code)  # ``not_configured`` stays retryable
            if exc.code == "terminal":
                raise PublicCallFailure(409, "call_already_started") from None
            if exc.code == "dispatch_failed":
                raise PublicCallFailure(503, "call_provider_unavailable") from None
            raise PublicCallFailure(503, "call_unavailable") from None
        self._mark_ready(runtime_id)
        return join

    def _attach_crm(self, voice_session_id: str, tenant_id: str, crm_call_id: str) -> None:
        with self.session_factory() as db:
            self.runtime_factory(db).attach_crm_call(voice_session_id, tenant_id, crm_call_id)

    def _create_session(self, runtime_id: str, context_session_id: str) -> str:
        with self.session_factory() as db:
            runtime = db.get(TenantVoiceRuntimeCall, runtime_id)
            version = db.get(TenantVoiceExperienceVersion, runtime.experience_version_id)
            submission = db.get(TenantVoiceExperienceSubmission, runtime.submission_id)
            if version is None or submission is None:
                raise VoiceRuntimeUnavailable("unavailable")
            variables = self._trusted_variables(db, version, submission)
            self.runtime_factory(db).validate_session_variables(dict(variables))
            args = dict(
                tenant_id=runtime.tenant_id,
                agent_id=version.agent_id,
                agent_version_id=version.agent_version_id,
                idempotency_key=f"voice-experience:{context_session_id}",
                contact_id=submission.crm_contact_id,
                lead_id=submission.crm_lead_id,
                variables=variables,
            )
            launch_session = self.runtime_factory(db).create_exact_session(**args)
        with self.session_factory() as db:
            db.execute(
                update(TenantVoiceRuntimeCall)
                .where(TenantVoiceRuntimeCall.id == runtime_id, TenantVoiceRuntimeCall.voice_session_id.is_(None))
                .values(
                    voice_session_id=launch_session.session_id,
                    provider=launch_session.provider or TenantVoiceRuntimeCall.provider,
                    status="starting",
                    provider_attempt_started_at=datetime.now(UTC),
                )
            )
            db.commit()
            stored = db.scalar(
                select(TenantVoiceRuntimeCall.voice_session_id).where(TenantVoiceRuntimeCall.id == runtime_id)
            )
        return stored or launch_session.session_id

    @staticmethod
    def _trusted_variables(
        db: Session, version: TenantVoiceExperienceVersion, submission: TenantVoiceExperienceSubmission
    ) -> dict[str, object]:
        """Business variables come only from the persisted submission, never from the request, and
        only for fields the Context Schema collects BEFORE the call. ``internal_only`` and
        ``collect_during_call`` values never reach the agent. The locale is session metadata
        (AgentVersion.language / ExperienceVersion.default_locale), not a variable: it must not
        spend one of SessionContextV1's 20 slots."""
        public_keys = {
            key
            for (key,) in db.execute(
                select(TenantVoiceContextField.key).where(
                    TenantVoiceContextField.schema_id == version.context_schema_id,
                    TenantVoiceContextField.collection_mode.in_(sorted(PUBLIC_CONTEXT_COLLECTION_MODES)),
                )
            ).all()
        }
        rows = db.scalars(
            select(TenantVoiceExperienceSubmissionValue).where(
                TenantVoiceExperienceSubmissionValue.submission_id == submission.id
            )
        ).all()
        return {row.field_key: row.value_json for row in rows if row.field_key in public_keys}

    def _fail(self, runtime_id: str, code: str) -> None:
        failure_code = "provider_connect_failed" if code == "dispatch_failed" else "configuration_unavailable"
        with self.session_factory() as db:
            db.execute(
                update(TenantVoiceRuntimeCall)
                .where(TenantVoiceRuntimeCall.id == runtime_id, TenantVoiceRuntimeCall.status.in_(_OPEN_STATES))
                .values(status="failed", failure_code=failure_code)
            )
            db.commit()

    def _mark_ready(self, runtime_id: str) -> None:
        with self.session_factory() as db:
            db.execute(
                update(TenantVoiceRuntimeCall)
                .where(TenantVoiceRuntimeCall.id == runtime_id, TenantVoiceRuntimeCall.status.in_(("reserved", "starting")))
                .values(status="ready")
            )
            db.commit()
