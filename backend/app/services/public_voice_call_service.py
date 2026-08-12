from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Callable
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.crm import CrmVoiceCall
from app.models.identity import Tenant
from app.models.integrations import TenantVoiceAgentConfig
from app.models.voice_experiences import TenantVoiceExperience, TenantVoiceExperienceVersion
from app.models.voice_submissions import (
    TenantVoiceContextSession,
    TenantVoiceExperienceSubmission,
    TenantVoiceExperienceSubmissionValue,
    TenantVoiceRuntimeCall,
)
from app.schemas.public_voice_calls import PublicVoiceCallResponse
from app.services.tenant_feature_service import TenantFeatureService, VOICE_EXPERIENCES
from app.services.tenant_usage_service import TenantUsageService
from app.services.voice_config_service import VoiceConfigService
from app.services.voice_experience_runtime_provider import (
    ProviderAmbiguousFailure,
    ProviderCallResult,
    ProviderDefiniteFailure,
    VoiceExperienceRuntimeProvider,
)

logger = logging.getLogger(__name__)


class PublicCallFailure(Exception):
    def __init__(self, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code


class PublicVoiceCallService:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        provider_timeout_seconds: float,
        reserved_lease_seconds: int,
        starting_lease_seconds: int,
    ) -> None:
        self.session_factory = session_factory
        self.provider_timeout_seconds = provider_timeout_seconds
        self.reserved_lease_seconds = reserved_lease_seconds
        self.starting_lease_seconds = starting_lease_seconds

    def resolve_tenant(self, slug: str, context_token: str) -> str:
        session, runtime = self._resolve_session_and_runtime(slug, context_token)
        return runtime.tenant_id if runtime else session.tenant_id

    def launch(self, slug: str, context_token: str) -> PublicVoiceCallResponse:
        session, runtime = self._resolve_session_and_runtime(slug, context_token)
        if runtime:
            return self._recover(runtime.id)
        self._precheck(session)
        runtime_id, owner = self._claim(slug, session.id)
        if not owner:
            return self._recover(runtime_id)
        if not self._cas_start(runtime_id, stale_only=False):
            return self._recover(runtime_id)
        return self._create_provider_call(runtime_id)

    def _resolve_session_and_runtime(self, slug: str, token: str) -> tuple[TenantVoiceContextSession, TenantVoiceRuntimeCall | None]:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.session_factory() as db:
            context_session = db.scalar(select(TenantVoiceContextSession).where(TenantVoiceContextSession.token_hash == token_hash))
            if context_session is None:
                raise PublicCallFailure(404, "experience_unavailable")
            experience = db.get(TenantVoiceExperience, context_session.experience_id)
            if experience is None or experience.slug != slug:
                raise PublicCallFailure(404, "experience_unavailable")
            runtime = db.scalar(select(TenantVoiceRuntimeCall).where(TenantVoiceRuntimeCall.context_session_id == context_session.id))
            db.expunge(context_session)
            if runtime:
                db.expunge(runtime)
            return context_session, runtime

    def _precheck(self, context_session: TenantVoiceContextSession) -> None:
        now = datetime.now(UTC)
        if context_session.status != "active":
            raise PublicCallFailure(409, "context_session_unavailable")
        if self._utc(context_session.expires_at) <= now:
            raise PublicCallFailure(410, "context_session_expired")
        with self.session_factory() as db:
            tenant = db.get(Tenant, context_session.tenant_id)
            if tenant is None:
                raise PublicCallFailure(503, "call_unavailable")
            try:
                TenantUsageService(db).ensure_tenant_can_start_call_by_slug(tenant.slug)
                version = db.get(TenantVoiceExperienceVersion, context_session.experience_version_id)
                if version is None:
                    raise ValueError
                agent = db.get(TenantVoiceAgentConfig, version.agent_config_id)
                if agent is None or agent.tenant_id != tenant.id or agent.status != "active":
                    raise ValueError
                config = VoiceConfigService(db).get_active_provider_config(tenant.id, agent.provider)
                if config.id != agent.provider_config_id or not config.webhook_secret_encrypted:
                    raise ValueError
            except Exception as exc:
                if isinstance(exc, PublicCallFailure):
                    raise
                raise PublicCallFailure(503, "call_unavailable") from None

    def _claim(self, slug: str, session_id: str) -> tuple[str, bool]:
        now = datetime.now(UTC)
        with self.session_factory() as db:
            try:
                with db.begin():
                    context_session = db.scalar(select(TenantVoiceContextSession).where(TenantVoiceContextSession.id == session_id).with_for_update())
                    if context_session is None:
                        raise PublicCallFailure(404, "experience_unavailable")
                    experience = db.scalar(select(TenantVoiceExperience).where(TenantVoiceExperience.id == context_session.experience_id).with_for_update())
                    version = db.get(TenantVoiceExperienceVersion, context_session.experience_version_id)
                    if context_session.status != "active":
                        raise PublicCallFailure(409, "context_session_unavailable")
                    if self._utc(context_session.expires_at) <= now:
                        raise PublicCallFailure(410, "context_session_expired")
                    if experience is None or experience.slug != slug or experience.status != "published":
                        raise PublicCallFailure(404, "experience_unavailable")
                    if experience.published_version_id != context_session.experience_version_id:
                        raise PublicCallFailure(409, "experience_version_changed")
                    if version is None or version.tenant_id != context_session.tenant_id or version.experience_id != experience.id:
                        raise PublicCallFailure(409, "experience_version_changed")
                    if not TenantFeatureService(db).is_enabled(context_session.tenant_id, VOICE_EXPERIENCES):
                        raise PublicCallFailure(404, "experience_unavailable")
                    submission = db.get(TenantVoiceExperienceSubmission, context_session.submission_id)
                    if submission is None or submission.tenant_id != context_session.tenant_id:
                        raise PublicCallFailure(409, "context_session_unavailable")
                    agent = db.get(TenantVoiceAgentConfig, version.agent_config_id)
                    if agent is None or agent.tenant_id != context_session.tenant_id:
                        raise PublicCallFailure(503, "call_unavailable")
                    crm_id, runtime_id = str(uuid4()), str(uuid4())
                    db.add(CrmVoiceCall(id=crm_id, tenant_id=context_session.tenant_id, lead_id=submission.crm_lead_id, contact_id=submission.crm_contact_id, provider="ultravox", provider_agent_id=agent.provider_agent_id, direction="webrtc", status="requested"))
                    db.flush()
                    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
                    result = db.execute(insert(TenantVoiceRuntimeCall).values(id=runtime_id, tenant_id=context_session.tenant_id, context_session_id=context_session.id, submission_id=submission.id, experience_id=experience.id, experience_version_id=version.id, agent_config_id=version.agent_config_id, crm_voice_call_id=crm_id, provider="ultravox", status="reserved", created_at=now).on_conflict_do_nothing(index_elements=["context_session_id"]).returning(TenantVoiceRuntimeCall.id)).scalar_one_or_none()
                    if result is None:
                        raise RuntimeError("claim_lost")
                    if not context_session.mark_consumed(db, now=now, commit=False):
                        raise PublicCallFailure(409, "context_session_unavailable")
                return runtime_id, True
            except RuntimeError as exc:
                db.rollback()
                if str(exc) != "claim_lost":
                    raise
        with self.session_factory() as db:
            runtime_id = db.scalar(select(TenantVoiceRuntimeCall.id).where(TenantVoiceRuntimeCall.context_session_id == session_id))
            if not runtime_id:
                raise PublicCallFailure(409, "call_state_conflict")
            return runtime_id, False

    def _cas_start(self, runtime_id: str, *, stale_only: bool) -> bool:
        now = datetime.now(UTC)
        conditions = [TenantVoiceRuntimeCall.id == runtime_id, TenantVoiceRuntimeCall.status == "reserved", TenantVoiceRuntimeCall.provider_attempt_started_at.is_(None)]
        if stale_only:
            conditions.append(TenantVoiceRuntimeCall.created_at < now - timedelta(seconds=self.reserved_lease_seconds))
        with self.session_factory() as db:
            won = db.execute(update(TenantVoiceRuntimeCall).where(*conditions).values(status="starting", provider_attempt_started_at=now).returning(TenantVoiceRuntimeCall.id)).scalar_one_or_none()
            db.commit()
            return won is not None

    def _load_provider_context(self, db: Session, runtime: TenantVoiceRuntimeCall):
        agent = db.get(TenantVoiceAgentConfig, runtime.agent_config_id)
        if agent is None or agent.tenant_id != runtime.tenant_id or agent.status != "active":
            raise PublicCallFailure(503, "call_unavailable")
        config_service = VoiceConfigService(db)
        try:
            config = config_service.get_active_provider_config(runtime.tenant_id, runtime.provider)
            if config.id != agent.provider_config_id or not config.webhook_secret_encrypted:
                raise ValueError
        except Exception:
            raise PublicCallFailure(503, "call_unavailable") from None
        provider = VoiceExperienceRuntimeProvider(config_service, timeout_seconds=self.provider_timeout_seconds)
        return agent, config, provider

    def _create_provider_call(self, runtime_id: str) -> PublicVoiceCallResponse:
        with self.session_factory() as db:
            runtime = db.get(TenantVoiceRuntimeCall, runtime_id)
            if runtime is None or runtime.status != "starting":
                raise PublicCallFailure(409, "call_state_conflict")
            agent, config, provider = self._load_provider_context(db, runtime)
            submission = db.get(TenantVoiceExperienceSubmission, runtime.submission_id)
            values = db.scalars(select(TenantVoiceExperienceSubmissionValue).where(TenantVoiceExperienceSubmissionValue.submission_id == runtime.submission_id)).all()
            user_context = {value.field_key: value.value_json for value in values}
            user_context["locale"] = submission.locale if submission else "es"
            metadata = {"voice_call_id": str(runtime.crm_voice_call_id), "runtime_call_id": str(runtime.id), "source": "voice_experience"}
        try:
            result = provider.create_webrtc_call(config, agent, metadata=metadata, user_context=user_context)
        except ProviderDefiniteFailure as exc:
            self._finish_attempt(runtime_id, "failed", failure_code=exc.failure_code)
            logger.warning("Voice runtime provider failure", extra={"runtime_call_id": runtime_id, "provider": "ultravox", "error_type": type(exc).__name__, "status_code": exc.status_code, "failure_code": exc.failure_code})
            raise PublicCallFailure(503, "call_provider_unavailable") from None
        except ProviderAmbiguousFailure as exc:
            self._finish_attempt(runtime_id, "unknown", failure_code="provider_ambiguous")
            logger.warning("Voice runtime provider ambiguous", extra={"runtime_call_id": runtime_id, "provider": "ultravox", "error_type": type(exc).__name__, "failure_code": "provider_ambiguous"})
            raise PublicCallFailure(503, "call_provider_unavailable") from None
        state = "ready" if result.provider_call_id and result.join_url else "unknown"
        self._finish_attempt(runtime_id, state, provider_call_id=result.provider_call_id, failure_code=None if state == "ready" else "provider_ambiguous")
        if state != "ready":
            raise PublicCallFailure(503, "call_provider_unavailable")
        return PublicVoiceCallResponse(status="ready", join_url=result.join_url)

    def _finish_attempt(self, runtime_id: str, state: str, *, provider_call_id: str | None = None, failure_code: str | None = None) -> None:
        with self.session_factory() as db:
            runtime = db.get(TenantVoiceRuntimeCall, runtime_id)
            origins = {
                "ready": {"starting", "unknown"},
                "connected": {"starting", "unknown", "ready"},
                "ended": {"starting", "unknown", "ready", "connected"},
                "failed": {"starting", "unknown"},
                "unknown": {"starting", "unknown"},
            }.get(state, set())
            if runtime is None or runtime.status not in origins:
                return
            runtime.status = state
            runtime.provider_call_id = provider_call_id or runtime.provider_call_id
            runtime.failure_code = failure_code
            crm = db.get(CrmVoiceCall, runtime.crm_voice_call_id)
            if crm and state == "ready":
                crm.provider_call_id = runtime.provider_call_id
                crm.status = "queued"
            elif crm and state == "connected":
                crm.provider_call_id = runtime.provider_call_id
                crm.status = "in_progress"
                runtime.connected_at = runtime.connected_at or datetime.now(UTC)
            elif crm and state == "ended":
                crm.provider_call_id = runtime.provider_call_id
                crm.status = "completed"
                runtime.ended_at = runtime.ended_at or datetime.now(UTC)
            db.commit()

    def _recover(self, runtime_id: str) -> PublicVoiceCallResponse:
        with self.session_factory() as db:
            runtime = db.get(TenantVoiceRuntimeCall, runtime_id)
            if runtime is None:
                raise PublicCallFailure(409, "call_state_conflict")
            if runtime.status in {"connected", "ended"}:
                raise PublicCallFailure(409, "call_already_started")
            if runtime.status == "failed":
                raise PublicCallFailure(409, "call_state_conflict")
            if runtime.status == "reserved":
                stale = self._utc(runtime.created_at) < datetime.now(UTC) - timedelta(seconds=self.reserved_lease_seconds)
                if not stale:
                    raise PublicCallFailure(409, "call_already_started")
                if self._cas_start(runtime.id, stale_only=True):
                    return self._create_provider_call(runtime.id)
                raise PublicCallFailure(409, "call_already_started")
            if runtime.status == "starting":
                started = self._utc(runtime.provider_attempt_started_at or runtime.created_at)
                if started >= datetime.now(UTC) - timedelta(seconds=self.starting_lease_seconds):
                    raise PublicCallFailure(409, "call_already_started")
                db.execute(update(TenantVoiceRuntimeCall).where(TenantVoiceRuntimeCall.id == runtime.id, TenantVoiceRuntimeCall.status == "starting").values(status="unknown", failure_code="provider_ambiguous"))
                db.commit()
                runtime.status = "unknown"
            agent, config, provider = self._load_provider_context(db, runtime)
            provider_call_id = runtime.provider_call_id
            attempted_at = runtime.provider_attempt_started_at
        try:
            if provider_call_id:
                result = provider.get_call(config, provider_call_id)
            else:
                found = provider.find_call_by_runtime_metadata(config, agent, runtime_call_id=runtime_id, attempted_at=attempted_at)
                if len(found) != 1:
                    if len(found) > 1:
                        self._finish_attempt(runtime_id, "failed", failure_code="provider_inconsistent")
                    raise PublicCallFailure(503, "call_provider_unavailable")
                result = found[0]
                if not result.provider_call_id:
                    raise PublicCallFailure(503, "call_provider_unavailable")
                self._finish_attempt(runtime_id, "unknown", provider_call_id=result.provider_call_id, failure_code="provider_ambiguous")
            if result.join_url and result.provider_call_id:
                provider_state = str(result.state or "").lower()
                if provider_state in {"ended", "completed"}:
                    self._finish_attempt(runtime_id, "ended", provider_call_id=result.provider_call_id)
                    raise PublicCallFailure(409, "call_already_started")
                if provider_state in {"joined", "connected", "in_progress"}:
                    self._finish_attempt(runtime_id, "connected", provider_call_id=result.provider_call_id)
                    raise PublicCallFailure(409, "call_already_started")
                self._finish_attempt(runtime_id, "ready", provider_call_id=result.provider_call_id)
                return PublicVoiceCallResponse(status="ready", join_url=result.join_url)
        except PublicCallFailure:
            raise
        except ProviderAmbiguousFailure:
            pass
        raise PublicCallFailure(503, "call_provider_unavailable")

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
