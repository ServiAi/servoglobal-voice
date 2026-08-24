from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from cryptography.fernet import Fernet
from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase
from app.api.auth.deps import get_current_auth_context
from app.api.endpoints.voice_public import get_public_rate_limiter, get_public_turnstile_verifier
from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.crm import CrmActivity, CrmVoiceCall
from app.models.integrations import TenantSipRoute, TenantVoiceAgentConfig, TenantVoiceProviderConfig
from app.models.voice_context import TenantVoiceContextField
from app.services.secret_manager_service import SecretManager
from app.services.tenant_feature_service import TenantFeatureService, VOICE_EXPERIENCES
from app.services.voice_callback_service import VoiceCallbackWorker
import test_public_voice_experience_submissions as submissions_tests


class PublicVoiceCallbackTests(Integration2ATestCase):
    _seed_agent = submissions_tests.PublicVoiceExperienceSubmissionTests._seed_agent
    _seed_schema = submissions_tests.PublicVoiceExperienceSubmissionTests._seed_schema
    _seed_fields = submissions_tests.PublicVoiceExperienceSubmissionTests._seed_fields
    _publish = submissions_tests.PublicVoiceExperienceSubmissionTests._publish
    _body = submissions_tests.PublicVoiceExperienceSubmissionTests._body
    _post = submissions_tests.PublicVoiceExperienceSubmissionTests._post

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
            TenantFeatureService(db).set_feature(
                self.tenant.id,
                VOICE_EXPERIENCES,
                True,
                {"max_experiences": 10, "max_context_fields": 20},
                self.user.id,
            )
            provider = TenantVoiceProviderConfig(
                tenant_id=self.tenant.id,
                provider="ultravox",
                status="active",
                api_key_encrypted=secrets.encrypt_secret("tenant-api-key"),
                webhook_secret_encrypted=secrets.encrypt_secret("tenant-webhook-secret"),
            )
            db.add(provider)
            db.flush()
            agent = db.get(TenantVoiceAgentConfig, self.agent_id)
            agent.provider_config_id = provider.id
            phone_field = db.scalar(
                select(TenantVoiceContextField).where(
                    TenantVoiceContextField.schema_id == self.schema_id,
                    TenantVoiceContextField.key == "mobile_number",
                )
            )
            phone_field.required = True
            db.add(
                TenantSipRoute(
                    tenant_id=self.tenant.id,
                    provider_config_id=provider.id,
                    status="active",
                    pbx_host="pbx.example.com",
                    pbx_port=5060,
                    sip_username="tenant-a",
                    sip_password_encrypted=secrets.encrypt_secret("test-sip-password"),
                    caller_id="+573001112233",
                    default_country="CO",
                    allowed_countries_json=["CO", "US"],
                    max_concurrent_calls=1,
                    provision_status="active",
                    desired_revision=1,
                    applied_revision=1,
                )
            )
            db.commit()
        self.published = self._publish()

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_public_rate_limiter, None)
        app.dependency_overrides.pop(get_public_turnstile_verifier, None)
        settings.INTEGRATIONS_ENCRYPTION_KEY = self.original_encryption_key
        settings.VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET = self.original_hash_secret
        super().tearDown()

    def _experience_payload(self) -> dict:
        payload = submissions_tests.PublicVoiceExperienceSubmissionTests._experience_payload(self)
        payload["call_settings"] = {
            "mode": "callback",
            "phone_field_key": "mobile_number",
            "default_country": "CO",
            "auto_start": False,
            "show_microphone_help": False,
            "language": "es",
        }
        return payload

    def _request_callback(self, token: str):
        return self.client.post(
            f"/api/v1/public/voice-experiences/{self.published['slug']}/callback-requests",
            json={"context_token": token},
        )

    def test_callback_is_idempotent_and_worker_uses_tenant_route(self) -> None:
        app.dependency_overrides.pop(get_current_auth_context, None)
        submission = self._post()
        self.assertEqual(submission.status_code, 200, submission.text)
        token = submission.json()["context_token"]

        first = self._request_callback(token)
        second = self._request_callback(token)
        self.assertEqual(first.status_code, 202, first.text)
        self.assertEqual(second.status_code, 202, second.text)
        self.assertEqual(first.json(), {"status": "accepted"})
        with SessionLocal() as db:
            calls = db.scalars(select(CrmVoiceCall)).all()
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0].to_phone, "+573001112233")
            self.assertEqual(calls[0].status, "requested")
            activity = db.scalars(
                select(CrmActivity).where(CrmActivity.activity_type == "voice_call_requested")
            ).one()
            self.assertEqual(activity.payload_json["voice_call_id"], calls[0].id)

        with patch("app.services.voice_callback_service.VoiceClient.start_outbound_call") as start:
            start.return_value = {"callId": "provider-callback-1", "status": "queued"}
            self.assertTrue(VoiceCallbackWorker(SessionLocal).process_once())
            config = start.call_args.args[0]
            self.assertEqual(start.call_args.kwargs["agent_id"], "submission-agent")
            self.assertEqual(config.sip_route.username, "tenant-a")
            self.assertEqual(config.sip_route.password, "test-sip-password")

        with SessionLocal() as db:
            call = db.scalars(select(CrmVoiceCall)).one()
            self.assertEqual(call.status, "queued")
            self.assertEqual(call.provider_call_id, "provider-callback-1")

    def test_submission_rejects_phone_outside_tenant_allowed_countries(self) -> None:
        app.dependency_overrides.pop(get_current_auth_context, None)
        # Mexico is in the global SUPPORTED_OUTBOUND_COUNTRIES set but the
        # tenant's SIP route (seeded in setUp) only allows CO/US.
        body = self._body(answers={
            "full_name": "Ana",
            "client_email": "ana@example.com",
            "mobile_number": "+522221234567",
            "company": "ServiAI",
            "guests": 0,
            "plan": "pro",
            "verified": False,
            "date": "2026-08-12",
        })
        response = self._post(body)
        self.assertEqual(response.status_code, 422, response.text)
        fields = {(item["key"], item["code"]) for item in response.json()["detail"]["fields"]}
        self.assertIn(("mobile_number", "invalid_format"), fields)

    def test_failed_callback_can_be_retried_through_same_endpoint(self) -> None:
        app.dependency_overrides.pop(get_current_auth_context, None)
        submission = self._post()
        token = submission.json()["context_token"]

        first = self._request_callback(token)
        self.assertEqual(first.status_code, 202, first.text)

        with patch("app.services.voice_callback_service.VoiceClient.start_outbound_call") as start:
            start.side_effect = RuntimeError("provider unavailable")
            self.assertTrue(VoiceCallbackWorker(SessionLocal).process_once())

        with SessionLocal() as db:
            call = db.scalars(select(CrmVoiceCall)).one()
            self.assertEqual(call.status, "failed")
            self.assertIsNotNone(call.error_message)

        retry = self._request_callback(token)
        self.assertEqual(retry.status_code, 202, retry.text)
        self.assertEqual(retry.json(), {"status": "accepted"})

        with SessionLocal() as db:
            calls = db.scalars(select(CrmVoiceCall)).all()
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0].status, "requested")
            self.assertIsNone(calls[0].error_message)

        with patch("app.services.voice_callback_service.VoiceClient.start_outbound_call") as start:
            start.return_value = {"callId": "provider-callback-retry", "status": "queued"}
            self.assertTrue(VoiceCallbackWorker(SessionLocal).process_once())

        with SessionLocal() as db:
            call = db.scalars(select(CrmVoiceCall)).one()
            self.assertEqual(call.status, "queued")
            self.assertEqual(call.provider_call_id, "provider-callback-retry")

    def test_worker_recovers_call_stuck_in_starting_past_lease(self) -> None:
        with SessionLocal() as db:
            route_a = db.scalar(
                select(TenantSipRoute).where(TenantSipRoute.tenant_id == self.tenant.id)
            )
            stuck = CrmVoiceCall(
                tenant_id=self.tenant.id,
                sip_route_id=route_a.id,
                source_submission_id="sub-stuck-starting",
                provider="ultravox",
                direction="outbound",
                status="starting",
                to_phone="+573001110002",
                from_number=route_a.caller_id,
                provider_attempt_started_at=datetime.now(UTC) - timedelta(seconds=90),
            )
            db.add(stuck)
            db.commit()
            stuck_id = stuck.id

        with patch("app.services.voice_callback_service.VoiceClient.start_outbound_call") as start:
            start.return_value = {"callId": "provider-recovered-1", "status": "queued"}
            worker = VoiceCallbackWorker(SessionLocal, starting_lease_seconds=60)
            self.assertTrue(worker.process_once())

        with SessionLocal() as db:
            call = db.get(CrmVoiceCall, stuck_id)
            self.assertEqual(call.status, "queued")
            self.assertEqual(call.provider_call_id, "provider-recovered-1")

    def test_worker_leaves_starting_call_within_lease_untouched(self) -> None:
        with SessionLocal() as db:
            route_a = db.scalar(
                select(TenantSipRoute).where(TenantSipRoute.tenant_id == self.tenant.id)
            )
            fresh = CrmVoiceCall(
                tenant_id=self.tenant.id,
                sip_route_id=route_a.id,
                source_submission_id="sub-fresh-starting",
                provider="ultravox",
                direction="outbound",
                status="starting",
                to_phone="+573001110003",
                from_number=route_a.caller_id,
                provider_attempt_started_at=datetime.now(UTC) - timedelta(seconds=5),
            )
            db.add(fresh)
            db.commit()
            fresh_id = fresh.id

        worker = VoiceCallbackWorker(SessionLocal, starting_lease_seconds=60)
        self.assertFalse(worker.process_once())

        with SessionLocal() as db:
            call = db.get(CrmVoiceCall, fresh_id)
            self.assertEqual(call.status, "starting")

    def test_claim_skips_saturated_route_to_serve_other_tenants(self) -> None:
        secrets = SecretManager()
        tenant_b, _user_b = self._seed_tenant_user(slug="tenant-b", email="admin-b@example.com")

        with SessionLocal() as db:
            route_a = db.scalar(
                select(TenantSipRoute).where(TenantSipRoute.tenant_id == self.tenant.id)
            )

            provider_b = TenantVoiceProviderConfig(
                tenant_id=tenant_b.id,
                provider="ultravox",
                status="active",
                api_key_encrypted=secrets.encrypt_secret("tenant-b-api-key"),
            )
            db.add(provider_b)
            db.flush()
            route_b = TenantSipRoute(
                tenant_id=tenant_b.id,
                provider_config_id=provider_b.id,
                status="active",
                pbx_host="pbx-b.example.com",
                pbx_port=5060,
                sip_username="tenant-b",
                sip_password_encrypted=secrets.encrypt_secret("tenant-b-sip-password"),
                caller_id="+573009998877",
                default_country="CO",
                allowed_countries_json=["CO"],
                max_concurrent_calls=1,
                provision_status="active",
                desired_revision=1,
                applied_revision=1,
            )
            db.add(route_b)
            db.flush()

            now = datetime.now(UTC)
            # Tenant A's only capacity slot is already occupied by an active call.
            db.add(
                CrmVoiceCall(
                    tenant_id=self.tenant.id,
                    sip_route_id=route_a.id,
                    provider="ultravox",
                    direction="outbound",
                    status="in_progress",
                    to_phone="+573001110000",
                    from_number=route_a.caller_id,
                    created_at=now - timedelta(minutes=5),
                )
            )
            # Tenant A has an older queued callback that cannot be served yet.
            db.add(
                CrmVoiceCall(
                    tenant_id=self.tenant.id,
                    sip_route_id=route_a.id,
                    source_submission_id="sub-tenant-a-queued",
                    provider="ultravox",
                    direction="outbound",
                    status="requested",
                    to_phone="+573001110001",
                    from_number=route_a.caller_id,
                    created_at=now - timedelta(minutes=4),
                )
            )
            # Tenant B has spare capacity and a newer queued callback.
            call_b = CrmVoiceCall(
                tenant_id=tenant_b.id,
                sip_route_id=route_b.id,
                source_submission_id="sub-tenant-b-queued",
                provider="ultravox",
                direction="outbound",
                status="requested",
                to_phone="+573009998866",
                from_number=route_b.caller_id,
                created_at=now - timedelta(minutes=1),
            )
            db.add(call_b)
            db.commit()
            call_b_id = call_b.id

        claimed_id = VoiceCallbackWorker(SessionLocal)._claim()
        self.assertEqual(claimed_id, call_b_id)

        with SessionLocal() as db:
            claimed = db.get(CrmVoiceCall, call_b_id)
            self.assertEqual(claimed.status, "starting")

            still_queued = db.scalar(
                select(CrmVoiceCall).where(
                    CrmVoiceCall.source_submission_id == "sub-tenant-a-queued"
                )
            )
            self.assertEqual(still_queued.status, "requested")


if __name__ == "__main__":
    import unittest

    unittest.main()
