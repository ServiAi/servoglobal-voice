from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
from cryptography.fernet import Fernet
from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase
from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.integrations import TenantVoiceProviderConfig
from app.modules.agents.infrastructure.models import TenantAgent, TenantAgentVersion
from app.modules.analytics.infrastructure.models import Call, CallEvent
from app.modules.crm.infrastructure.models import CrmContact, CrmLead, CrmPipelineStage, CrmVoiceCall, CrmVoiceCallEvent
from app.modules.identity.application.feature_service import VOICE_EXPERIENCES, VOICE_RUNTIME_V2, TenantFeatureService
from app.modules.voice.infrastructure.livekit_runtime import RuntimeDispatchResult
from app.modules.voice.infrastructure.models import VoiceSession
from app.modules.voice.public import VoiceSessionFacade
from app.modules.voice_experiences.api.public_router import (
    get_public_call_service,
    get_public_rate_limiter,
    get_public_turnstile_verifier,
)
from app.modules.voice_experiences.application.experience_service import VoiceExperienceService
from app.modules.voice_experiences.application.public_webrtc_service import PublicWebRTCService
from app.modules.voice_experiences.infrastructure.context_models import TenantVoiceContextField
from app.modules.voice_experiences.infrastructure.submission_models import (
    TenantVoiceContextSession,
    TenantVoiceExperienceSubmission,
    TenantVoiceExperienceSubmissionValue,
    TenantVoiceRuntimeCall,
)
from app.modules.voice_experiences.infrastructure.voice_runtime_adapter import VoiceRuntimeAdapter
from app.services.secret_manager_service import SecretManager
import test_public_voice_experience_submissions as submissions_tests

LIVEKIT_SECRET = "s" * 32
FORBIDDEN_PUBLIC_KEYS = (
    "tenant_id", "agent_id", "agent_version_id", "voice_session_id", "room_name", "provider",
    "provider_agent_id", "provider_call_id", "agent_config_id", "context_schema_id", "system_prompt",
    "tools", "runtime_binding", "join_url", "api_key", "api_secret",
)


class FakeLiveKit:
    """Stands in for LiveKit's dispatch API; counts rooms created."""

    def __init__(self) -> None:
        self.dispatches: list[str] = []
        self.closed: list[str] = []
        self.fail = False
        self.delay = 0.0

    async def dispatch(self, session_id: str) -> RuntimeDispatchResult:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("livekit exploded: secret-internal-detail")
        self.dispatches.append(session_id)
        return RuntimeDispatchResult(f"sg-vs-{session_id}", f"dispatch-{len(self.dispatches)}")

    async def close_session_room(self, session_id: str) -> None:
        self.closed.append(session_id)


