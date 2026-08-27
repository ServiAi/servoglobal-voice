from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Callable

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.crm import CrmActivity, CrmVoiceCall
from app.models.identity import Tenant
from app.models.integrations import TenantSipRoute, TenantVoiceAgentConfig
from app.models.voice_context import TenantVoiceContextField
from app.models.voice_experiences import TenantVoiceExperience, TenantVoiceExperienceVersion
from app.models.voice_submissions import (
    TenantVoiceContextSession,
    TenantVoiceExperienceSubmission,
    TenantVoiceExperienceSubmissionValue,
)
from app.schemas.public_voice_calls import PublicVoiceCallbackResponse
from app.services.public_voice_call_service import PublicCallFailure
from app.services.tenant_feature_service import TenantFeatureService
from app.services.tenant_usage_service import TenantUsageService
from app.services.voice_call_service import VoiceCallService
from app.services.voice_capacity_service import VoiceCapacityService
from app.services.voice_client import VoiceClient, VoiceClientConfig, VoiceSipRouteConfig
from app.services.voice_config_service import VoiceConfigService
from app.services.voice_phone_service import VoicePhoneValidationError, normalize_outbound_phone
from app.services.voice_sip_route_service import VoiceSipRouteService
from app.services.voice_webhook_service import VoiceWebhookService


logger = logging.getLogger(__name__)
CLAIM_BATCH_SIZE = 25


class _CapacityReached(Exception):
    def __init__(self, tenant_id: str, route_id: str, active_calls: int, limit: int) -> None:
        self.tenant_id = tenant_id
        self.route_id = route_id
        self.active_calls = active_calls
        self.limit = limit


