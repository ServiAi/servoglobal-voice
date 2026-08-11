from __future__ import annotations

import hashlib
from unittest.mock import patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase
from app.api.auth.deps import get_current_auth_context
from app.api.endpoints.voice_public import (
    get_public_rate_limiter,
    get_public_turnstile_verifier,
)
from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.crm import CrmContact
from app.models.integrations import TenantIntegrationEvent, TenantVoiceAgentConfig
from app.models.voice_context import TenantVoiceContextField, TenantVoiceContextSchema
from app.models.voice_submissions import (
    TenantVoiceContextSession,
    TenantVoiceExperienceSubmission,
    TenantVoiceExperienceSubmissionValue,
)
from app.services.tenant_feature_service import VOICE_EXPERIENCES, TenantFeatureService


class _AllowLimiter:
    def __init__(self) -> None:
        self.scopes: list[str] = []

    def consume(self, scope: str, _limit: int) -> bool:
        self.scopes.append(scope)
        return True

    def cleanup(self, **_kwargs) -> int:
        return 0


class _Verifier:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.tokens: list[str] = []

    async def verify(self, token: str, _remote_ip: str) -> bool:
        self.tokens.append(token)
        return self.accepted


class PublicVoiceExperienceSubmissionTests(Integration2ATestCase):
    def setUp(self) -> None:
        super().setUp()
        self.original_hash_secret = settings.VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET
        settings.VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET = "test-rate-secret"
        self.limiter = _AllowLimiter()
        self.verifier = _Verifier()
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

    def tearDown(self) -> None:
        settings.VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET = self.original_hash_secret
        app.dependency_overrides.pop(get_public_rate_limiter, None)
        app.dependency_overrides.pop(get_public_turnstile_verifier, None)
        super().tearDown()

    def _seed_agent(self) -> str:
        with SessionLocal() as db:
            agent = TenantVoiceAgentConfig(
                tenant_id=self.tenant.id,
                provider="ultravox",
                provider_agent_id="submission-agent",
                display_name="Submission agent",
                default_tools_json={},
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
            return agent.id

    def _seed_schema(self) -> str:
        with SessionLocal() as db:
            schema = TenantVoiceContextSchema(
                tenant_id=self.tenant.id,
                agent_config_id=self.agent_id,
                schema_key="submission-schema",
                version=1,
                status="active",
                name="Submission schema",
            )
            db.add(schema)
            db.commit()
            db.refresh(schema)
            return schema.id

    def _seed_fields(self) -> None:
        definitions = [
            ("full_name", "text", False, {}, []),
            ("notes", "textarea", False, {"max_length": 100}, []),
            ("email", "email", False, {}, []),
            ("phone", "phone", False, {}, []),
            ("guests", "integer", True, {"min": 0, "max": 20}, []),
            ("plan", "select", True, {}, [{"value": "pro", "label": "Pro"}]),
            ("verified", "checkbox", True, {}, []),
            ("date", "date", False, {}, []),
        ]
        with SessionLocal() as db:
            db.add_all(
                [
                    TenantVoiceContextField(
                        tenant_id=self.tenant.id,
                        schema_id=self.schema_id,
                        key=key,
                        label=key,
                        field_type=field_type,
                        collection_mode="ask_if_missing",
                        required=required,
                        position=position,
                        sensitivity="standard",
                        validation_json=validation,
                        options_json=options,
                    )
                    for position, (key, field_type, required, validation, options) in enumerate(definitions)
                ]
            )
            db.commit()

    def _experience_payload(self) -> dict:
        return {
            "agent_config_id": self.agent_id,
            "context_schema_id": self.schema_id,
            "name": "Submission experience",
            "default_locale": "es",
            "content": {
                "title": "Context",
                "description": "Description",
                "submit_label": "Continue",
                "call_label": "Call",
                "success_message": "Accepted",
            },
            "theme": {"logo_url": None, "primary_color": "#123ABC", "layout": "card"},
            "consent": {"required": True, "label": "Accept", "privacy_url": None},
            "call_settings": {"auto_start": False, "show_microphone_help": False, "language": "es"},
        }

    def _publish(self) -> dict:
        created = self.client.post("/api/v1/voice/experiences", json=self._experience_payload())
        self.assertEqual(created.status_code, 201, created.text)
        published = self.client.post(f"/api/v1/voice/experiences/{created.json()['id']}/publish")
        self.assertEqual(published.status_code, 200, published.text)
        return published.json()

    def _body(self, **overrides) -> dict:
        body = {
            "version": 1,
            "locale": "es",
            "answers": {
                "full_name": "Ana",
                "email": "ana@example.com",
                "phone": "+573001112233",
                "guests": 0,
                "plan": "pro",
                "verified": False,
                "date": "2026-08-12",
            },
            "consent": True,
            "turnstile_token": "single-use-token",
            "hp": "",
        }
        body.update(overrides)
        return body

    def _post(self, body: dict | None = None):
        return self.client.post(
            f"/api/v1/public/voice-experiences/{self.published['slug']}/submissions",
            json=body or self._body(),
        )

    def test_valid_submission_persists_typed_values_consent_and_hashed_context_token(self) -> None:
        app.dependency_overrides.pop(get_current_auth_context, None)
        response = self._post()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["capabilities"], {"submissions": True, "calls": False})
        self.assertNotIn("tenant_id", response.text)
        self.assertNotIn("experience_id", response.text)
        with SessionLocal() as db:
            submission = db.scalars(select(TenantVoiceExperienceSubmission)).one()
            values = db.scalars(select(TenantVoiceExperienceSubmissionValue)).all()
            session = db.scalars(select(TenantVoiceContextSession)).one()
            self.assertIsNotNone(submission.consent_accepted_at)
            typed = {item.field_key: item.value_json for item in values}
            self.assertEqual(typed["guests"], 0)
            self.assertIs(typed["verified"], False)
            self.assertEqual(session.token_hash, hashlib.sha256(payload["context_token"].encode()).hexdigest())
            self.assertNotEqual(session.token_hash, payload["context_token"])
            self.assertEqual(db.query(CrmContact).count(), 1)

    def test_field_formats_options_and_lengths_use_stable_codes(self) -> None:
        cases = [
            ("email", "invalid", "invalid_format"),
            ("phone", "abc", "invalid_format"),
            ("date", "11/08/2026", "invalid_format"),
            ("plan", "enterprise", "invalid_option"),
            ("notes", "x" * 101, "too_long"),
        ]
        for key, value, expected in cases:
            with self.subTest(key=key):
                body = self._body()
                body["answers"][key] = value
                response = self._post(body)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn(
                    {"key": key, "code": expected},
                    response.json()["detail"]["fields"],
                )

    def test_strict_answer_types_reject_bool_float_number_and_nested_object(self) -> None:
        cases = [
            ("guests", True),
            ("guests", 1.0),
            ("verified", 1),
            ("full_name", 123),
            ("email", True),
            ("notes", {"nested": True}),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                body = self._body()
                body["answers"][key] = value
                response = self._post(body)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["detail"]["code"], "validation_error")
                self.assertNotIn("input", response.text)

    def test_required_integer_zero_and_checkbox_false_are_present(self) -> None:
        self.assertEqual(self._post().status_code, 200)

    def test_unknown_field_and_required_consent_use_stable_codes(self) -> None:
        body = self._body(consent=False)
        body["answers"]["internal"] = "leak"
        response = self._post(body)
        self.assertEqual(response.status_code, 422, response.text)
        fields = {(item["key"], item["code"]) for item in response.json()["detail"]["fields"]}
        self.assertIn(("internal", "unknown_field"), fields)
        self.assertIn(("consent", "consent_required"), fields)

    def test_version_mismatch_rolls_back_all_primary_rows(self) -> None:
        response = self._post(self._body(version=999))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "experience_version_changed")
        with SessionLocal() as db:
            self.assertEqual(db.query(TenantVoiceExperienceSubmission).count(), 0)
            self.assertEqual(db.query(TenantVoiceExperienceSubmissionValue).count(), 0)
            self.assertEqual(db.query(TenantVoiceContextSession).count(), 0)

    def test_turnstile_failure_is_closed_before_primary_transaction(self) -> None:
        self.verifier.accepted = False
        response = self._post()
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["detail"]["code"], "verification_failed")
        with SessionLocal() as db:
            self.assertEqual(db.query(TenantVoiceExperienceSubmission).count(), 0)

    def test_corrupt_supported_historical_validation_fails_closed(self) -> None:
        with SessionLocal() as db:
            field = db.scalar(select(TenantVoiceContextField).where(TenantVoiceContextField.key == "guests"))
            field.validation_json = {"min": "abc"}
            db.commit()
        response = self._post()
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["detail"], {"code": "validation_error", "fields": []})

    def test_malformed_json_consumes_global_quota_before_parsing(self) -> None:
        class _ThreeAttemptLimiter:
            def __init__(self) -> None:
                self.count = 0

            def consume(self, _scope: str, _limit: int) -> bool:
                self.count += 1
                return self.count <= 2

            def cleanup(self, **_kwargs) -> int:
                return 0

        limiter = _ThreeAttemptLimiter()
        app.dependency_overrides[get_public_rate_limiter] = lambda: limiter
        url = f"/api/v1/public/voice-experiences/{self.published['slug']}/submissions"
        first = self.client.post(url, content="{", headers={"Content-Type": "application/json"})
        second = self.client.post(url, content="{", headers={"Content-Type": "application/json"})
        third = self.client.post(url, content="{", headers={"Content-Type": "application/json"})
        self.assertEqual([first.status_code, second.status_code, third.status_code], [422, 422, 429])

    def test_local_phone_without_email_does_not_create_contact(self) -> None:
        body = self._body()
        body["answers"].pop("email")
        body["answers"]["phone"] = "3001112233"
        self.assertEqual(self._post(body).status_code, 200)
        with SessionLocal() as db:
            self.assertEqual(db.query(CrmContact).count(), 0)
            event = db.scalars(
                select(TenantIntegrationEvent).where(
                    TenantIntegrationEvent.event_type == "voice_experience_submission_crm"
                )
            ).one()
            self.assertEqual(event.status, "skipped")

    def test_crm_failure_isolated_after_primary_commit(self) -> None:
        with patch(
            "app.services.public_voice_submission_service.CrmContactService.get_or_create_contact",
            side_effect=RuntimeError("database unavailable"),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 200, response.text)
        with SessionLocal() as db:
            self.assertEqual(db.query(TenantVoiceExperienceSubmission).count(), 1)
            event = db.scalars(
                select(TenantIntegrationEvent).where(
                    TenantIntegrationEvent.event_type == "voice_experience_submission_crm"
                )
            ).one()
            self.assertEqual(event.status, "failed")
