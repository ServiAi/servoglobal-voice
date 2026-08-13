from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from _integrations_2a_test_base import Integration2ATestCase
from app.api.auth.deps import get_current_auth_context
from app.api.endpoints.voice_public import (
    get_public_rate_limiter,
    get_public_turnstile_verifier,
)
from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.crm import CrmActivity, CrmContact, CrmLead
from app.models.integrations import TenantIntegrationEvent, TenantVoiceAgentConfig
from app.models.voice_context import TenantVoiceContextField, TenantVoiceContextSchema
from app.models.voice_experiences import TenantVoiceExperience, TenantVoiceExperienceVersion
from app.models.voice_submissions import (
    TenantVoiceContextSession,
    TenantVoiceExperienceSubmission,
    TenantVoiceExperienceSubmissionValue,
)
from app.services.tenant_feature_service import VOICE_EXPERIENCES, TenantFeatureService
from app.services.voice_experience_service import VoiceExperienceService


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

    async def verify(self, token: str | None, _remote_ip: str) -> bool:
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
            ("client_email", "email", False, {}, []),
            ("mobile_number", "phone", False, {}, []),
            ("company", "text", False, {}, []),
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
                "client_email": "ana@example.com",
                "mobile_number": "+573001112233",
                "company": "ServiAI",
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
        self.assertEqual(payload["capabilities"], {"submissions": True, "calls": True})
        self.assertNotIn("tenant_id", response.text)
        self.assertNotIn("experience_id", response.text)
        with SessionLocal() as db:
            submission = db.scalars(select(TenantVoiceExperienceSubmission)).one()
            values = db.scalars(select(TenantVoiceExperienceSubmissionValue)).all()
            session = db.scalars(select(TenantVoiceContextSession)).one()
            self.assertIsNotNone(submission.consent_accepted_at)
            self.assertEqual(submission.version, 1)
            self.assertEqual(submission.locale, "es")
            typed = {item.field_key: item.value_json for item in values}
            self.assertEqual(typed["guests"], 0)
            self.assertIs(typed["verified"], False)
            self.assertTrue(all(item.tenant_id == self.tenant.id for item in values))
            self.assertTrue(all(item.created_at is not None for item in values))
            self.assertEqual(session.token_hash, hashlib.sha256(payload["context_token"].encode()).hexdigest())
            self.assertNotEqual(session.token_hash, payload["context_token"])
            self.assertEqual(session.status, "active")
            self.assertIsNone(session.consumed_at)
            self.assertEqual(db.query(CrmContact).count(), 1)
            self.assertEqual(db.query(CrmLead).count(), 1)
            activity = db.scalars(select(CrmActivity)).one()
            self.assertEqual(activity.activity_type, "voice_experience_submitted")
            self.assertEqual(activity.payload_json["context_id"], submission.id)
            self.assertNotIn("email", activity.payload_json)
            self.assertEqual(submission.crm_contact_id, activity.contact_id)
            self.assertEqual(submission.crm_lead_id, activity.lead_id)
            event = db.scalars(
                select(TenantIntegrationEvent).where(
                    TenantIntegrationEvent.event_type == "voice_experience_submission_crm"
                )
            ).one()
            self.assertEqual(event.status, "success")
            self.assertEqual(event.metadata_json, {
                "experience_id": submission.experience_id,
                "version": 1,
            })

    def test_delete_archived_experience_removes_context_data_and_history(self) -> None:
        app.dependency_overrides.pop(get_current_auth_context, None)
        self.assertEqual(self._post().status_code, 200)
        experience_id = self.published["id"]
        with SessionLocal() as db:
            service = VoiceExperienceService(db)
            service.unpublish_experience(self.tenant.id, experience_id, self.user.id)
            service.archive_experience(self.tenant.id, experience_id, self.user.id)
            service.delete_experience(self.tenant.id, experience_id, self.user.id)

            self.assertIsNone(db.get(TenantVoiceExperience, experience_id))
            self.assertEqual(db.query(TenantVoiceExperienceVersion).count(), 0)
            self.assertEqual(db.query(TenantVoiceExperienceSubmission).count(), 0)
            self.assertEqual(db.query(TenantVoiceExperienceSubmissionValue).count(), 0)
            self.assertEqual(db.query(TenantVoiceContextSession).count(), 0)

    def test_field_formats_options_and_lengths_use_stable_codes(self) -> None:
        cases = [
            ("client_email", "invalid", "invalid_format"),
            ("mobile_number", "abc", "invalid_format"),
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
            ("client_email", True),
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
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.json()["detail"], {"code": "internal_error", "fields": []})

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
        body["answers"].pop("client_email")
        body["answers"]["mobile_number"] = "3001112233"
        self.assertEqual(self._post(body).status_code, 200)
        with SessionLocal() as db:
            self.assertEqual(db.query(CrmContact).count(), 0)
            event = db.scalars(
                select(TenantIntegrationEvent).where(
                    TenantIntegrationEvent.event_type == "voice_experience_submission_crm"
                )
            ).one()
            self.assertEqual(event.status, "skipped")

    def test_context_session_lifecycle_is_atomic_and_one_to_one(self) -> None:
        self.assertEqual(self._post().status_code, 200)
        consumed_at = datetime.now(UTC)
        with SessionLocal() as db:
            session = db.scalars(select(TenantVoiceContextSession)).one()
            self.assertTrue(session.mark_consumed(db, now=consumed_at))
            self.assertEqual(session.status, "consumed")
            self.assertEqual(session.consumed_at.replace(tzinfo=UTC), consumed_at)
            self.assertFalse(session.mark_consumed(db, now=consumed_at + timedelta(seconds=1)))

            duplicate = TenantVoiceContextSession(
                tenant_id=session.tenant_id,
                submission_id=session.submission_id,
                experience_id=session.experience_id,
                experience_version_id=session.experience_version_id,
                context_schema_id=session.context_schema_id,
                token_hash="f" * 64,
                expires_at=session.expires_at,
            )
            db.add(duplicate)
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

    def test_expired_context_session_cannot_be_consumed(self) -> None:
        self.assertEqual(self._post().status_code, 200)
        now = datetime.now(UTC)
        with SessionLocal() as db:
            session = db.scalars(select(TenantVoiceContextSession)).one()
            session.expires_at = now - timedelta(seconds=1)
            db.commit()
            self.assertFalse(session.mark_consumed(db, now=now))
            self.assertEqual(session.status, "expired")
            self.assertIsNone(session.consumed_at)

    def test_null_answers_are_not_persisted_and_url_locale_is_stored_exactly(self) -> None:
        body = self._body(locale="en")
        body["answers"]["notes"] = None
        response = self._post(body)
        self.assertEqual(response.status_code, 200, response.text)
        with SessionLocal() as db:
            submission = db.scalars(select(TenantVoiceExperienceSubmission)).one()
            self.assertEqual(submission.locale, "en")
            self.assertNotIn(
                "notes",
                {value.field_key for value in db.scalars(select(TenantVoiceExperienceSubmissionValue))},
            )

        invalid = self._body(locale="en-US")
        self.assertEqual(self._post(invalid).status_code, 422)

    def test_missing_empty_invalid_and_verifier_error_are_verification_failed(self) -> None:
        self.verifier.accepted = False
        bodies = [self._body(), self._body(turnstile_token=""), self._body(turnstile_token="invalid")]
        bodies[0].pop("turnstile_token")
        for body in bodies:
            with self.subTest(token=body.get("turnstile_token")):
                response = self._post(body)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["detail"]["code"], "verification_failed")

        class _FailingVerifier:
            async def verify(self, _token, _remote_ip):
                raise TimeoutError

        app.dependency_overrides[get_public_turnstile_verifier] = _FailingVerifier
        response = self._post()
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["detail"]["code"], "verification_failed")

    def test_envelope_and_global_field_limits(self) -> None:
        envelope_cases = [
            self._body(hp="x" * 201),
            self._body(turnstile_token="x" * 2049),
            self._body(answers={f"field_{index}": "x" for index in range(101)}),
            self._body(answers={"x" * 81: "value"}),
            self._body(answers={f"field_{index}": "x" * 600 for index in range(100)}),
        ]
        for body in envelope_cases:
            with self.subTest(case=len(str(body))):
                response = self._post(body)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["detail"]["code"], "validation_error")

        field_cases = [
            ("full_name", "x" * 201, "too_long"),
            ("notes", "x" * 5001, "too_long"),
            ("client_email", f"{'x' * 243}@example.com", "too_long"),
            ("mobile_number", "+" + "1" * 32, "too_long"),
            ("guests", 1_000_000_001, "invalid_format"),
            ("guests", -1_000_000_001, "invalid_format"),
            ("date", "1899-12-31", "invalid_format"),
            ("date", "2101-01-01", "invalid_format"),
            ("date", "2026-02-30", "invalid_format"),
        ]
        for key, value, code in field_cases:
            with self.subTest(field=key, value=value):
                body = self._body()
                body["answers"][key] = value
                response = self._post(body)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn({"key": key, "code": code}, response.json()["detail"]["fields"])

    def test_historical_validation_cannot_expand_global_limits(self) -> None:
        with SessionLocal() as db:
            db.scalar(select(TenantVoiceContextField).where(TenantVoiceContextField.key == "notes")).validation_json = {"max_length": 10_000}
            db.scalar(select(TenantVoiceContextField).where(TenantVoiceContextField.key == "guests")).validation_json = {"max": 2_000_000_000}
            db.commit()
        for key, value in (("notes", "x" * 5001), ("guests", 1_000_000_001)):
            body = self._body()
            body["answers"][key] = value
            self.assertEqual(self._post(body).status_code, 422)

    def test_non_public_states_fail_closed_and_exact_historical_schema_is_used(self) -> None:
        experience_id = self.published["id"]
        with SessionLocal() as db:
            experience = db.get(TenantVoiceExperience, experience_id)
            published_version_id = experience.published_version_id
            for state, version_id in (("draft", published_version_id), ("archived", published_version_id), ("published", None)):
                experience.status = state
                experience.published_version_id = version_id
                db.commit()
                with self.subTest(state=state, version_id=version_id):
                    self.assertEqual(self._post().status_code, 404)
            experience.status = "published"
            experience.published_version_id = published_version_id
            db.commit()

        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(
                self.tenant.id,
                VOICE_EXPERIENCES,
                False,
                {"max_experiences": 10, "max_context_fields": 20},
                self.user.id,
            )
        self.assertEqual(self._post().status_code, 404)
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(
                self.tenant.id,
                VOICE_EXPERIENCES,
                True,
                {"max_experiences": 10, "max_context_fields": 20},
                self.user.id,
            )
            schema = db.get(TenantVoiceContextSchema, self.schema_id)
            schema.status = "archived"
            alternate = TenantVoiceContextSchema(
                tenant_id=self.tenant.id,
                agent_config_id=self.agent_id,
                schema_key="alternate-schema",
                version=1,
                status="active",
                name="Alternate schema",
            )
            db.add(alternate)
            db.flush()
            db.get(TenantVoiceExperience, experience_id).context_schema_id = alternate.id
            db.commit()

        response = self._post()
        self.assertEqual(response.status_code, 200, response.text)
        with SessionLocal() as db:
            submission = db.scalars(select(TenantVoiceExperienceSubmission)).one()
            self.assertEqual(submission.context_schema_id, self.schema_id)

    def test_non_public_collection_modes_are_rejected_as_unknown_answers(self) -> None:
        with SessionLocal() as db:
            db.add_all([
                TenantVoiceContextField(
                    tenant_id=self.tenant.id, schema_id=self.schema_id, key=key,
                    label=key, field_type="text", collection_mode=mode,
                    required=False, position=100 + index, sensitivity="standard",
                    validation_json={}, options_json=[],
                )
                for index, (key, mode) in enumerate((
                    ("internal_note", "internal_only"),
                    ("call_note", "collect_during_call"),
                ))
            ])
            db.commit()
        body = self._body()
        body["answers"].update({"internal_note": "hidden", "call_note": "hidden"})
        response = self._post(body)
        self.assertEqual(response.status_code, 422, response.text)
        fields = response.json()["detail"]["fields"]
        self.assertIn({"key": "internal_note", "code": "unknown_field"}, fields)
        self.assertIn({"key": "call_note", "code": "unknown_field"}, fields)

    def test_internal_failures_are_generic_and_logs_exclude_request_data(self) -> None:
        sensitive = self._body(turnstile_token="sensitive-token")
        sensitive["answers"]["client_email"] = "private@example.com"
        with patch(
            "app.services.public_voice_submission_service.PublicVoiceSubmissionService.pre_resolve",
            side_effect=RuntimeError("private@example.com sensitive-token 127.0.0.1"),
        ), patch("app.api.endpoints.voice_public.logger.error") as logged:
            response = self._post(sensitive)
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.json()["detail"], {"code": "internal_error", "fields": []})
        self.assertNotIn("private@example.com", str(logged.call_args_list))

        with patch(
            "app.services.public_voice_submission_service.PublicVoiceSubmissionService.persist",
            side_effect=RuntimeError("private@example.com sensitive-token 127.0.0.1"),
        ), patch("app.api.endpoints.voice_public.logger.error") as logged:
            response = self._post(sensitive)
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.json()["detail"], {"code": "internal_error", "fields": []})
        rendered_logs = str(logged.call_args_list)
        self.assertNotIn("private@example.com", rendered_logs)
        self.assertNotIn("sensitive-token", rendered_logs)
        self.assertNotIn("127.0.0.1", rendered_logs)

        class _BrokenLimiter:
            def consume(self, _scope, _limit):
                raise RuntimeError("database unavailable")

            def cleanup(self, **_kwargs):
                return 0

        app.dependency_overrides[get_public_rate_limiter] = _BrokenLimiter
        response = self._post()
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.json()["detail"]["code"], "internal_error")

    def test_crm_failure_isolated_after_primary_commit(self) -> None:
        with patch(
            "app.services.public_voice_submission_service.CrmContactService.get_or_create_contact",
            side_effect=RuntimeError("database unavailable"),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 200, response.text)
        with SessionLocal() as db:
            self.assertEqual(db.query(TenantVoiceExperienceSubmission).count(), 1)
            self.assertEqual(db.query(TenantVoiceExperienceSubmissionValue).count(), len(self._body()["answers"]))
            self.assertEqual(db.query(TenantVoiceContextSession).count(), 1)
            event = db.scalars(
                select(TenantIntegrationEvent).where(
                    TenantIntegrationEvent.event_type == "voice_experience_submission_crm"
                )
            ).one()
            self.assertEqual(event.status, "failed")
            self.assertEqual(event.metadata_json["version"], 1)
            self.assertNotIn("answers", event.metadata_json)