class PublicVoiceCallbackService:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def resolve_tenant(self, slug: str, context_token: str) -> str:
        token_hash = hashlib.sha256(context_token.encode()).hexdigest()
        with self.session_factory() as db:
            session = db.scalar(
                select(TenantVoiceContextSession).where(
                    TenantVoiceContextSession.token_hash == token_hash
                )
            )
            experience = db.get(TenantVoiceExperience, session.experience_id) if session else None
            if session is None or experience is None or experience.slug != slug:
                raise PublicCallFailure(404, "experience_unavailable")
            return session.tenant_id

    def request(self, slug: str, context_token: str) -> PublicVoiceCallbackResponse:
        token_hash = hashlib.sha256(context_token.encode()).hexdigest()
        now = datetime.now(UTC)
        tenant_id = self.resolve_tenant(slug, context_token)
        with self.session_factory() as usage_db:
            tenant = usage_db.get(Tenant, tenant_id)
            if tenant is None:
                raise PublicCallFailure(503, "call_unavailable")
            try:
                TenantUsageService(usage_db).ensure_tenant_can_start_call_by_slug(tenant.slug)
            except HTTPException:
                raise PublicCallFailure(503, "call_unavailable") from None
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
                    version = db.get(
                        TenantVoiceExperienceVersion,
                        context_session.experience_version_id,
                    )
                    submission = db.get(
                        TenantVoiceExperienceSubmission, context_session.submission_id
                    )
                    if (
                        experience is None
                        or experience.slug != slug
                        or experience.status != "published"
                        or experience.published_version_id != context_session.experience_version_id
                        or version is None
                        or version.call_settings_json.get("mode") != "callback"
                    ):
                        raise PublicCallFailure(404, "experience_unavailable")

                    existing = db.scalar(
                        select(CrmVoiceCall)
                        .where(
                            CrmVoiceCall.source_submission_id == context_session.submission_id
                        )
                        .with_for_update()
                    )
                    if existing is not None:
                        if existing.status == "failed":
                            # A prior attempt failed (e.g. transient SIP error); let the
                            # worker pick it back up instead of dead-ending the customer.
                            existing.status = "requested"
                            existing.error_message = None
                            existing.provider_call_id = None
                            existing.provider_session_id = None
                            existing.provider_attempt_started_at = None
                            existing.started_at = None
                        return PublicVoiceCallbackResponse(status="accepted")
                    if context_session.status != "active":
                        raise PublicCallFailure(409, "context_session_unavailable")
                    if self._utc(context_session.expires_at) <= now:
                        raise PublicCallFailure(410, "context_session_expired")
                    if submission is None or not submission.consent_accepted:
                        raise PublicCallFailure(409, "context_session_unavailable")
                    if not TenantFeatureService(db).is_enabled(
                        context_session.tenant_id, "voice_experiences"
                    ):
                        raise PublicCallFailure(404, "experience_unavailable")
                    agent = db.get(TenantVoiceAgentConfig, version.agent_config_id)
                    config_service = VoiceConfigService(db)
                    if (
                        agent is None
                        or agent.tenant_id != context_session.tenant_id
                        or agent.status != "active"
                    ):
                        raise PublicCallFailure(503, "call_unavailable")
                    try:
                        provider_config = config_service.get_active_provider_config(
                            context_session.tenant_id, agent.provider
                        )
                        route = VoiceSipRouteService(
                            db, config_service.secret_manager
                        ).get_active_route(context_session.tenant_id, for_update=True)
                    except (HTTPException, ValueError):
                        raise PublicCallFailure(503, "call_unavailable") from None
                    if route.provider_config_id != provider_config.id:
                        raise PublicCallFailure(503, "call_unavailable")

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
                        phone = normalize_outbound_phone(
                            value,
                            default_country=version.call_settings_json.get("default_country"),
                            allowed_countries=set(route.allowed_countries_json),
                        )
                    except VoicePhoneValidationError:
                        raise PublicCallFailure(422, "destination_not_allowed") from None

                    active_count = VoiceCapacityService(db).active_calls(
                        tenant_id=context_session.tenant_id,
                        route_id=route.id,
                    )
                    if active_count >= route.max_concurrent_calls:
                        raise _CapacityReached(
                            context_session.tenant_id,
                            route.id,
                            active_count,
                            route.max_concurrent_calls,
                        )

                    call = CrmVoiceCall(
                        tenant_id=context_session.tenant_id,
                        lead_id=submission.crm_lead_id,
                        contact_id=submission.crm_contact_id,
                        source_submission_id=submission.id,
                        sip_route_id=route.id,
                        provider=agent.provider,
                        provider_agent_id=agent.provider_agent_id,
                        direction="outbound",
                        status="requested",
                        to_phone=phone.e164,
                        from_number=route.caller_id,
                    )
                    db.add(call)
                    db.flush()
                    if submission.crm_contact_id:
                        db.add(
                            CrmActivity(
                                tenant_id=context_session.tenant_id,
                                lead_id=submission.crm_lead_id,
                                contact_id=submission.crm_contact_id,
                                activity_type="voice_call_requested",
                                title="Llamada saliente solicitada",
                                description="Solicitud creada desde una experiencia de voz publicada.",
                                occurred_at=now,
                                deduplication_key=f"voice-callback-request:{submission.id}",
                                payload_json={
                                    "voice_call_id": call.id,
                                    "provider": agent.provider,
                                    "status": "requested",
                                },
                            )
                        )
                    if not context_session.mark_consumed(db, now=now, commit=False):
                        raise PublicCallFailure(409, "context_session_unavailable")
            except _CapacityReached as exc:
                VoiceCapacityService(db).record_capacity_reached(
                    tenant_id=exc.tenant_id,
                    route_id=exc.route_id,
                    active_calls=exc.active_calls,
                    max_concurrent_calls=exc.limit,
                )
                raise PublicCallFailure(429, "call_capacity_reached") from None
            except IntegrityError:
                db.rollback()
                existing = db.scalar(
                    select(CrmVoiceCall.id).where(
                        CrmVoiceCall.source_submission_id == context_session.submission_id
                    )
                )
                if existing is None:
                    raise
        return PublicVoiceCallbackResponse(status="accepted")

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class VoiceCallbackWorker:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        starting_lease_seconds: int = 120,
        reconcile_after_seconds: int = 30,
        max_active_seconds: int = 7200,
    ) -> None:
        self.session_factory = session_factory
        self.starting_lease_seconds = starting_lease_seconds
        self.reconcile_after_seconds = reconcile_after_seconds
        self.max_active_seconds = max_active_seconds

    def process_once(self) -> bool:
        self._recover_stale_starting()
        reconciled = self._reconcile_active()
        call_id = self._claim()
        if call_id is None:
            return reconciled
        self._start(call_id)
        return True

    def _reconcile_active(self) -> bool:
        now = datetime.now(UTC)
        reconcile_cutoff = now - timedelta(seconds=self.reconcile_after_seconds)
        with self.session_factory() as db:
            with db.begin():
                call = db.scalar(
                    select(CrmVoiceCall)
                    .where(
                        CrmVoiceCall.status.in_(("queued", "in_progress")),
                        CrmVoiceCall.provider_call_id.is_not(None),
                        CrmVoiceCall.updated_at < reconcile_cutoff,
                    )
                    .order_by(CrmVoiceCall.updated_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if call is None:
                    return False
                call.updated_at = now
                call_id = call.id

        timed_out = False
        with self.session_factory() as db:
            call = db.get(CrmVoiceCall, call_id)
            if call is None or call.status not in {"queued", "in_progress"}:
                return True
            started_at = call.started_at or call.provider_attempt_started_at or call.created_at
            timed_out = self._utc(started_at) < now - timedelta(seconds=self.max_active_seconds)
            if timed_out:
                provider_call = {
                    "callId": call.provider_call_id,
                    "ended": now.isoformat(),
                    "endReason": "system_error",
                }
            else:
                try:
                    config_service = VoiceConfigService(db)
                    provider_config = config_service.get_active_provider_config(
                        call.tenant_id, call.provider
                    )
                    provider_call = VoiceClient().get_call(
                        VoiceClientConfig(
                            provider=provider_config.provider,
                            api_key=config_service.decrypt_api_key(provider_config),
                            base_url=provider_config.base_url,
                        ),
                        provider_call_id=call.provider_call_id or "",
                    )
                except Exception as exc:
                    logger.warning(
                        "Voice callback reconciliation failed",
                        extra={
                            "voice_call_id": call.id,
                            "error_type": type(exc).__name__,
                        },
                    )
                    return True

            ended = provider_call.get("ended")
            joined = provider_call.get("joined")
            if not ended and not joined:
                return True
            provider_call = dict(provider_call)
            provider_call.setdefault("callId", call.provider_call_id)
            prior_status = call.status
            result = VoiceWebhookService(db).handle_provider_event(
                call.provider,
                {
                    "event": "call.ended" if ended else "call.joined",
                    "call": provider_call,
                },
            )
            if ended and result.get("status") == "processed":
                VoiceCapacityService(db).record_release(
                    tenant_id=call.tenant_id,
                    call_id=call.id,
                    prior_status=prior_status,
                    resulting_status=result["call_status"],
                    forced=timed_out,
                )
            if timed_out:
                call = db.get(CrmVoiceCall, call_id)
                if call is not None:
                    call.error_message = "Provider completion timeout."
                    db.commit()
            return True

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def _recover_stale_starting(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(seconds=self.starting_lease_seconds)
        with self.session_factory() as db:
            with db.begin():
                result = db.execute(
                    update(CrmVoiceCall)
                    .where(
                        CrmVoiceCall.status == "starting",
                        CrmVoiceCall.provider_attempt_started_at.is_not(None),
                        CrmVoiceCall.provider_attempt_started_at < cutoff,
                    )
                    .values(status="requested", provider_attempt_started_at=None)
                )
            if result.rowcount:
                logger.warning(
                    "Recovered voice callback calls stuck in starting",
                    extra={"recovered_count": result.rowcount},
                )

    def _claim(self) -> str | None:
        with self.session_factory() as db:
            with db.begin():
                candidates = db.scalars(
                    select(CrmVoiceCall)
                    .where(
                        CrmVoiceCall.status == "requested",
                        CrmVoiceCall.direction == "outbound",
                        CrmVoiceCall.source_submission_id.is_not(None),
                        CrmVoiceCall.sip_route_id.is_not(None),
                    )
                    .order_by(CrmVoiceCall.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(CLAIM_BATCH_SIZE)
                ).all()

                for call in candidates:
                    route = db.scalar(
                        select(TenantSipRoute)
                        .where(TenantSipRoute.id == call.sip_route_id)
                        .with_for_update()
                    )
                    if route is None or route.status != "active":
                        call.status = "failed"
                        call.error_message = "Outbound SIP route is unavailable."
                        return call.id
                    active_count = VoiceCapacityService(db).active_calls(
                        tenant_id=call.tenant_id,
                        route_id=route.id,
                    )
                    if active_count >= route.max_concurrent_calls:
                        # This tenant's route is at capacity; try the next
                        # oldest candidate instead of starving other tenants.
                        continue
                    call.status = "starting"
                    call.provider_attempt_started_at = datetime.now(UTC)
                    return call.id

                return None

    def _start(self, call_id: str) -> None:
        with self.session_factory() as db:
            call = db.get(CrmVoiceCall, call_id)
            if call is None or call.status != "starting":
                return
            config_service = VoiceConfigService(db)
            route_service = VoiceSipRouteService(db, config_service.secret_manager)
            client = VoiceClient()
            try:
                provider_config = config_service.get_active_provider_config(
                    call.tenant_id, call.provider
                )
                route = route_service.get_active_route(call.tenant_id)
                if route.id != call.sip_route_id or route.provider_config_id != provider_config.id:
                    raise ValueError("Outbound SIP route mismatch.")
                values = db.scalars(
                    select(TenantVoiceExperienceSubmissionValue).where(
                        TenantVoiceExperienceSubmissionValue.submission_id
                        == call.source_submission_id
                    )
                ).all()
                context = {
                    item.field_key: item.value_json
                    for item in values
                    if not any(
                        term in item.field_key.lower()
                        for term in ("key", "secret", "auth", "token", "password")
                    )
                }
                response = client.start_outbound_call(
                    VoiceClientConfig(
                        provider=provider_config.provider,
                        api_key=config_service.decrypt_api_key(provider_config),
                        base_url=provider_config.base_url,
                        default_language=provider_config.default_language,
                        default_timezone=provider_config.default_timezone,
                        sip_route=VoiceSipRouteConfig(
                            host=route.pbx_host,
                            port=route.pbx_port,
                            username=route.sip_username,
                            password=route_service.decrypt_password(route),
                            caller_id=route.caller_id,
                            default_country=route.default_country,
                            allowed_countries=tuple(route.allowed_countries_json),
                        ),
                    ),
                    to_phone=call.to_phone or "",
                    agent_id=call.provider_agent_id or "",
                    metadata={
                        "tenant_id": call.tenant_id,
                        "voice_call_id": call.id,
                        "source": "voice_experience_callback",
                    },
                    context=context,
                )
                normalized = client.normalize_provider_response(call.provider, response)
                call.provider_call_id = normalized.get("provider_call_id")
                call.provider_session_id = normalized.get("provider_session_id")
                call.status = "queued"
                call.started_at = datetime.now(UTC)
                call.error_message = None
                db.commit()
                VoiceCallService(db).record_integration_event(
                    tenant_id=call.tenant_id,
                    provider=call.provider,
                    event_type="voice_callback_started",
                    status="success",
                    metadata={
                        "voice_call_id": call.id,
                        "provider_call_id": call.provider_call_id,
                    },
                )
            except Exception as exc:
                call.status = "failed"
                call.error_message = client.sanitize_voice_error(exc)
                db.commit()
                logger.warning(
                    "Voice callback start failed",
                    extra={"voice_call_id": call.id, "error_type": type(exc).__name__},
                )
