"""Public callbacks over the canonical runtime (VoiceSession + Telephony + LiveKit SIP).

A callback is accepted asynchronously (202), then placed by the worker through Telephony against the
ExperienceVersion's exact AgentVersion, driving the SAME CrmVoiceCall. The provider runtime
(VoiceClient) must never be involved.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from cryptography.fernet import Fernet

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase
from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.integrations import TenantVoiceAgentConfig, TenantVoiceProviderConfig
from app.modules.agents.infrastructure.models import TenantAgent, TenantAgentVersion
from app.modules.crm.infrastructure.models import CrmVoiceCall
from app.modules.identity.application.feature_service import (
    LIVEKIT_SIP_OUTBOUND_V2,
    VOICE_RUNTIME_V2,
    TenantFeatureService,
)
from app.modules.identity.api.deps import get_current_auth_context
from app.modules.telephony.infrastructure.livekit_sip import LiveKitSipDialError
from app.modules.telephony.infrastructure.models import TenantSipRoute
from app.modules.telephony.public import TelephonyFacade
from app.modules.telephony.wiring import default_telephony_ports
from app.modules.voice.infrastructure.models import VoiceSession, VoiceSessionEvent
from app.modules.voice_experiences.application.callback_worker import CallbackWorker
from app.modules.voice_experiences.infrastructure.context_models import TenantVoiceContextField
from app.modules.voice_experiences.infrastructure.submission_models import (
    TenantVoiceContextSession,
    TenantVoiceExperienceSubmission,
    TenantVoiceExperienceSubmissionValue,
)
from app.modules.voice_experiences.infrastructure.voice_runtime_adapter import VoiceRuntimeAdapter
from test_outbound_voice_call_service import FakeSip, NeverReadyBackend, ReadyBackend
from app.modules.voice_experiences.api.public_router import get_public_rate_limiter, get_public_turnstile_verifier
from app.modules.identity.application.feature_service import VOICE_EXPERIENCES
from app.services.secret_manager_service import SecretManager
import test_public_voice_callbacks as callbacks_tests
import test_public_voice_experience_submissions as submissions_tests


class _Legacy:
    """The temporary provider runtime: counts how often the worker falls through to it."""

    def __init__(self) -> None:
        self.calls = 0

    def process_once(self) -> bool:
        self.calls += 1
        return False


class CanonicalCallbackTests(Integration2ATestCase):
    _seed_agent = callbacks_tests.PublicVoiceCallbackTests._seed_agent
    _seed_schema = callbacks_tests.PublicVoiceCallbackTests._seed_schema
    _seed_fields = callbacks_tests.PublicVoiceCallbackTests._seed_fields
    _experience_payload = callbacks_tests.PublicVoiceCallbackTests._experience_payload
    _publish = callbacks_tests.PublicVoiceCallbackTests._publish
    _body = callbacks_tests.PublicVoiceCallbackTests._body
    _post = callbacks_tests.PublicVoiceCallbackTests._post
    _request_callback = callbacks_tests.PublicVoiceCallbackTests._request_callback

    def setUp(self) -> None:
        self.original_encryption_key = settings.INTEGRATIONS_ENCRYPTION_KEY
        self.original_hash_secret = settings.VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET
        settings.INTEGRATIONS_ENCRYPTION_KEY = Fernet.generate_key().decode()
        settings.VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET = "test-rate-secret"
        super().setUp()
        self.limiter = submissions_tests._AllowLimiter()
        self.verifier = submissions_tests._Verifier()
        app.dependency_overrides[get_public_rate_limiter] = lambda: self.limiter
        app.dependency_overrides[get_public_turnstile_verifier] = lambda: self.verifier
        self.agent_id = self._seed_agent()
        self.schema_id = self._seed_schema()
        self._seed_fields()
        secrets = SecretManager()
        with SessionLocal() as db:
            features = TenantFeatureService(db)
            features.set_feature(
                self.tenant.id, VOICE_EXPERIENCES, True, {"max_experiences": 10, "max_context_fields": 20}, self.user.id
            )
            for key in (VOICE_RUNTIME_V2, LIVEKIT_SIP_OUTBOUND_V2):
                features.set_feature(self.tenant.id, key, True, {}, self.user.id)
            provider = TenantVoiceProviderConfig(
                tenant_id=self.tenant.id, provider="ultravox", status="active",
                api_key_encrypted=secrets.encrypt_secret("tenant-api-key"),
                webhook_secret_encrypted=secrets.encrypt_secret("tenant-webhook-secret"),
            )
            db.add(provider)
            db.flush()
            db.get(TenantVoiceAgentConfig, self.agent_id).provider_config_id = provider.id
            phone_field = db.scalar(
                select(TenantVoiceContextField).where(
                    TenantVoiceContextField.schema_id == self.schema_id,
                    TenantVoiceContextField.key == "mobile_number",
                )
            )
            phone_field.required = True
            db.add(
                TenantSipRoute(
                    tenant_id=self.tenant.id, provider_config_id=provider.id, status="active",
                    pbx_host="pbx.example.com", pbx_port=5060, sip_username="tenant-a",
                    sip_password_encrypted=secrets.encrypt_secret("test-sip-password"),
                    caller_id="+573001112233", default_country="CO", allowed_countries_json=["CO", "US"],
                    max_concurrent_calls=1, provision_status="active", desired_revision=1, applied_revision=1,
                    livekit_outbound_trunk_id="ST_callback", livekit_provision_status="active",
                    livekit_provisioned_at=datetime.now(UTC),
                )
            )
            db.commit()
        self.published = self._publish()
        self.legacy = _Legacy()
        # The provider runtime must never start a canonical callback.
        forbidden = patch(
            "app.services.voice_client.VoiceClient.start_outbound_call",
            side_effect=AssertionError("provider-originated call"),
        )
        forbidden.start()
        self.addCleanup(forbidden.stop)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_public_rate_limiter, None)
        app.dependency_overrides.pop(get_public_turnstile_verifier, None)
        settings.INTEGRATIONS_ENCRYPTION_KEY = self.original_encryption_key
        settings.VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET = self.original_hash_secret
        super().tearDown()

    # -- helpers -----------------------------------------------------------------------------------

    def _worker(self, sip, backend, *, starting_lease_seconds: int = 120) -> CallbackWorker:
        return CallbackWorker(
            SessionLocal,
            runtime_factory=lambda db: VoiceRuntimeAdapter(db, runtime_backend=backend),
            legacy=self.legacy,
            telephony_factory=lambda db: TelephonyFacade(
                db, ports=default_telephony_ports(db, sip_transport=sip, runtime_backend=backend)
            ),
            starting_lease_seconds=starting_lease_seconds,
        )

    def _run(self, worker: CallbackWorker) -> bool:
        return asyncio.run(worker.process_once())

    def _token(self) -> str:
        app.dependency_overrides.pop(get_current_auth_context, None)  # the visitor is anonymous
        response = self._post()
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["context_token"]

    def _accepted_callback(self) -> str:
        token = self._token()
        response = self._request_callback(token)
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json(), {"status": "accepted"})
        return token

    def _call(self) -> CrmVoiceCall:
        with SessionLocal() as db:
            return db.scalars(select(CrmVoiceCall)).one()

    def _canonical_agent(self) -> tuple[str, str]:
        with SessionLocal() as db:
            version = db.scalars(
                select(TenantAgentVersion).where(TenantAgentVersion.voice_agent_config_id == self.agent_id)
            ).one()
            return version.agent_id, version.id

    def _counts(self) -> tuple[int, int]:
        with SessionLocal() as db:
            return db.query(CrmVoiceCall).count(), db.query(VoiceSession).count()

    # -- request ------------------------------------------------------------------------------------

    def test_request_records_one_canonical_call_and_stays_asynchronous(self) -> None:
        token = self._accepted_callback()

        call = self._call()
        self.assertEqual((call.provider, call.status, call.direction), ("livekit_sip", "requested", "outbound"))
        self.assertEqual(call.to_phone, "+573001112233")
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(TenantVoiceContextSession)).one().status, "consumed")
            self.assertEqual(db.query(VoiceSession).count(), 0)  # nothing placed yet: the worker's job
        self.assertEqual(self._request_callback(token).json(), {"status": "accepted"})  # replay
        self.assertEqual(self._counts(), (1, 0))

    def test_request_response_exposes_nothing_internal(self) -> None:
        response = self._request_callback(self._token())
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"status": "accepted"})
        for forbidden in ("voice_session", "sip_call", "agent_version", "tenant_id", "phone", "provider", "room"):
            self.assertNotIn(forbidden, response.text)

    # -- happy path / exact version -----------------------------------------------------------------

    def test_worker_places_the_call_through_telephony_with_one_call_one_session_one_dial(self) -> None:
        self._accepted_callback()
        agent_id, version_id = self._canonical_agent()
        order: list[str] = []
        sip, backend = FakeSip(order), ReadyBackend(order)

        self.assertTrue(self._run(self._worker(sip, backend)))

        self.assertEqual(order, ["dispatch", "ready", "dial"])  # runtime ready BEFORE the SIP leg
        self.assertEqual(sip.calls, 1)
        self.assertEqual(sip.last_kwargs["trunk_id"], "ST_callback")
        self.assertEqual(sip.last_kwargs["to_phone"], "+573001112233")
        with SessionLocal() as db:
            call = db.scalars(select(CrmVoiceCall)).one()
            session = db.scalars(select(VoiceSession)).one()
            self.assertEqual(db.query(CrmVoiceCall).count(), 1)  # the request's own record, no second one
            self.assertEqual((call.status, call.provider), ("answered", "livekit_sip"))
            self.assertEqual(
                (session.channel, session.direction, session.purpose, session.agent_id, session.agent_version_id),
                ("sip", "outbound", "production", agent_id, version_id),
            )
            self.assertEqual(session.crm_voice_call_id, call.id)
            self.assertEqual(session.sip_call_id, "SC_1")
            self.assertEqual(session.sip_route_id, call.sip_route_id)
        self.assertEqual(self.legacy.calls, 0)

    def test_the_call_uses_the_experience_versions_exact_agent_version(self) -> None:
        self._accepted_callback()
        agent_id, v1 = self._canonical_agent()
        with SessionLocal() as db:  # the Agent publishes v2 after the request was accepted
            v2 = TenantAgentVersion(
                agent_id=agent_id, tenant_id=self.tenant.id, version=2, status="published", language="es",
                timezone="America/Bogota", identity_json={"name": "Safe agent"},
                instructions_json={"system_prompt": "v2"}, behavior_json={},
                runtime_binding_json={"pipeline_type": "realtime", "realtime": {"provider": "ultravox"}},
                voice_agent_config_id=self.agent_id, published_at=datetime.now(UTC),
            )
            db.add(v2)
            db.flush()
            db.get(TenantAgentVersion, v1).status = "superseded"
            db.get(TenantAgent, agent_id).published_version_id = v2.id
            db.commit()
        order: list[str] = []

        self._run(self._worker(FakeSip(order), ReadyBackend(order)))

        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(VoiceSession)).one().agent_version_id, v1)

    def test_agent_archived_between_request_and_worker_fails_the_call_without_dialing(self) -> None:
        self._accepted_callback()
        agent_id, _ = self._canonical_agent()
        with SessionLocal() as db:
            db.get(TenantAgent, agent_id).status = "archived"
            db.commit()
        order: list[str] = []
        sip = FakeSip(order)

        self._run(self._worker(sip, ReadyBackend(order)))

        self.assertEqual(sip.calls, 0)
        self.assertEqual(order, [])  # no room, no SIP, no provider call
        with SessionLocal() as db:
            call = db.scalars(select(CrmVoiceCall)).one()
            self.assertEqual((call.status, call.error_message), ("failed", "agent_unavailable"))
            self.assertEqual(db.query(VoiceSession).count(), 0)
        self.assertEqual(self.legacy.calls, 0)

    def test_missing_provenance_fails_closed_instead_of_using_the_current_agent(self) -> None:
        self._accepted_callback()
        with SessionLocal() as db:
            call = db.scalars(select(CrmVoiceCall)).one()
            call.source_submission_id = None  # provenance lost
            db.commit()
        order: list[str] = []
        sip = FakeSip(order)

        self._run(self._worker(sip, ReadyBackend(order)))

        self.assertEqual(sip.calls, 0)
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(CrmVoiceCall)).one().status, "requested")  # not even claimable
            self.assertEqual(db.query(VoiceSession).count(), 0)

    # -- trusted context ----------------------------------------------------------------------------

    def test_session_context_comes_from_the_trusted_submission(self) -> None:
        token = self._accepted_callback()
        with SessionLocal() as db:
            submission = db.scalars(select(TenantVoiceExperienceSubmission)).one()
            contact_id, lead_id = submission.crm_contact_id, submission.crm_lead_id
            self.assertTrue(contact_id and lead_id)
            schema_id = db.scalars(select(TenantVoiceContextSession)).one().context_schema_id
            for position, (key, mode) in enumerate((("hidden_note", "internal_only"), ("live_note", "collect_during_call"))):
                db.add(TenantVoiceContextField(
                    tenant_id=self.tenant.id, schema_id=schema_id, key=key, label=key, field_type="text",
                    collection_mode=mode, required=False, position=300 + position, sensitivity="standard",
                    validation_json={}, options_json=[],
                ))
                db.add(TenantVoiceExperienceSubmissionValue(
                    tenant_id=self.tenant.id, submission_id=submission.id, field_key=key, field_type="text", value_json="x",
                ))
            db.commit()
        order: list[str] = []

        self._run(self._worker(FakeSip(order), ReadyBackend(order)))

        with SessionLocal() as db:
            context = db.scalars(select(VoiceSession)).one().session_context_json
        self.assertEqual(context["source"], "outbound")
        self.assertEqual(context["contact"]["id"], contact_id)
        self.assertEqual(context["lead"]["id"], lead_id)
        self.assertEqual(context["caller"]["phone"], "+573001112233")  # the destination of an outbound call
        variables = context["variables"]
        self.assertEqual(variables["full_name"], "Ana")
        for absent in ("locale", "hidden_note", "live_note"):
            self.assertNotIn(absent, variables)
        self.assertNotIn(token, str(context))

    # -- replay / recovery ---------------------------------------------------------------------------

    def test_repeated_worker_runs_never_duplicate_the_session_or_the_dial(self) -> None:
        self._accepted_callback()
        order: list[str] = []
        sip, backend = FakeSip(order), ReadyBackend(order)
        worker = self._worker(sip, backend)

        for _ in range(3):
            self._run(worker)

        self.assertEqual((sip.calls, self._counts()), (1, (1, 1)))

    def test_a_worker_that_died_before_any_session_resumes_the_same_call(self) -> None:
        self._accepted_callback()
        with SessionLocal() as db:  # claimed (starting) and then the worker died
            call = db.scalars(select(CrmVoiceCall)).one()
            call.status = "starting"
            call.provider_attempt_started_at = datetime.now(UTC) - timedelta(minutes=10)
            db.commit()
        order: list[str] = []
        sip = FakeSip(order)

        self._run(self._worker(sip, ReadyBackend(order)))

        self.assertEqual((sip.calls, self._counts()), (1, (1, 1)))

    def test_a_worker_that_died_after_session_correlation_continues_the_same_session(self) -> None:
        self._accepted_callback()
        call = self._call()
        agent_id, version_id = self._canonical_agent()
        with SessionLocal() as db:
            from app.modules.voice.public import VoiceTelephonyFacade

            voice = VoiceTelephonyFacade(db)
            with SessionLocal() as sub:
                submission_id = sub.scalars(select(TenantVoiceExperienceSubmission)).one().id
            session = voice.create_outbound_sip_session_from_agent_version(
                self.tenant.id, agent_id, version_id,
                idempotency_key=f"voice-experience-callback:{submission_id}",
                contact_id=call.contact_id, lead_id=call.lead_id, caller_phone="+573001112233",
            )
            voice.correlate_crm_call(session.id, self.tenant.id, call.id)
            db.commit()
            crashed_session_id = session.id
        with SessionLocal() as db:
            row = db.get(CrmVoiceCall, call.id)
            row.status = "starting"
            row.provider_attempt_started_at = datetime.now(UTC) - timedelta(minutes=10)
            db.commit()
        order: list[str] = []
        sip = FakeSip(order)

        self._run(self._worker(sip, ReadyBackend(order)))

        self.assertEqual((sip.calls, self._counts()), (1, (1, 1)))
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(VoiceSession)).one().id, crashed_session_id)
            self.assertEqual(db.scalars(select(CrmVoiceCall)).one().status, "answered")

    def test_a_started_sip_attempt_is_never_redialed(self) -> None:
        self._accepted_callback()
        order: list[str] = []
        sip, backend = FakeSip(order), ReadyBackend(order)
        self._run(self._worker(sip, backend))  # places the call: dial.started + answered
        self.assertEqual(sip.calls, 1)
        call = self._call()
        with SessionLocal() as db:  # the outcome never reached the CRM: crash right after the attempt began
            session = db.scalars(select(VoiceSession)).one()
            self.assertIsNotNone(session.livekit_sip_participant_identity)
            self.assertTrue(db.scalars(select(VoiceSessionEvent).where(VoiceSessionEvent.event_type == "voice.sip.dial.started")).all())
            row = db.get(CrmVoiceCall, call.id)
            row.status = "starting"
            row.provider_call_id = None
            row.provider_attempt_started_at = datetime.now(UTC) - timedelta(minutes=10)
            db.commit()

        self._run(self._worker(sip, backend))

        self.assertEqual(sip.calls, 1)  # no blind redial
        self.assertEqual(self._counts(), (1, 1))
        self.assertEqual(self._call().status, "dialing")  # an attempt is in flight: left for reconciliation

    # -- capacity ---------------------------------------------------------------------------------

    def _occupy_route(self, *, legacy: bool) -> str:
        """One channel of the (max 1) route held by the other runtime."""
        with SessionLocal() as db:
            route = db.scalars(select(TenantSipRoute)).one()
            if legacy:
                row = CrmVoiceCall(
                    tenant_id=self.tenant.id, sip_route_id=route.id, provider="ultravox", direction="outbound",
                    status="in_progress", to_phone="+573009999999", from_number=route.caller_id,
                )
            else:
                row = VoiceSession(
                    tenant_id=self.tenant.id, channel="sip", direction="outbound", purpose="production",
                    runtime_engine="livekit", pipeline_type="realtime", provider="ultravox", status="connected",
                    sip_route_id=route.id,
                )
            db.add(row)
            db.commit()
            return row.id

    def test_a_full_route_defers_an_accepted_callback_instead_of_losing_it(self) -> None:
        for legacy in (False, True):
            with self.subTest(blocker="legacy callback" if legacy else "canonical session"):
                with SessionLocal() as db:
                    for model in (VoiceSession, CrmVoiceCall, TenantVoiceContextSession, TenantVoiceExperienceSubmission):
                        db.query(model).delete()
                    db.commit()
                token = self._token()  # fresh submission
                self._accepted_callback_for(token)
                blocker = self._occupy_route(legacy=legacy)
                order: list[str] = []
                sip = FakeSip(order)
                worker = self._worker(sip, ReadyBackend(order))

                self._run(worker)
                self._run(worker)

                self.assertEqual(sip.calls, 0)
                with SessionLocal() as db:
                    call = db.scalars(
                        select(CrmVoiceCall).where(CrmVoiceCall.provider == "livekit_sip")
                    ).one()
                    self.assertEqual(call.status, "requested")  # retryable, not failed
                    self.assertEqual(db.query(VoiceSession).filter(VoiceSession.channel == "sip").count(), 0 if legacy else 1)
                with SessionLocal() as db:  # capacity frees up
                    if legacy:
                        db.get(CrmVoiceCall, blocker).status = "completed"
                    else:
                        db.get(VoiceSession, blocker).status = "ended"
                    db.commit()

                self._run(worker)

                self.assertEqual(sip.calls, 1)
                with SessionLocal() as db:
                    self.assertEqual(
                        db.scalars(select(CrmVoiceCall).where(CrmVoiceCall.provider == "livekit_sip")).one().status,
                        "answered",
                    )

    def _accepted_callback_for(self, token: str) -> None:
        response = self._request_callback(token)
        self.assertEqual(response.status_code, 202, response.text)

    def test_the_current_callback_does_not_count_against_itself(self) -> None:
        self._accepted_callback()  # max_concurrent_calls = 1, nothing else active
        order: list[str] = []
        sip = FakeSip(order)

        self._run(self._worker(sip, ReadyBackend(order)))

        self.assertEqual(sip.calls, 1)  # its own "starting" record did not fill the single channel
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(CrmVoiceCall)).one().status, "answered")

    # -- failures -----------------------------------------------------------------------------------

    def test_sip_failures_use_the_telephony_status_mapping(self) -> None:
        for sip_code, expected in ((486, "busy"), (603, "rejected"), (408, "no_answer"), (500, "failed")):
            with self.subTest(sip_code=sip_code):
                with SessionLocal() as db:
                    for model in (VoiceSessionEvent, VoiceSession, CrmVoiceCall, TenantVoiceContextSession, TenantVoiceExperienceSubmission):
                        db.query(model).delete()
                    db.commit()
                self._accepted_callback()
                order: list[str] = []
                sip = FakeSip(order, LiveKitSipDialError(expected, sip_code))

                self._run(self._worker(sip, ReadyBackend(order)))

                self.assertEqual(sip.calls, 1)
                with SessionLocal() as db:
                    self.assertEqual(db.scalars(select(CrmVoiceCall)).one().status, expected)
                    self.assertEqual(db.scalars(select(VoiceSession)).one().status, "failed")

    def test_runtime_not_ready_never_dials_and_fails_session_and_call(self) -> None:
        self._accepted_callback()
        order: list[str] = []
        sip, backend = FakeSip(order), NeverReadyBackend(order)

        with patch.object(settings, "LIVEKIT_SIP_RUNTIME_READY_TIMEOUT_SECONDS", 0.01):
            self._run(self._worker(sip, backend))

        self.assertEqual(sip.calls, 0)
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(CrmVoiceCall)).one().status, "failed")
            self.assertEqual(db.scalars(select(VoiceSession)).one().status, "failed")
        self.assertEqual(len(backend.closed), 1)  # room cleanup attempted

    # -- request-time refusals (nothing consumed) -------------------------------------------------

    def test_a_route_without_a_livekit_trunk_refuses_the_request_without_consuming_the_token(self) -> None:
        with SessionLocal() as db:
            db.scalars(select(TenantSipRoute)).one().livekit_outbound_trunk_id = None
            db.commit()
        token = self._token()

        response = self._request_callback(token)

        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"], {"code": "call_unavailable"})
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(TenantVoiceContextSession)).one().status, "active")
            self.assertEqual(db.query(CrmVoiceCall).count(), 0)

    def test_an_archived_agent_or_an_oversized_context_refuses_before_consuming_the_token(self) -> None:
        agent_id, _ = self._canonical_agent()
        token = self._token()
        with SessionLocal() as db:
            db.get(TenantAgent, agent_id).status = "archived"
            db.commit()
        self.assertEqual(self._request_callback(token).status_code, 503)
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(TenantVoiceContextSession)).one().status, "active")
            db.get(TenantAgent, agent_id).status = "active"
            submission = db.scalars(select(TenantVoiceExperienceSubmission)).one()
            schema_id = db.scalars(select(TenantVoiceContextSession)).one().context_schema_id
            db.add(TenantVoiceContextField(
                tenant_id=self.tenant.id, schema_id=schema_id, key="big_answer", label="b", field_type="text",
                collection_mode="ask_if_missing", required=False, position=400, sensitivity="standard",
                validation_json={}, options_json=[],
            ))
            db.add(TenantVoiceExperienceSubmissionValue(
                tenant_id=self.tenant.id, submission_id=submission.id, field_key="big_answer", field_type="text",
                value_json="x" * 4500,
            ))
            db.commit()

        response = self._request_callback(token)

        self.assertEqual((response.status_code, response.json()["detail"]), (503, {"code": "call_unavailable"}))
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(TenantVoiceContextSession)).one().status, "active")
            self.assertEqual((db.query(CrmVoiceCall).count(), db.query(VoiceSession).count()), (0, 0))

    # -- rollout / rollback -----------------------------------------------------------------------

    def test_with_the_canonical_flags_off_the_request_stays_on_the_legacy_runtime(self) -> None:
        with SessionLocal() as db:
            features = TenantFeatureService(db)
            for key in (VOICE_RUNTIME_V2, LIVEKIT_SIP_OUTBOUND_V2):
                features.set_feature(self.tenant.id, key, False, {}, self.user.id)

        self._accepted_callback()

        call = self._call()
        self.assertEqual(call.provider, "ultravox")  # provider-originated: the legacy worker's call
        order: list[str] = []
        sip = FakeSip(order)
        self._run(self._worker(sip, ReadyBackend(order)))
        self.assertEqual((sip.calls, self.legacy.calls), (0, 1))  # the canonical worker did not claim it
        self.assertEqual(self._call().status, "requested")

    def test_the_legacy_worker_never_claims_a_canonical_call(self) -> None:
        from app.modules.voice_experiences.infrastructure.legacy_runtime.callback_compat import VoiceCallbackWorker

        self._accepted_callback()
        VoiceCallbackWorker(SessionLocal).process_once()  # would fail/redirect it if it touched it
        self.assertEqual(self._call().status, "requested")

    def test_a_provider_webhook_does_not_mutate_a_canonical_call(self) -> None:
        self._accepted_callback()
        order: list[str] = []
        self._run(self._worker(FakeSip(order), ReadyBackend(order)))
        call = self._call()

        payload = {"event": "call.ended", "call": {"callId": "x", "metadata": {"voice_call_id": call.id}}}
        raw = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = datetime.now(UTC).isoformat()
        signature = hmac.new(b"tenant-webhook-secret", raw + timestamp.encode(), hashlib.sha256).hexdigest()
        response = self.client.post(
            "/api/v1/voice/webhook/ultravox",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "x-ultravox-webhook-timestamp": timestamp,
                "x-ultravox-webhook-signature": signature,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)  # even a correctly SIGNED event is ignored
        self.assertEqual(response.json(), {"status": "ignored", "processed": False})
        after = self._call()
        self.assertEqual((after.status, after.ended_at), (call.status, call.ended_at))
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(VoiceSession)).one().status, "dispatched")


if __name__ == "__main__":
    import unittest

    unittest.main()
