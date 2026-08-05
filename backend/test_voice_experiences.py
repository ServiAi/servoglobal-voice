from __future__ import annotations

from unittest.mock import patch

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from _integrations_2a_test_base import Integration2ATestCase
from app.db.session import SessionLocal
from app.models.identity import TenantMembership, User
from app.models.integrations import TenantIntegrationEvent, TenantVoiceAgentConfig
from app.models.voice_context import TenantVoiceContextSchema
from app.models.voice_experiences import (
    TenantVoiceExperience,
    TenantVoiceExperienceVersion,
)
from app.schemas.voice_experiences import VoiceExperienceWriteRequest
from app.services.tenant_feature_service import VOICE_EXPERIENCES, TenantFeatureService
from app.services.voice_experience_service import (
    VoiceExperienceConflictError,
    VoiceExperienceService,
)


class VoiceExperienceTests(Integration2ATestCase):
    def setUp(self) -> None:
        super().setUp()
        self.agent_id = self._seed_agent(self.tenant.id, "agent-a")
        self.other_agent_id = self._seed_agent(self.tenant.id, "agent-b")
        self.active_schema_id = self._seed_schema(
            self.tenant.id, self.agent_id, "active", "active_schema"
        )
        self.draft_schema_id = self._seed_schema(
            self.tenant.id, self.agent_id, "draft", "draft_schema"
        )
        self.archived_schema_id = self._seed_schema(
            self.tenant.id, self.agent_id, "archived", "archived_schema"
        )

    @staticmethod
    def _seed_agent(tenant_id: str, provider_agent_id: str) -> str:
        with SessionLocal() as db:
            agent = TenantVoiceAgentConfig(
                tenant_id=tenant_id,
                provider="ultravox",
                provider_agent_id=provider_agent_id,
                display_name="Safe agent",
                default_system_prompt="private system prompt",
                default_tools_json={"private": "tool"},
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
            return agent.id

    @staticmethod
    def _seed_schema(tenant_id: str, agent_id: str, status: str, key: str) -> str:
        with SessionLocal() as db:
            schema = TenantVoiceContextSchema(
                tenant_id=tenant_id,
                agent_config_id=agent_id,
                schema_key=key,
                version=1,
                status=status,
                name=key.replace("_", " ").title(),
            )
            db.add(schema)
            db.commit()
            db.refresh(schema)
            return schema.id

    def _enable_feature(self, tenant_id: str | None = None, max_experiences: int = 3) -> None:
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(
                tenant_id or self.tenant.id,
                VOICE_EXPERIENCES,
                True,
                {"max_experiences": max_experiences, "max_context_fields": 8},
                self.user.id,
            )

    def _payload(
        self,
        *,
        agent_id: str | None = None,
        schema_id: str | None = None,
        name: str = "Customer intake",
        title: str = "Talk with us",
    ) -> dict:
        return {
            "agent_config_id": agent_id or self.agent_id,
            "context_schema_id": schema_id or self.active_schema_id,
            "name": name,
            "default_locale": "es",
            "content": {
                "title": title,
                "description": "A safe public description",
                "submit_label": "Continue",
                "call_label": "Start call",
                "success_message": "Ready",
            },
            "theme": {
                "logo_url": "https://example.com/logo.png",
                "primary_color": "#123ABC",
                "layout": "card",
            },
            "consent": {
                "required": True,
                "label": "I accept the privacy policy",
                "privacy_url": "https://example.com/privacy",
            },
            "call_settings": {
                "auto_start": False,
                "show_microphone_help": True,
                "language": "es",
            },
        }

    def _create(self, **payload_overrides):
        return self.client.post(
            "/api/v1/voice/experiences", json=self._payload(**payload_overrides)
        )

    def _assert_safe_event(self, event_type: str, experience_id: str) -> None:
        with SessionLocal() as db:
            event = db.scalar(
                select(TenantIntegrationEvent)
                .where(
                    TenantIntegrationEvent.tenant_id == self.tenant.id,
                    TenantIntegrationEvent.event_type == event_type,
                    TenantIntegrationEvent.resource_id == experience_id,
                )
                .order_by(TenantIntegrationEvent.created_at.desc())
            )
            self.assertIsNotNone(event)
            self.assertEqual(event.resource_type, "voice_experience")
            self.assertEqual(event.metadata_json["content_json"], "[omitted]")
            self.assertEqual(event.metadata_json["theme_json"], "[omitted]")

    def _set_actor(self, role: str, *, is_internal: bool = True) -> None:
        with SessionLocal() as db:
            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == self.tenant.id,
                    TenantMembership.user_id == self.user.id,
                )
            )
            membership.role = role
            db.get(User, self.user.id).is_internal = is_internal
            db.commit()

    def test_feature_disabled_is_forbidden(self) -> None:
        self.assertEqual(self._create().status_code, 403)
        self.assertEqual(self.client.get("/api/v1/voice/experiences").status_code, 403)

    def test_valid_creation_uses_stable_opaque_server_slug_and_safe_response(self) -> None:
        self._enable_feature()
        create = self._create(name="Alice Smith alice@example.com")
        self.assertEqual(create.status_code, 201, create.text)
        payload = create.json()
        self.assertEqual(payload["status"], "draft")
        self.assertNotIn("alice", payload["slug"].lower())
        self.assertNotIn("tenant_id", payload)
        self.assertNotIn("created_by_user_id", payload)
        self.assertNotIn("private system prompt", create.text.lower())
        original_slug = payload["slug"]
        update = self.client.put(
            f"/api/v1/voice/experiences/{payload['id']}", json=self._payload(name="Renamed")
        )
        self.assertEqual(update.status_code, 200, update.text)
        self.assertEqual(update.json()["slug"], original_slug)

    def test_max_experiences_counts_non_archived_only(self) -> None:
        self._enable_feature(max_experiences=1)
        first = self._create()
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(self._create(name="Blocked").status_code, 422)
        archived = self.client.post(
            f"/api/v1/voice/experiences/{first.json()['id']}/archive"
        )
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertEqual(self._create(name="Replacement").status_code, 201)

    def test_unpublished_experience_still_consumes_capacity(self) -> None:
        self._enable_feature(max_experiences=1)
        created = self._create().json()
        self.assertEqual(
            self.client.post(
                f"/api/v1/voice/experiences/{created['id']}/publish"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/voice/experiences/{created['id']}/unpublish"
            ).status_code,
            200,
        )
        self.assertEqual(self._create(name="Still blocked").status_code, 422)

    def test_agent_and_schema_tenant_and_agent_ownership(self) -> None:
        tenant_b, _ = self._seed_tenant_user(slug="tenant-b", email="b@example.com")
        agent_b = self._seed_agent(tenant_b.id, "agent-tenant-b")
        schema_b = self._seed_schema(tenant_b.id, agent_b, "active", "tenant_b")
        wrong_agent_schema = self._seed_schema(
            self.tenant.id, self.other_agent_id, "active", "other_agent"
        )
        self._enable_feature()
        self.assertEqual(self._create(agent_id=agent_b).status_code, 404)
        self.assertEqual(self._create(schema_id=schema_b).status_code, 404)
        self.assertEqual(self._create(schema_id=wrong_agent_schema).status_code, 422)

    def test_publish_requires_active_schema(self) -> None:
        self._enable_feature()
        draft = self._create(schema_id=self.draft_schema_id).json()["id"]
        archived = self._create(
            schema_id=self.archived_schema_id, name="Archived schema experience"
        ).json()["id"]
        self.assertEqual(
            self.client.post(f"/api/v1/voice/experiences/{draft}/publish").status_code,
            422,
        )
        self.assertEqual(
            self.client.post(f"/api/v1/voice/experiences/{archived}/publish").status_code,
            422,
        )

    def test_publish_versions_are_immutable_snapshots_and_unpublish_keeps_history(self) -> None:
        self._enable_feature()
        experience_id = self._create(title="Version one").json()["id"]
        first = self.client.post(
            f"/api/v1/voice/experiences/{experience_id}/publish"
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertIsNotNone(first.json()["published_version_id"])

        edited = self.client.put(
            f"/api/v1/voice/experiences/{experience_id}",
            json=self._payload(title="Edited draft"),
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        versions = self.client.get(
            f"/api/v1/voice/experiences/{experience_id}/versions"
        )
        self.assertEqual(versions.status_code, 200, versions.text)
        self.assertEqual(versions.json()[0]["version"], 1)
        self.assertEqual(versions.json()[0]["content"]["title"], "Version one")

        unpublished = self.client.post(
            f"/api/v1/voice/experiences/{experience_id}/unpublish"
        )
        self.assertEqual(unpublished.status_code, 200, unpublished.text)
        self.assertIsNone(unpublished.json()["published_version_id"])
        self.assertEqual(
            len(
                self.client.get(
                    f"/api/v1/voice/experiences/{experience_id}/versions"
                ).json()
            ),
            1,
        )
        second = self.client.post(
            f"/api/v1/voice/experiences/{experience_id}/publish"
        )
        self.assertEqual(second.status_code, 200, second.text)
        versions = self.client.get(
            f"/api/v1/voice/experiences/{experience_id}/versions"
        ).json()
        self.assertEqual([item["version"] for item in versions], [2, 1])
        self.assertEqual(versions[0]["content"]["title"], "Edited draft")
        self.assertEqual(versions[1]["content"]["title"], "Version one")

    def test_published_must_be_unpublished_before_archive(self) -> None:
        self._enable_feature()
        experience_id = self._create().json()["id"]
        self.client.post(f"/api/v1/voice/experiences/{experience_id}/publish")
        response = self.client.post(
            f"/api/v1/voice/experiences/{experience_id}/archive"
        )
        self.assertEqual(response.status_code, 409)

    def test_archived_experience_is_immutable(self) -> None:
        self._enable_feature()
        experience_id = self._create().json()["id"]
        self.client.post(f"/api/v1/voice/experiences/{experience_id}/archive")
        self.assertEqual(
            self.client.put(
                f"/api/v1/voice/experiences/{experience_id}", json=self._payload()
            ).status_code,
            409,
        )
        for action in ("publish", "unpublish", "archive"):
            self.assertEqual(
                self.client.post(
                    f"/api/v1/voice/experiences/{experience_id}/{action}"
                ).status_code,
                409,
            )

    def test_request_and_nested_json_forbid_extra_fields(self) -> None:
        self._enable_feature()
        top_level = self._payload()
        top_level["tenant_id"] = self.tenant.id
        nested = self._payload()
        nested["content"]["system_prompt"] = "forbidden"
        self.assertEqual(
            self.client.post("/api/v1/voice/experiences", json=top_level).status_code,
            422,
        )
        self.assertEqual(
            self.client.post("/api/v1/voice/experiences", json=nested).status_code,
            422,
        )

    def test_urls_consent_and_color_are_validated(self) -> None:
        self._enable_feature()
        insecure = self._payload()
        insecure["theme"]["logo_url"] = "http://example.com/logo.png"
        missing_label = self._payload()
        missing_label["consent"]["label"] = ""
        bad_color = self._payload()
        bad_color["theme"]["primary_color"] = "red"
        for payload in (insecure, missing_label, bad_color):
            self.assertEqual(
                self.client.post("/api/v1/voice/experiences", json=payload).status_code,
                422,
            )

    def test_read_and_write_roles(self) -> None:
        self._enable_feature()
        experience_id = self._create().json()["id"]
        for role in ("platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"):
            self._set_actor(role)
            self.assertEqual(
                self.client.get(f"/api/v1/voice/experiences/{experience_id}").status_code,
                200,
            )
        for role in ("tenant_analyst", "tenant_viewer"):
            self._set_actor(role)
            self.assertEqual(
                self.client.put(
                    f"/api/v1/voice/experiences/{experience_id}", json=self._payload()
                ).status_code,
                403,
            )
        for role in ("tenant_admin", "platform_admin"):
            self._set_actor(role)
            self.assertEqual(
                self.client.put(
                    f"/api/v1/voice/experiences/{experience_id}", json=self._payload()
                ).status_code,
                200,
            )

    def test_non_internal_platform_admin_is_forbidden(self) -> None:
        self._enable_feature()
        self._set_actor("platform_admin", is_internal=False)
        self.assertEqual(self.client.get("/api/v1/voice/experiences").status_code, 403)
        self.assertEqual(self._create().status_code, 403)

    def test_multi_tenant_isolation_uses_real_rows(self) -> None:
        tenant_b, user_b = self._seed_tenant_user(slug="tenant-b", email="b@example.com")
        agent_b = self._seed_agent(tenant_b.id, "agent-b")
        schema_b = self._seed_schema(tenant_b.id, agent_b, "active", "schema_b")
        self._enable_feature(tenant_b.id)
        with SessionLocal() as db:
            experience = VoiceExperienceService(db).create_experience(
                tenant_b.id,
                VoiceExperienceWriteRequest.model_validate(
                    self._payload(agent_id=agent_b, schema_id=schema_b)
                ),
                user_b.id,
            )
            other_id = experience.id
        self._enable_feature()
        self.assertEqual(
            self.client.get(f"/api/v1/voice/experiences/{other_id}").status_code, 404
        )
        self.assertEqual(self.client.get("/api/v1/voice/experiences").json(), [])

    def test_create_records_safe_integration_event(self) -> None:
        self._enable_feature()
        created = self._create()
        self.assertEqual(created.status_code, 201, created.text)
        self._assert_safe_event("voice_experience_created", created.json()["id"])

    def test_publish_records_safe_integration_event(self) -> None:
        self._enable_feature()
        experience_id = self._create().json()["id"]
        published = self.client.post(
            f"/api/v1/voice/experiences/{experience_id}/publish"
        )
        self.assertEqual(published.status_code, 200, published.text)
        self._assert_safe_event("voice_experience_published", experience_id)

    def test_unpublish_records_safe_integration_event(self) -> None:
        self._enable_feature()
        experience_id = self._create().json()["id"]
        self.client.post(f"/api/v1/voice/experiences/{experience_id}/publish")
        unpublished = self.client.post(
            f"/api/v1/voice/experiences/{experience_id}/unpublish"
        )
        self.assertEqual(unpublished.status_code, 200, unpublished.text)
        self._assert_safe_event("voice_experience_unpublished", experience_id)

    def test_archive_records_safe_integration_event(self) -> None:
        self._enable_feature()
        experience_id = self._create().json()["id"]
        archived = self.client.post(
            f"/api/v1/voice/experiences/{experience_id}/archive"
        )
        self.assertEqual(archived.status_code, 200, archived.text)
        self._assert_safe_event("voice_experience_archived", experience_id)

    def test_get_current_published_version_returns_latest_after_unpublish(self) -> None:
        self._enable_feature()
        experience_id = self._create().json()["id"]
        self.client.post(f"/api/v1/voice/experiences/{experience_id}/publish")
        self.client.post(f"/api/v1/voice/experiences/{experience_id}/unpublish")

        with SessionLocal() as db:
            version = VoiceExperienceService(db).get_current_published_version(
                self.tenant.id, experience_id
            )
            self.assertIsNotNone(version)
            self.assertEqual(version.version, 1)

    def test_consent_label_is_optional_when_consent_is_not_required(self) -> None:
        self._enable_feature()
        payload = self._payload()
        payload["consent"]["required"] = False
        payload["consent"]["label"] = None
        created = self.client.post("/api/v1/voice/experiences", json=payload)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertIsNone(created.json()["consent"]["label"])

    def test_slug_collision_maps_to_conflict(self) -> None:
        self._enable_feature()
        collision = IntegrityError(
            "INSERT",
            {},
            Exception("UNIQUE constraint failed: tenant_voice_experiences.slug"),
        )
        real_flush = SessionLocal.class_.flush

        def collide_only_for_experience(db, *args, **kwargs):
            if any(isinstance(item, TenantVoiceExperience) for item in db.new):
                raise collision
            return real_flush(db, *args, **kwargs)

        with patch.object(
            SessionLocal.class_, "flush", new=collide_only_for_experience
        ):
            response = self._create()
        self.assertEqual(response.status_code, 409, response.text)

    def test_concurrent_publish_collision_cannot_create_duplicate_version(self) -> None:
        self._enable_feature()
        experience_id = self._create().json()["id"]
        collision = IntegrityError(
            "INSERT",
            {},
            Exception(
                "UNIQUE constraint failed: "
                "tenant_voice_experience_versions.experience_id, "
                "tenant_voice_experience_versions.version"
            ),
        )
        with SessionLocal() as db:
            service = VoiceExperienceService(db)
            real_flush = db.flush

            def collide_only_for_version(*args, **kwargs):
                if any(isinstance(item, TenantVoiceExperienceVersion) for item in db.new):
                    raise collision
                return real_flush(*args, **kwargs)

            with (
                patch.object(db, "flush", side_effect=collide_only_for_version),
                self.assertRaises(VoiceExperienceConflictError),
            ):
                service.publish_experience(self.tenant.id, experience_id, self.user.id)
        with SessionLocal() as db:
            self.assertEqual(
                len(list(db.scalars(select(TenantVoiceExperienceVersion)).all())), 0
            )

    def test_unknown_integrity_error_is_re_raised(self) -> None:
        self._enable_feature()
        experience_id = self._create().json()["id"]
        unknown = IntegrityError("INSERT", {}, Exception("unexpected constraint"))
        with SessionLocal() as db:
            service = VoiceExperienceService(db)
            real_flush = db.flush

            def fail_only_for_version(*args, **kwargs):
                if any(isinstance(item, TenantVoiceExperienceVersion) for item in db.new):
                    raise unknown
                return real_flush(*args, **kwargs)

            with (
                patch.object(db, "flush", side_effect=fail_only_for_version),
                self.assertRaises(IntegrityError),
            ):
                service.publish_experience(self.tenant.id, experience_id, self.user.id)

    def test_alembic_has_one_head(self) -> None:
        heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
        self.assertEqual(heads, ["202608050002"])