class PublicVoiceCallTests(Integration2ATestCase):
    _seed_agent = submissions_tests.PublicVoiceExperienceSubmissionTests._seed_agent
    _seed_schema = submissions_tests.PublicVoiceExperienceSubmissionTests._seed_schema
    _seed_fields = submissions_tests.PublicVoiceExperienceSubmissionTests._seed_fields
    _experience_payload = submissions_tests.PublicVoiceExperienceSubmissionTests._experience_payload
    _publish = submissions_tests.PublicVoiceExperienceSubmissionTests._publish
    _body = submissions_tests.PublicVoiceExperienceSubmissionTests._body
    _post = submissions_tests.PublicVoiceExperienceSubmissionTests._post

    def setUp(self) -> None:
        self.original_encryption_key = settings.INTEGRATIONS_ENCRYPTION_KEY
        settings.INTEGRATIONS_ENCRYPTION_KEY = Fernet.generate_key().decode()
        super().setUp()
        self.original_hash_secret = settings.VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET
        settings.VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET = "test-rate-secret"
        for name, value in (
            ("LIVEKIT_URL", "wss://livekit.example"),
            ("LIVEKIT_API_KEY", "test-key"),
            ("LIVEKIT_API_SECRET", LIVEKIT_SECRET),
        ):
            patcher = patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.livekit = FakeLiveKit()
        self.limiter = submissions_tests._AllowLimiter()
        self.verifier = submissions_tests._Verifier()
        app.dependency_overrides[get_public_rate_limiter] = lambda: self.limiter
        app.dependency_overrides[get_public_turnstile_verifier] = lambda: self.verifier
        app.dependency_overrides[get_public_call_service] = self._service
        self.agent_id = self._seed_agent()
        self.schema_id = self._seed_schema()
        self._seed_fields()
        with SessionLocal() as db:
            features = TenantFeatureService(db)
            features.set_feature(
                self.tenant.id, VOICE_EXPERIENCES, True, {"max_experiences": 10, "max_context_fields": 20}, self.user.id
            )
            features.set_feature(self.tenant.id, VOICE_RUNTIME_V2, True, {}, self.user.id)
        self.published = self._publish()
        secrets = SecretManager()
        with SessionLocal() as db:  # tenant webhook secret, only used by the legacy webhook regression tests
            db.add(
                TenantVoiceProviderConfig(
                    tenant_id=self.tenant.id,
                    provider="ultravox",
                    status="active",
                    api_key_encrypted=secrets.encrypt_secret("tenant-api-key"),
                    webhook_secret_encrypted=secrets.encrypt_secret("tenant-webhook-secret"),
                )
            )
            db.commit()

    def tearDown(self) -> None:
        settings.VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET = self.original_hash_secret
        for dependency in (get_public_rate_limiter, get_public_turnstile_verifier, get_public_call_service):
            app.dependency_overrides.pop(dependency, None)
        settings.INTEGRATIONS_ENCRYPTION_KEY = self.original_encryption_key
        super().tearDown()

    def _service(self) -> PublicWebRTCService:
        return PublicWebRTCService(
            session_factory=SessionLocal,
            runtime_factory=lambda db: VoiceRuntimeAdapter(db, runtime_backend=self.livekit),
        )

    def _launch(self, token: str):
        return self.client.post(
            f"/api/v1/public/voice-experiences/{self.published['slug']}/calls",
            json={"context_token": token},
        )

    def _token(self, body: dict | None = None) -> str:
        response = self._post(body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["context_token"]

    def _canonical_agent(self) -> tuple[str, str]:
        with SessionLocal() as db:
            version = db.scalars(
                select(TenantAgentVersion).where(TenantAgentVersion.voice_agent_config_id == self.agent_id)
            ).one()
            return version.agent_id, version.id

    def _decode(self, token: str) -> dict:
        return jwt.decode(token, LIVEKIT_SECRET, algorithms=["HS256"], options={"verify_aud": False})

    def _send_runtime_event(self, voice_call_id: str, provider_call_id: str, event_type: str, **call_values):
        payload = {
            "event": event_type,
            "call": {
                "callId": provider_call_id,
                "metadata": {"voice_call_id": voice_call_id, "tenant_id": "attacker"},
                **call_values,
            },
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = datetime.now(UTC).isoformat()
        signature = hmac.new(b"tenant-webhook-secret", raw + timestamp.encode(), hashlib.sha256).hexdigest()
        return self.client.post(
            "/api/v1/voice/webhook/ultravox",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "x-ultravox-webhook-timestamp": timestamp,
                "x-ultravox-webhook-signature": signature,
            },
        )

    # -- canonical launch ------------------------------------------------------

    def test_launch_creates_one_voice_session_and_returns_only_join_credentials(self) -> None:
        agent_id, version_id = self._canonical_agent()
        response = self._launch(self._token())

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body), {"status", "server_url", "participant_token", "expires_in", "capabilities"})
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["server_url"], "wss://livekit.example")
        for forbidden in FORBIDDEN_PUBLIC_KEYS:
            self.assertNotIn(forbidden, response.text, forbidden)
        self.assertNotIn(LIVEKIT_SECRET, response.text)
        grants = self._decode(body["participant_token"])
        self.assertTrue(grants["sub"].startswith("web-"))
        video = grants["video"]
        self.assertTrue(video["roomJoin"] and video["canSubscribe"] and video["canPublish"])
        self.assertEqual(video["canPublishSources"], ["microphone"])
        self.assertFalse(video.get("canPublishData", False))
        self.assertFalse(any(video.get(flag) for flag in ("roomCreate", "roomAdmin", "roomRecord", "ingressAdmin")))

        with SessionLocal() as db:
            session = db.scalars(select(VoiceSession)).one()
            runtime = db.scalars(select(TenantVoiceRuntimeCall)).one()
            crm_call = db.scalars(select(CrmVoiceCall)).one()
            context = db.scalars(select(TenantVoiceContextSession)).one()
            self.assertEqual(
                (session.channel, session.direction, session.purpose, session.status),
                ("webrtc", "internal", "production", "dispatched"),
            )
            self.assertEqual((session.agent_id, session.agent_version_id), (agent_id, version_id))
            self.assertEqual(video["room"], session.livekit_room_name)
            self.assertEqual(runtime.voice_session_id, session.id)
            self.assertEqual(session.crm_voice_call_id, runtime.crm_voice_call_id)
            self.assertEqual(crm_call.id, runtime.crm_voice_call_id)
            self.assertEqual((runtime.status, runtime.provider_call_id), ("ready", None))
            self.assertEqual(context.status, "consumed")
            self.assertEqual(crm_call.direction, "webrtc")
            self.assertNotIn(body["participant_token"], repr([runtime.__dict__, session.__dict__, crm_call.__dict__]))
        self.assertEqual(self.livekit.dispatches, [session.id])

    def test_replay_returns_the_same_session_with_a_new_token_and_never_redispatches(self) -> None:
        token = self._token()
        first = self._launch(token)
        second = self._launch(token)

        self.assertEqual((first.status_code, second.status_code), (200, 200), second.text)
        self.assertNotEqual(first.json()["participant_token"], second.json()["participant_token"])
        first_claims, second_claims = (self._decode(r.json()["participant_token"]) for r in (first, second))
        self.assertEqual(first_claims["video"]["room"], second_claims["video"]["room"])
        self.assertNotEqual(first_claims["sub"], second_claims["sub"])
        self.assertEqual(len(self.livekit.dispatches), 1)
        with SessionLocal() as db:
            for model in (VoiceSession, TenantVoiceRuntimeCall, CrmVoiceCall):
                self.assertEqual(db.query(model).count(), 1, model.__name__)

    def test_launch_uses_the_exact_agent_version_even_after_the_agent_publishes_a_newer_one(self) -> None:
        agent_id, v1 = self._canonical_agent()
        token = self._token()
        with SessionLocal() as db:
            v1_row = db.get(TenantAgentVersion, v1)
            v2 = TenantAgentVersion(
                agent_id=agent_id, tenant_id=self.tenant.id, version=2, status="published", language="es",
                timezone="America/Bogota", identity_json={"name": "Safe agent"},
                instructions_json={"system_prompt": "v2"}, behavior_json={},
                runtime_binding_json={"pipeline_type": "realtime", "realtime": {"provider": "ultravox"}},
                voice_agent_config_id=self.agent_id, published_at=datetime.now(UTC),
            )
            db.add(v2)
            db.flush()
            v1_row.status = "superseded"
            db.get(TenantAgent, agent_id).published_version_id = v2.id
            db.commit()

        self.assertEqual(self._launch(token).status_code, 200)
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(VoiceSession)).one().agent_version_id, v1)

    def test_archived_or_unpublished_agent_blocks_the_launch_before_the_token_is_consumed(self) -> None:
        agent_id, _ = self._canonical_agent()
        for status in ("archived", "draft"):
            with self.subTest(agent_status=status):
                token = self._token()
                with SessionLocal() as db:
                    db.get(TenantAgent, agent_id).status = status
                    db.commit()
                response = self._launch(token)
                self.assertEqual(response.status_code, 503, response.text)
                self.assertEqual(response.json()["detail"]["code"], "call_unavailable")
                with SessionLocal() as db:
                    self.assertEqual(db.query(VoiceSession).count(), 0)
                    self.assertEqual(db.query(TenantVoiceRuntimeCall).count(), 0)
                    self.assertEqual(db.query(CrmVoiceCall).count(), 0)
                    db.get(TenantAgent, agent_id).status = "active"
                    db.commit()
        self.assertEqual(self.livekit.dispatches, [])

    def test_voice_runtime_v2_disabled_fails_closed_without_consuming_the_token(self) -> None:
        token = self._token()
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(self.tenant.id, VOICE_RUNTIME_V2, False, {}, self.user.id)

        response = self._launch(token)

        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["code"], "call_unavailable")
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(TenantVoiceContextSession)).one().status, "active")
            self.assertEqual(db.query(VoiceSession).count(), 0)

    def test_session_context_comes_from_the_trusted_submission_only(self) -> None:
        token = self._token()
        with SessionLocal() as db:
            context_session = db.scalars(select(TenantVoiceContextSession)).one()
            submission = db.get(TenantVoiceExperienceSubmission, context_session.submission_id)
            contact_id, lead_id = submission.crm_contact_id, submission.crm_lead_id
            self.assertTrue(contact_id and lead_id)
            db.add(
                TenantVoiceContextField(
                    tenant_id=self.tenant.id, schema_id=self.schema_id, key="internal_note", label="n",
                    field_type="text", collection_mode="internal_only", required=False, position=99,
                    sensitivity="standard", validation_json={}, options_json=[],
                )
            )
            db.add(
                TenantVoiceExperienceSubmissionValue(
                    tenant_id=self.tenant.id, submission_id=submission.id, field_key="internal_note", field_type="text", value_json="hidden"
                )
            )
            db.commit()

        # The request can only carry the token: IDs smuggled in the body are rejected outright.
        smuggled = self.client.post(
            f"/api/v1/public/voice-experiences/{self.published['slug']}/calls",
            json={"context_token": token, "contact_id": "attacker", "lead_id": "attacker", "agent_id": "x"},
        )
        self.assertEqual(smuggled.status_code, 422)
        self.assertEqual(self._launch(token).status_code, 200)

        with SessionLocal() as db:
            context = db.scalars(select(VoiceSession)).one().session_context_json
        self.assertEqual(context["source"], "webrtc")
        self.assertEqual(context["contact"]["id"], contact_id)
        self.assertEqual(context["lead"]["id"], lead_id)
        self.assertIsNone(context["caller"])  # a browser participant is not a PSTN caller
        variables = context["variables"]
        self.assertEqual(variables["full_name"], "Ana")
        self.assertEqual(variables["locale"], "es")
        self.assertNotIn("internal_note", variables)
        flat = json.dumps(context)
        for secret in (token, self.tenant.id, "token_hash"):
            self.assertNotIn(secret, flat)

    def test_lead_reaches_the_tools_through_the_session_context(self) -> None:
        agent_id, version_id = self._canonical_agent()
        with SessionLocal() as db:
            version = db.get(TenantAgentVersion, version_id)
            version.runtime_binding_json = {
                **version.runtime_binding_json,
                "tools": [{"key": "calendar.create_booking", "enabled": True}],
            }
            db.commit()
        self.assertEqual(self._launch(self._token()).status_code, 200)
        with SessionLocal() as db:
            session = db.scalars(select(VoiceSession)).one()
            lead_id = db.scalars(select(CrmVoiceCall)).one().lead_id
            view = VoiceSessionFacade(db).get_tool_session(session.id)
        self.assertEqual(view.context.lead.id, lead_id)
        self.assertIsNotNone(view.context.contact)
        self.assertIsNotNone(view.binding("calendar.create_booking"))

    def test_submission_without_crm_identity_launches(self) -> None:
        body = self._body()
        body["answers"].pop("client_email")
        body["answers"].pop("mobile_number")
        response = self._launch(self._token(body))
        self.assertEqual(response.status_code, 200, response.text)
        with SessionLocal() as db:
            call = db.scalars(select(CrmVoiceCall)).one()
            self.assertIsNone(call.contact_id)
            self.assertIsNone(call.lead_id)
            context = db.scalars(select(VoiceSession)).one().session_context_json
            self.assertIsNone(context["contact"])
            self.assertIsNone(context["lead"])

    # -- failures and crash recovery -------------------------------------------

    def test_dispatch_failure_fails_session_and_ledger_with_a_sanitized_503(self) -> None:
        self.livekit.fail = True
        token = self._token()

        response = self._launch(token)

        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"], {"code": "call_provider_unavailable"})
        self.assertNotIn("secret-internal-detail", response.text)
        self.assertNotIn("livekit", response.text.lower())
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(VoiceSession)).one().status, "failed")
            self.assertEqual(db.scalars(select(TenantVoiceRuntimeCall)).one().status, "failed")
        replay = self._launch(token)
        self.assertEqual(replay.status_code, 503)
        self.assertEqual(self.livekit.dispatches, [])

    def test_unconfigured_livekit_fails_closed_without_a_partial_response(self) -> None:
        token = self._token()
        with patch.object(settings, "LIVEKIT_API_SECRET", ""):
            response = self._launch(token)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"], {"code": "call_unavailable"})
        self.assertNotIn("participant_token", response.text)
        self.assertNotIn("join_url", response.text)
        # Not a permanent failure: once LiveKit is configured the same token recovers.
        recovered = self._launch(token)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(len(self.livekit.dispatches), 1)

    def test_crash_after_claim_before_session_converges_on_one_session(self) -> None:
        token = self._token()
        service = self._service()
        session, _ = service._resolve_session_and_runtime(self.published["slug"], token)
        service._claim(self.published["slug"], session.id, service._precheck(session))

        response = self._launch(token)

        self.assertEqual(response.status_code, 200, response.text)
        with SessionLocal() as db:
            self.assertEqual(db.query(VoiceSession).count(), 1)
            self.assertEqual(db.query(TenantVoiceRuntimeCall).count(), 1)
        self.assertEqual(len(self.livekit.dispatches), 1)

    def test_crash_after_session_creation_before_ledger_link_recovers_the_same_session(self) -> None:
        token = self._token()
        service = self._service()
        context, _ = service._resolve_session_and_runtime(self.published["slug"], token)
        service._claim(self.published["slug"], context.id, service._precheck(context))
        agent_id, version_id = self._canonical_agent()
        with SessionLocal() as db:
            orphan = VoiceSessionFacade(db).create_session_from_agent_version(
                self.tenant.id, agent_id, version_id, channel="webrtc", direction="internal",
                idempotency_key=f"voice-experience:{context.id}",
            )
            self.assertIsNone(db.scalars(select(TenantVoiceRuntimeCall)).one().voice_session_id)

        response = self._launch(token)

        self.assertEqual(response.status_code, 200, response.text)
        with SessionLocal() as db:
            self.assertEqual(db.query(VoiceSession).count(), 1)
            self.assertEqual(db.scalars(select(TenantVoiceRuntimeCall)).one().voice_session_id, orphan.session_id)

    def test_crash_after_dispatch_before_response_reissues_a_token_without_redispatch(self) -> None:
        token = self._token()
        self.assertEqual(self._launch(token).status_code, 200)
        with SessionLocal() as db:  # the response was lost: ledger still "starting"
            runtime = db.scalars(select(TenantVoiceRuntimeCall)).one()
            runtime.status = "starting"
            db.commit()

        response = self._launch(token)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.livekit.dispatches), 1)
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(TenantVoiceRuntimeCall)).one().status, "ready")

    def test_ended_session_is_not_rejoinable(self) -> None:
        token = self._token()
        self.assertEqual(self._launch(token).status_code, 200)
        with SessionLocal() as db:
            session = db.scalars(select(VoiceSession)).one()
            session.status = "ended"
            db.commit()
        response = self._launch(token)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "call_already_started")

    def test_a_pre_canonical_direct_provider_call_is_never_relaunched(self) -> None:
        token = self._token()
        self.assertEqual(self._launch(token).status_code, 200)
        with SessionLocal() as db:
            runtime = db.scalars(select(TenantVoiceRuntimeCall)).one()
            runtime.voice_session_id = None
            runtime.provider_call_id = "legacy-provider-call"
            db.commit()
            db.query(VoiceSession).delete()
            db.commit()
        response = self._launch(token)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "call_already_started")

    def test_public_launch_never_calls_a_provider_directly(self) -> None:
        token = self._token()
        with patch(
            "app.modules.voice_experiences.infrastructure.legacy_runtime.provider_adapter."
            "VoiceExperienceRuntimeProvider.create_webrtc_call",
            side_effect=AssertionError("direct provider call"),
        ) as create_call, patch(
            "app.services.voice_client.VoiceClient.__init__", side_effect=AssertionError("VoiceClient used")
        ), patch("httpx.AsyncClient.send", side_effect=AssertionError("outbound HTTP")):
            response = self._launch(token)
        self.assertEqual(response.status_code, 200, response.text)
        create_call.assert_not_called()

    # -- ledger / regressions ---------------------------------------------------

    def test_delete_archived_experience_removes_the_ledger_but_keeps_crm_audit_and_session(self) -> None:
        self.assertEqual(self._launch(self._token()).status_code, 200)
        experience_id = self.published["id"]

        with SessionLocal() as db:
            service = VoiceExperienceService(db)
            service.unpublish_experience(self.tenant.id, experience_id, self.user.id)
            service.archive_experience(self.tenant.id, experience_id, self.user.id)
            service.delete_experience(self.tenant.id, experience_id, self.user.id)

            self.assertEqual(db.query(TenantVoiceRuntimeCall).count(), 0)
            self.assertEqual(db.query(TenantVoiceContextSession).count(), 0)
            self.assertEqual(db.query(CrmVoiceCall).count(), 1)
            self.assertEqual(db.query(VoiceSession).count(), 1)

    def test_manual_body_validation_rejects_extra_fields_without_pydantic_detail(self) -> None:
        response = self.client.post(
            f"/api/v1/public/voice-experiences/{self.published['slug']}/calls",
            json={"context_token": "x" * 40, "tenant_id": "attacker"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], {"code": "validation_error"})
        self.assertNotIn("loc", response.text)
        self.assertNotIn("input", response.text)

    def test_runtime_webhook_is_signed_deduplicated_and_updates_analytics(self) -> None:
        self.assertEqual(self._launch(self._token()).status_code, 200)
        with SessionLocal() as db:
            crm_call = db.scalars(select(CrmVoiceCall)).one()

        send = lambda event_type, **values: self._send_runtime_event(
            crm_call.id, "provider-webhook", event_type, **values
        )
        self.assertEqual(send("call.joined").status_code, 200)
        self.assertEqual(send("call.billed", billedDuration="75s").status_code, 200)
        duplicate = send("call.billed", billedDuration="120s")
        self.assertEqual(duplicate.status_code, 200)
        self.assertFalse(duplicate.json()["processed"])
        self.assertEqual(send("call.ended", duration=75).status_code, 200)
        with SessionLocal() as db:
            runtime = db.scalars(select(TenantVoiceRuntimeCall)).one()
            analytics = db.scalars(select(Call)).one()
            self.assertEqual(runtime.status, "ended")
            self.assertEqual(str(analytics.billed_minutes), "1.25")
            self.assertEqual(db.query(CallEvent).count(), 3)
            self.assertEqual(db.query(CrmVoiceCallEvent).count(), 3)

        unsigned = self.client.post(
            "/api/v1/voice/webhook/ultravox",
            json={"event": "call.started", "call": {"callId": "provider-webhook", "metadata": {"voice_call_id": crm_call.id}}},
        )
        self.assertEqual(unsigned.status_code, 401)

    def test_terminal_runtime_and_crm_do_not_regress_on_late_events(self) -> None:
        self.assertEqual(self._launch(self._token()).status_code, 200)
        with SessionLocal() as db:
            crm_call = db.scalars(select(CrmVoiceCall)).one()
        send = lambda event_type: self._send_runtime_event(crm_call.id, "provider-monotonic", event_type)
        self.assertEqual(send("call.ended").status_code, 200)
        self.assertEqual(send("call.joined").status_code, 200)
        with SessionLocal() as db:
            self.assertEqual(db.get(CrmVoiceCall, crm_call.id).status, "completed")
            self.assertEqual(db.scalars(select(TenantVoiceRuntimeCall)).one().status, "ended")


if __name__ == "__main__":
    import unittest

    unittest.main()
