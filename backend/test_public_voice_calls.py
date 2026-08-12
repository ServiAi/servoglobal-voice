from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from unittest.mock import patch

from cryptography.fernet import Fernet
from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase
from app.api.endpoints.voice_public import get_public_rate_limiter, get_public_turnstile_verifier
from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.crm import CrmVoiceCall
from app.models.analytics import Call, CallEvent
from app.models.crm import CrmVoiceCallEvent
from app.models.integrations import TenantVoiceAgentConfig, TenantVoiceProviderConfig
from app.models.voice_submissions import TenantVoiceContextSession, TenantVoiceRuntimeCall
from app.services.secret_manager_service import SecretManager
from app.services.tenant_feature_service import TenantFeatureService, VOICE_EXPERIENCES
from app.services.voice_experience_runtime_provider import ProviderAmbiguousFailure, ProviderCallResult
import test_public_voice_experience_submissions as submissions_tests


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
        self.limiter = submissions_tests._AllowLimiter()
        self.verifier = submissions_tests._Verifier()
        app.dependency_overrides[get_public_rate_limiter] = lambda: self.limiter
        app.dependency_overrides[get_public_turnstile_verifier] = lambda: self.verifier
        self.agent_id = self._seed_agent()
        self.schema_id = self._seed_schema()
        self._seed_fields()
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(
                self.tenant.id,
                VOICE_EXPERIENCES,
                True,
                {"max_experiences": 10, "max_context_fields": 20},
                self.user.id,
            )
        self.published = self._publish()
        secrets = SecretManager()
        with SessionLocal() as db:
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
            db.commit()

    def tearDown(self) -> None:
        settings.VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET = self.original_hash_secret
        app.dependency_overrides.pop(get_public_rate_limiter, None)
        app.dependency_overrides.pop(get_public_turnstile_verifier, None)
        settings.INTEGRATIONS_ENCRYPTION_KEY = self.original_encryption_key
        super().tearDown()

    def _launch(self, token: str):
        return self.client.post(
            f"/api/v1/public/voice-experiences/{self.published['slug']}/calls",
            json={"context_token": token},
        )

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

    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.create_webrtc_call",
        return_value=ProviderCallResult("provider-call-1", "https://provider.invalid/join/secret"),
    )
    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.get_call",
        return_value=ProviderCallResult("provider-call-1", "https://provider.invalid/join/secret"),
    )
    def test_same_token_recovers_same_call_without_second_create(self, _get_call, create_call) -> None:
        submission = self._post()
        token = submission.json()["context_token"]
        first = self._launch(token)
        second = self._launch(token)

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(create_call.call_count, 1)
        kwargs = create_call.call_args.kwargs
        self.assertEqual(kwargs["metadata"]["source"], "voice_experience")
        self.assertTrue(all(isinstance(value, str) for value in kwargs["metadata"].values()))
        self.assertEqual(kwargs["user_context"]["locale"], "es")
        self.assertNotIn("systemPrompt", kwargs)
        self.assertNotIn("tools", kwargs)
        self.assertNotIn("provider_call_id", first.text)
        with SessionLocal() as db:
            runtime = db.scalars(select(TenantVoiceRuntimeCall)).one()
            context = db.scalars(select(TenantVoiceContextSession)).one()
            crm_call = db.scalars(select(CrmVoiceCall)).one()
            self.assertEqual(runtime.status, "ready")
            self.assertEqual(context.status, "consumed")
            self.assertEqual(crm_call.direction, "webrtc")
            self.assertNotIn("join", repr(runtime.__dict__).lower())

    def test_manual_body_validation_rejects_extra_fields_without_pydantic_detail(self) -> None:
        response = self.client.post(
            f"/api/v1/public/voice-experiences/{self.published['slug']}/calls",
            json={"context_token": "x" * 40, "tenant_id": "attacker"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], {"code": "validation_error"})
        self.assertNotIn("loc", response.text)
        self.assertNotIn("input", response.text)

    def test_provider_result_uses_joined_ended_and_end_reason_contract(self) -> None:
        from app.services.voice_experience_runtime_provider import VoiceExperienceRuntimeProvider

        result = VoiceExperienceRuntimeProvider._result(
            {
                "callId": "provider-real-contract",
                "joinUrl": "https://provider.invalid/join/real-contract",
                "status": "ignored-legacy-status",
                "joined": "2026-08-12T11:59:00Z",
                "ended": "2026-08-12T12:00:00Z",
                "endReason": "hangup",
            }
        )
        self.assertEqual(result.provider_call_id, "provider-real-contract")
        self.assertEqual(result.joined_at, "2026-08-12T11:59:00Z")
        self.assertEqual(result.ended_at, "2026-08-12T12:00:00Z")
        self.assertEqual(result.end_reason, "hangup")

    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.create_webrtc_call",
        return_value=ProviderCallResult("provider-call-nullable", "https://provider.invalid/join/nullable"),
    )
    def test_submission_without_crm_identity_launches(self, create_call) -> None:
        body = self._body()
        body["answers"].pop("client_email")
        body["answers"]["mobile_number"] = "3001112233"
        submission = self._post(body)
        response = self._launch(submission.json()["context_token"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(create_call.call_count, 1)
        with SessionLocal() as db:
            call = db.scalars(select(CrmVoiceCall)).one()
            self.assertIsNone(call.contact_id)
            self.assertIsNone(call.lead_id)

    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.create_webrtc_call",
        return_value=ProviderCallResult("provider-partial", None),
    )
    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.get_call",
        return_value=ProviderCallResult("provider-partial", "https://provider.invalid/join/recovered"),
    )
    def test_partial_2xx_recovers_same_call_without_recreate(self, _get_call, create_call) -> None:
        token = self._post().json()["context_token"]
        self.assertEqual(self._launch(token).status_code, 503)
        self.assertEqual(self._launch(token).status_code, 200)
        self.assertEqual(create_call.call_count, 1)

    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.create_webrtc_call",
        side_effect=ProviderAmbiguousFailure(),
    )
    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.find_call_by_runtime_metadata",
        return_value=[ProviderCallResult("provider-found", "https://provider.invalid/join/found")],
    )
    def test_ambiguous_timeout_recovers_by_runtime_metadata(self, _find_call, create_call) -> None:
        token = self._post().json()["context_token"]
        self.assertEqual(self._launch(token).status_code, 503)
        self.assertEqual(self._launch(token).status_code, 200)
        self.assertEqual(create_call.call_count, 1)

    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.create_webrtc_call",
        return_value=ProviderCallResult("provider-ended", "https://provider.invalid/join/ended"),
    )
    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.get_call",
        return_value=ProviderCallResult(
            "provider-ended",
            "https://provider.invalid/join/ended",
            ended_at="2026-08-12T12:00:00Z",
            end_reason="hangup",
        ),
    )
    def test_get_call_ended_never_returns_join_url(self, _get_call, create_call) -> None:
        token = self._post().json()["context_token"]
        self.assertEqual(self._launch(token).status_code, 200)
        recovered = self._launch(token)
        self.assertEqual(recovered.status_code, 409)
        self.assertEqual(recovered.json()["detail"]["code"], "call_already_started")
        self.assertNotIn("join_url", recovered.text)
        self.assertEqual(create_call.call_count, 1)

    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.create_webrtc_call",
        return_value=ProviderCallResult("provider-joined", "https://provider.invalid/join/joined"),
    )
    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.get_call",
        return_value=ProviderCallResult(
            "provider-joined",
            "https://provider.invalid/join/joined",
            joined_at="2026-08-12T11:59:00Z",
        ),
    )
    def test_get_call_joined_returns_call_already_started(self, _get_call, create_call) -> None:
        token = self._post().json()["context_token"]
        self.assertEqual(self._launch(token).status_code, 200)
        recovered = self._launch(token)
        self.assertEqual(recovered.status_code, 409)
        self.assertEqual(recovered.json()["detail"]["code"], "call_already_started")
        self.assertEqual(create_call.call_count, 1)

    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.create_webrtc_call",
        side_effect=ProviderAmbiguousFailure(),
    )
    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.find_call_by_runtime_metadata",
        return_value=[
            ProviderCallResult(
                "provider-list-ended",
                "https://provider.invalid/join/list-ended",
                ended_at="2026-08-12T12:00:00Z",
                end_reason="hangup",
            )
        ],
    )
    def test_unknown_list_calls_ended_recovers_as_ended_without_recreate(self, _find_call, create_call) -> None:
        token = self._post().json()["context_token"]
        self.assertEqual(self._launch(token).status_code, 503)
        recovered = self._launch(token)
        self.assertEqual(recovered.status_code, 409)
        self.assertEqual(recovered.json()["detail"]["code"], "call_already_started")
        self.assertEqual(create_call.call_count, 1)
        with SessionLocal() as db:
            self.assertEqual(db.scalars(select(TenantVoiceRuntimeCall)).one().status, "ended")

    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.create_webrtc_call",
        return_value=ProviderCallResult("provider-webhook", "https://provider.invalid/join/webhook"),
    )
    def test_runtime_webhook_is_signed_deduplicated_and_updates_analytics(self, _create_call) -> None:
        submission = self._post()
        self.assertEqual(self._launch(submission.json()["context_token"]).status_code, 200)
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
            from app.services.tenant_usage_service import TenantUsageService

            usage = TenantUsageService(db).get_usage(db.get(type(self.tenant), self.tenant.id), persist_alerts=False)
            self.assertEqual(usage.minutes_used, 1.25)

        unsigned = self.client.post(
            "/api/v1/voice/webhook/ultravox",
            json={"event": "call.started", "call": {"callId": "provider-webhook", "metadata": {"voice_call_id": crm_call.id}}},
        )
        self.assertEqual(unsigned.status_code, 401)

    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.create_webrtc_call",
        return_value=ProviderCallResult("provider-duration-120", "https://provider.invalid/join/duration-120"),
    )
    def test_runtime_billing_parses_120_second_official_duration(self, _create_call) -> None:
        token = self._post().json()["context_token"]
        self.assertEqual(self._launch(token).status_code, 200)
        with SessionLocal() as db:
            crm_call = db.scalars(select(CrmVoiceCall)).one()
        response = self._send_runtime_event(
            crm_call.id,
            "provider-duration-120",
            "call.billed",
            billedDuration="120s",
        )
        self.assertEqual(response.status_code, 200, response.text)
        with SessionLocal() as db:
            analytics = db.scalars(select(Call)).one()
            self.assertEqual(str(analytics.billed_minutes), "2.00")
            from app.services.tenant_usage_service import TenantUsageService

            usage = TenantUsageService(db).get_usage(db.get(type(self.tenant), self.tenant.id), persist_alerts=False)
            self.assertEqual(usage.minutes_used, 2.0)

    @patch(
        "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.create_webrtc_call",
        return_value=ProviderCallResult("provider-monotonic", "https://provider.invalid/join/monotonic"),
    )
    def test_terminal_runtime_and_crm_do_not_regress_on_late_events(self, _create_call) -> None:
        token = self._post().json()["context_token"]
        self.assertEqual(self._launch(token).status_code, 200)
        with SessionLocal() as db:
            crm_call = db.scalars(select(CrmVoiceCall)).one()
        send = lambda event_type: self._send_runtime_event(
            crm_call.id, "provider-monotonic", event_type
        )
        self.assertEqual(send("call.ended").status_code, 200)
        self.assertEqual(send("call.joined").status_code, 200)
        with SessionLocal() as db:
            self.assertEqual(db.get(CrmVoiceCall, crm_call.id).status, "completed")
            self.assertEqual(db.scalars(select(TenantVoiceRuntimeCall)).one().status, "ended")
        self.assertEqual(send("call.started").status_code, 200)
        with SessionLocal() as db:
            self.assertEqual(db.get(CrmVoiceCall, crm_call.id).status, "completed")
            self.assertEqual(db.scalars(select(TenantVoiceRuntimeCall)).one().status, "ended")


if __name__ == "__main__":
    import unittest

    unittest.main()
