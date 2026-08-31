from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from _integrations_2a_test_base import Integration2ATestCase
from app.db.session import SessionLocal
from app.models.identity import TenantMembership, User
from app.models.integrations import TenantVoiceAgentConfig
from app.models.voice_context import TenantVoiceContextField, TenantVoiceContextSchema
from app.models.voice_experiences import TenantVoiceExperience, TenantVoiceExperienceVersion
from app.services.integration_event_service import IntegrationEventService
from app.services.tenant_feature_service import TenantFeatureService, VOICE_EXPERIENCES
from app.services.voice_context_service import (
    ACTIVE_LINEAGE_INDEX,
    VoiceContextService,
)


class VoiceContextSchemaTests(Integration2ATestCase):
    def setUp(self) -> None:
        super().setUp()
        self.agent_id = self._seed_agent(self.tenant.id, "agent-a")

    def _enable_feature(
        self,
        tenant_id: str | None = None,
        *,
        max_experiences: int = 3,
        max_context_fields: int = 8,
    ) -> None:
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(
                tenant_id or self.tenant.id,
                VOICE_EXPERIENCES,
                True,
                {
                    "max_experiences": max_experiences,
                    "max_context_fields": max_context_fields,
                },
                self.user.id,
            )

    @staticmethod
    def _seed_agent(tenant_id: str, provider_agent_id: str) -> str:
        with SessionLocal() as db:
            agent = TenantVoiceAgentConfig(
                tenant_id=tenant_id,
                provider="ultravox",
                provider_agent_id=provider_agent_id,
                display_name="Safe voice agent",
                default_system_prompt="secret system prompt",
                default_tools_json={"private": "tool configuration"},
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
            return agent.id

    def _create_schema(
        self,
        *,
        agent_id: str | None = None,
        schema_key: str = "lead_intake",
        name: str = "Lead intake",
    ):
        return self.client.post(
            f"/api/v1/voice/agents/{agent_id or self.agent_id}/context-schemas",
            json={"schema_key": schema_key, "name": name, "description": "Safe metadata"},
        )

    def _field_payload(
        self,
        *,
        key: str = "customer_email",
        position: int = 0,
        field_type: str = "email",
        collection_mode: str = "ask_if_missing",
        description: str | None = "Collected during qualification",
        options_json: list[dict] | None = None,
    ) -> dict:
        return {
            "key": key,
            "label": key.replace("_", " ").title(),
            "description": description,
            "field_type": field_type,
            "collection_mode": collection_mode,
            "required": True,
            "position": position,
            "sensitivity": "sensitive" if field_type in {"email", "phone"} else "standard",
            "validation_json": {},
            "options_json": options_json
            if options_json is not None
            else ([{"value": "one", "label": "One"}] if field_type == "select" else []),
        }

    def _add_field(self, schema_id: str, **overrides):
        return self.client.post(
            f"/api/v1/voice/context-schemas/{schema_id}/fields",
            json=self._field_payload(**overrides),
        )

    @staticmethod
    def _experience_payload(schema_id: str, agent_id: str) -> dict:
        return {
            "agent_config_id": agent_id,
            "context_schema_id": schema_id,
            "name": "Customer intake",
            "default_locale": "es",
            "content": {
                "title": "Talk with us",
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

    def _create_ready_schema(self, *, schema_key: str = "lead_intake") -> str:
        response = self._create_schema(schema_key=schema_key)
        self.assertEqual(response.status_code, 201, response.text)
        schema_id = response.json()["id"]
        field_response = self._add_field(schema_id)
        self.assertEqual(field_response.status_code, 201, field_response.text)
        return schema_id

    def _set_actor(self, role: str, *, is_internal: bool | None = None) -> None:
        with SessionLocal() as db:
            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == self.tenant.id,
                    TenantMembership.user_id == self.user.id,
                )
            )
            membership.role = role
            if is_internal is not None:
                db.get(User, self.user.id).is_internal = is_internal
            db.commit()

    def test_feature_disabled_is_forbidden(self) -> None:
        response = self._create_schema()
        self.assertEqual(response.status_code, 403)

    def test_agent_from_another_tenant_is_not_found(self) -> None:
        tenant_b, _ = self._seed_tenant_user(slug="tenant-b", email="other@example.com")
        other_agent_id = self._seed_agent(tenant_b.id, "agent-b")
        self._enable_feature()
        response = self._create_schema(agent_id=other_agent_id)
        self.assertEqual(response.status_code, 404)

    def test_create_list_detail_and_safe_response(self) -> None:
        self._enable_feature()
        create = self._create_schema()
        self.assertEqual(create.status_code, 201, create.text)
        payload = create.json()
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["version"], 1)
        self.assertNotIn("tenant_id", payload)
        self.assertNotIn("created_by_user_id", payload)
        serialized = create.text.lower()
        self.assertNotIn("secret system prompt", serialized)
        self.assertNotIn("tool configuration", serialized)

        listing = self.client.get(
            f"/api/v1/voice/agents/{self.agent_id}/context-schemas"
        )
        detail = self.client.get(f"/api/v1/voice/context-schemas/{payload['id']}")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()), 1)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["schema_key"], "lead_intake")

    def test_field_types_and_collection_modes_are_validated(self) -> None:
        self._enable_feature()
        schema_id = self._create_schema().json()["id"]
        invalid_type = self._add_field(schema_id, field_type="password")
        invalid_mode = self._add_field(schema_id, collection_mode="always_ask")
        invalid_key = self._add_field(schema_id, key="Not Snake Case")
        self.assertEqual(invalid_type.status_code, 422)
        self.assertEqual(invalid_mode.status_code, 422)
        self.assertEqual(invalid_key.status_code, 422)

    def test_all_supported_field_types_can_be_created(self) -> None:
        self._enable_feature(max_context_fields=8)
        schema_id = self._create_schema().json()["id"]
        for position, field_type in enumerate(
            ["text", "textarea", "email", "phone", "integer", "select", "checkbox", "date"]
        ):
            response = self._add_field(
                schema_id,
                key=f"field_{position}",
                position=position,
                field_type=field_type,
                collection_mode="collect_during_call",
            )
            self.assertEqual(response.status_code, 201, response.text)

    def test_duplicate_field_key_does_not_persist(self) -> None:
        self._enable_feature()
        schema_id = self._create_schema().json()["id"]
        self.assertEqual(self._add_field(schema_id).status_code, 201)
        duplicate = self._add_field(schema_id, position=1)
        self.assertEqual(duplicate.status_code, 422)
        detail = self.client.get(f"/api/v1/voice/context-schemas/{schema_id}")
        self.assertEqual(len(detail.json()["fields"]), 1)

    def test_duplicate_field_position_has_specific_error_and_does_not_persist(self) -> None:
        self._enable_feature()
        schema_id = self._create_schema().json()["id"]
        self.assertEqual(self._add_field(schema_id).status_code, 201)
        duplicate = self._add_field(
            schema_id, key="customer_phone", position=0, field_type="phone"
        )
        self.assertEqual(duplicate.status_code, 422)
        self.assertEqual(
            duplicate.json()["detail"],
            "Field position already exists in this schema.",
        )
        detail = self.client.get(f"/api/v1/voice/context-schemas/{schema_id}")
        self.assertEqual(len(detail.json()["fields"]), 1)

    def test_select_requires_options(self) -> None:
        self._enable_feature()
        schema_id = self._create_schema().json()["id"]
        response = self._add_field(
            schema_id, field_type="select", options_json=[]
        )
        self.assertEqual(response.status_code, 422)

    def test_select_accepts_typed_options_and_returns_description(self) -> None:
        self._enable_feature()
        schema_id = self._create_schema().json()["id"]
        response = self._add_field(
            schema_id,
            field_type="select",
            description="Preferred contact channel",
            options_json=[
                {"value": "email", "label": "Email"},
                {"value": "phone", "label": "Phone"},
            ],
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["description"], "Preferred contact channel")
        self.assertEqual(len(response.json()["options_json"]), 2)

    def test_select_rejects_duplicate_option_values(self) -> None:
        self._enable_feature()
        schema_id = self._create_schema().json()["id"]
        response = self._add_field(
            schema_id,
            field_type="select",
            options_json=[
                {"value": "same", "label": "One"},
                {"value": "same", "label": "Two"},
            ],
        )
        self.assertEqual(response.status_code, 422)

    def test_email_rejects_options(self) -> None:
        self._enable_feature()
        schema_id = self._create_schema().json()["id"]
        response = self._add_field(
            schema_id,
            field_type="email",
            options_json=[{"value": "one", "label": "One"}],
        )
        self.assertEqual(response.status_code, 422)

    def test_text_rejects_options(self) -> None:
        self._enable_feature()
        schema_id = self._create_schema().json()["id"]
        response = self._add_field(
            schema_id,
            field_type="text",
            options_json=[{"value": "one", "label": "One"}],
        )
        self.assertEqual(response.status_code, 422)

    def test_option_requires_value(self) -> None:
        self._enable_feature()
        schema_id = self._create_schema().json()["id"]
        response = self._add_field(
            schema_id,
            field_type="select",
            options_json=[{"label": "One"}],
        )
        self.assertEqual(response.status_code, 422)

    def test_option_requires_label(self) -> None:
        self._enable_feature()
        schema_id = self._create_schema().json()["id"]
        response = self._add_field(
            schema_id,
            field_type="select",
            options_json=[{"value": "one"}],
        )
        self.assertEqual(response.status_code, 422)

    def test_option_forbids_additional_fields(self) -> None:
        self._enable_feature()
        schema_id = self._create_schema().json()["id"]
        response = self._add_field(
            schema_id,
            field_type="select",
            options_json=[{"value": "one", "label": "One", "secret": "no"}],
        )
        self.assertEqual(response.status_code, 422)

    def test_max_context_fields_is_enforced(self) -> None:
        self._enable_feature(max_context_fields=1)
        schema_id = self._create_schema().json()["id"]
        self.assertEqual(self._add_field(schema_id).status_code, 201)
        response = self._add_field(schema_id, key="second_field", position=1)
        self.assertEqual(response.status_code, 422)

    def test_max_experiences_does_not_limit_context_schemas_or_other_lineages(self) -> None:
        self._enable_feature(max_experiences=1)
        first_id = self._create_ready_schema(schema_key="first")
        second_id = self._create_ready_schema(schema_key="second")
        first = self.client.post(
            f"/api/v1/voice/context-schemas/{first_id}/activate"
        )
        second = self.client.post(
            f"/api/v1/voice/context-schemas/{second_id}/activate"
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)

    def test_activation_archives_prior_active_version_and_versions_are_unique(self) -> None:
        self._enable_feature()
        first_id = self._create_ready_schema()
        first_active = self.client.post(
            f"/api/v1/voice/context-schemas/{first_id}/activate"
        )
        self.assertEqual(first_active.status_code, 200, first_active.text)

        fork = self.client.post(
            f"/api/v1/voice/context-schemas/{first_id}/new-version"
        )
        self.assertEqual(fork.status_code, 201, fork.text)
        self.assertEqual(fork.json()["version"], 2)
        self.assertEqual(
            fork.json()["fields"][0]["description"],
            "Collected during qualification",
        )
        second_id = fork.json()["id"]
        second_active = self.client.post(
            f"/api/v1/voice/context-schemas/{second_id}/activate"
        )
        self.assertEqual(second_active.status_code, 200, second_active.text)

        with SessionLocal() as db:
            versions = list(
                db.scalars(
                    select(TenantVoiceContextSchema)
                    .where(TenantVoiceContextSchema.schema_key == "lead_intake")
                    .order_by(TenantVoiceContextSchema.version)
                ).all()
            )
            self.assertEqual([item.version for item in versions], [1, 2])
            self.assertEqual([item.status for item in versions], ["archived", "active"])

    def test_database_allows_only_one_active_per_lineage(self) -> None:
        with SessionLocal() as db:
            db.add_all(
                [
                    TenantVoiceContextSchema(
                        tenant_id=self.tenant.id,
                        agent_config_id=self.agent_id,
                        schema_key="single_active",
                        version=1,
                        status="active",
                        name="Version 1",
                    ),
                    TenantVoiceContextSchema(
                        tenant_id=self.tenant.id,
                        agent_config_id=self.agent_id,
                        schema_key="single_active",
                        version=2,
                        status="active",
                        name="Version 2",
                    ),
                ]
            )
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_database_allows_only_one_draft_per_lineage(self) -> None:
        with SessionLocal() as db:
            db.add_all(
                [
                    TenantVoiceContextSchema(
                        tenant_id=self.tenant.id,
                        agent_config_id=self.agent_id,
                        schema_key="single_draft",
                        version=1,
                        status="draft",
                        name="Version 1",
                    ),
                    TenantVoiceContextSchema(
                        tenant_id=self.tenant.id,
                        agent_config_id=self.agent_id,
                        schema_key="single_draft",
                        version=2,
                        status="draft",
                        name="Version 2",
                    ),
                ]
            )
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_fork_rejects_when_lineage_already_has_a_draft(self) -> None:
        self._enable_feature()
        active_id = self._create_ready_schema(schema_key="versioned")
        self.assertEqual(
            self.client.post(
                f"/api/v1/voice/context-schemas/{active_id}/activate"
            ).status_code,
            200,
        )
        first_fork = self.client.post(
            f"/api/v1/voice/context-schemas/{active_id}/new-version"
        )
        second_fork = self.client.post(
            f"/api/v1/voice/context-schemas/{active_id}/new-version"
        )
        self.assertEqual(first_fork.status_code, 201, first_fork.text)
        self.assertEqual(second_fork.status_code, 409)
        self.assertEqual(
            second_fork.json()["detail"],
            "A draft schema already exists for this lineage.",
        )

    def test_concurrent_activation_conflict_is_mapped_and_rolled_back(self) -> None:
        self._enable_feature()
        schema_id = self._create_ready_schema(schema_key="concurrent")
        with patch.object(
            IntegrationEventService,
            "record_event",
            side_effect=self._integrity_error(ACTIVE_LINEAGE_INDEX),
        ):
            response = self.client.post(
                f"/api/v1/voice/context-schemas/{schema_id}/activate"
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"],
            "An active schema already exists for this lineage.",
        )
        with SessionLocal() as db:
            self.assertEqual(db.get(TenantVoiceContextSchema, schema_id).status, "draft")

    def test_unknown_field_integrity_error_is_rolled_back_and_reraised(self) -> None:
        error = self._integrity_error("unknown_constraint")
        with SessionLocal() as db:
            service = VoiceContextService(db)
            field = TenantVoiceContextField(
                tenant_id=self.tenant.id,
                schema_id="schema-id",
                key="field_key",
                label="Field",
                field_type="text",
                collection_mode="ask_if_missing",
                position=0,
            )
            with (
                patch.object(db, "commit", side_effect=error),
                patch.object(db, "rollback") as rollback,
            ):
                with self.assertRaises(IntegrityError) as raised:
                    service._commit_field(field)
                self.assertIs(raised.exception, error)
                rollback.assert_called_once_with()

    def test_active_and_archived_schemas_are_immutable(self) -> None:
        self._enable_feature()
        schema_id = self._create_ready_schema()
        self.assertEqual(
            self.client.post(f"/api/v1/voice/context-schemas/{schema_id}/activate").status_code,
            200,
        )
        update = self.client.put(
            f"/api/v1/voice/context-schemas/{schema_id}",
            json={"name": "Changed", "description": None},
        )
        field_update = self.client.put(
            f"/api/v1/voice/context-schemas/{schema_id}/fields/missing",
            json=self._field_payload(),
        )
        self.assertEqual(update.status_code, 409)
        self.assertEqual(field_update.status_code, 409)
        self.assertEqual(
            self.client.post(f"/api/v1/voice/context-schemas/{schema_id}/archive").status_code,
            200,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/v1/voice/context-schemas/{schema_id}/fields/missing"
            ).status_code,
            409,
        )

    def test_delete_draft_schema_is_blocked(self) -> None:
        self._enable_feature()
        schema_id = self._create_ready_schema()
        self.assertEqual(
            self.client.delete(f"/api/v1/voice/context-schemas/{schema_id}").status_code,
            409,
        )

    def test_delete_active_schema_is_blocked(self) -> None:
        self._enable_feature()
        schema_id = self._create_ready_schema()
        self.assertEqual(
            self.client.post(f"/api/v1/voice/context-schemas/{schema_id}/activate").status_code,
            200,
        )
        self.assertEqual(
            self.client.delete(f"/api/v1/voice/context-schemas/{schema_id}").status_code,
            409,
        )

    def test_delete_archived_schema_removes_it_and_its_fields(self) -> None:
        self._enable_feature()
        schema_id = self._create_ready_schema()
        self.assertEqual(
            self.client.post(f"/api/v1/voice/context-schemas/{schema_id}/archive").status_code,
            200,
        )
        response = self.client.delete(f"/api/v1/voice/context-schemas/{schema_id}")
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(
            self.client.get(f"/api/v1/voice/context-schemas/{schema_id}").status_code,
            404,
        )
        with SessionLocal() as db:
            self.assertIsNone(db.get(TenantVoiceContextSchema, schema_id))
            remaining_fields = db.scalars(
                select(TenantVoiceContextField).where(
                    TenantVoiceContextField.schema_id == schema_id
                )
            ).all()
            self.assertEqual(list(remaining_fields), [])

    def test_delete_archived_schema_used_by_draft_experience_is_blocked(self) -> None:
        self._enable_feature()
        schema_id = self._create_ready_schema()
        create = self.client.post(
            "/api/v1/voice/experiences",
            json=self._experience_payload(schema_id, self.agent_id),
        )
        self.assertEqual(create.status_code, 201, create.text)
        experience_id = create.json()["id"]
        self.assertEqual(
            self.client.post(f"/api/v1/voice/context-schemas/{schema_id}/archive").status_code,
            200,
        )

        response = self.client.delete(f"/api/v1/voice/context-schemas/{schema_id}")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(
            response.json()["detail"],
            "Voice context schema is referenced by a voice experience and cannot be deleted.",
        )
        with SessionLocal() as db:
            self.assertIsNotNone(db.get(TenantVoiceContextSchema, schema_id))
            self.assertIsNotNone(db.get(TenantVoiceExperience, experience_id))

    def test_delete_archived_schema_used_by_unpublished_experience_is_blocked(self) -> None:
        self._enable_feature()
        schema_id = self._create_ready_schema()
        self.assertEqual(
            self.client.post(f"/api/v1/voice/context-schemas/{schema_id}/activate").status_code,
            200,
        )
        create = self.client.post(
            "/api/v1/voice/experiences",
            json=self._experience_payload(schema_id, self.agent_id),
        )
        self.assertEqual(create.status_code, 201, create.text)
        experience_id = create.json()["id"]
        publish = self.client.post(f"/api/v1/voice/experiences/{experience_id}/publish")
        self.assertEqual(publish.status_code, 200, publish.text)
        unpublish = self.client.post(f"/api/v1/voice/experiences/{experience_id}/unpublish")
        self.assertEqual(unpublish.status_code, 200, unpublish.text)

        self.assertEqual(
            self.client.post(f"/api/v1/voice/context-schemas/{schema_id}/archive").status_code,
            200,
        )
        response = self.client.delete(f"/api/v1/voice/context-schemas/{schema_id}")
        self.assertEqual(response.status_code, 409, response.text)

        with SessionLocal() as db:
            self.assertIsNotNone(db.get(TenantVoiceContextSchema, schema_id))
            self.assertIsNotNone(db.get(TenantVoiceExperience, experience_id))
            remaining_versions = db.scalars(
                select(TenantVoiceExperienceVersion).where(
                    TenantVoiceExperienceVersion.experience_id == experience_id
                )
            ).all()
            self.assertEqual(len(list(remaining_versions)), 1)

    def test_delete_archived_schema_preserves_all_publication_history(self) -> None:
        self._enable_feature()
        schema_id = self._create_ready_schema()
        self.client.post(f"/api/v1/voice/context-schemas/{schema_id}/activate")
        create = self.client.post(
            "/api/v1/voice/experiences",
            json=self._experience_payload(schema_id, self.agent_id),
        )
        self.assertEqual(create.status_code, 201, create.text)
        experience_id = create.json()["id"]
        for _ in range(2):
            self.assertEqual(
                self.client.post(
                    f"/api/v1/voice/experiences/{experience_id}/publish"
                ).status_code,
                200,
            )
            self.assertEqual(
                self.client.post(
                    f"/api/v1/voice/experiences/{experience_id}/unpublish"
                ).status_code,
                200,
            )
        self.client.post(f"/api/v1/voice/context-schemas/{schema_id}/archive")

        response = self.client.delete(f"/api/v1/voice/context-schemas/{schema_id}")
        self.assertEqual(response.status_code, 409, response.text)
        with SessionLocal() as db:
            self.assertIsNotNone(db.get(TenantVoiceContextSchema, schema_id))
            self.assertIsNotNone(db.get(TenantVoiceExperience, experience_id))
            versions = db.scalars(
                select(TenantVoiceExperienceVersion).where(
                    TenantVoiceExperienceVersion.experience_id == experience_id
                )
            ).all()
            self.assertEqual(len(list(versions)), 2)

    def test_delete_schema_used_only_by_historical_version_is_blocked(self) -> None:
        self._enable_feature()
        schema_a = self._create_ready_schema(schema_key="historical_a")
        self.client.post(f"/api/v1/voice/context-schemas/{schema_a}/activate")
        create = self.client.post(
            "/api/v1/voice/experiences",
            json=self._experience_payload(schema_a, self.agent_id),
        )
        self.assertEqual(create.status_code, 201, create.text)
        experience_id = create.json()["id"]
        self.client.post(f"/api/v1/voice/experiences/{experience_id}/publish")
        self.client.post(f"/api/v1/voice/experiences/{experience_id}/unpublish")

        schema_b = self._create_ready_schema(schema_key="current_b")
        self.client.post(f"/api/v1/voice/context-schemas/{schema_b}/activate")
        update = self.client.put(
            f"/api/v1/voice/experiences/{experience_id}",
            json=self._experience_payload(schema_b, self.agent_id),
        )
        self.assertEqual(update.status_code, 200, update.text)
        self.client.post(f"/api/v1/voice/context-schemas/{schema_a}/archive")

        response = self.client.delete(f"/api/v1/voice/context-schemas/{schema_a}")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(
            response.json()["detail"],
            "Voice context schema is referenced by publication history and cannot be deleted.",
        )
        with SessionLocal() as db:
            self.assertIsNotNone(db.get(TenantVoiceContextSchema, schema_a))
            experience = db.get(TenantVoiceExperience, experience_id)
            self.assertEqual(experience.context_schema_id, schema_b)
            versions = db.scalars(
                select(TenantVoiceExperienceVersion).where(
                    TenantVoiceExperienceVersion.experience_id == experience_id
                )
            ).all()
            self.assertEqual([version.context_schema_id for version in versions], [schema_a])

    def test_delete_unknown_integrity_error_is_rolled_back_and_reraised(self) -> None:
        error = self._integrity_error("unknown_constraint")
        schema = TenantVoiceContextSchema(
            tenant_id=self.tenant.id,
            agent_config_id=self.agent_id,
            schema_key="unknown_integrity",
            version=1,
            status="archived",
            name="Unknown integrity",
        )
        with SessionLocal() as db:
            service = VoiceContextService(db)
            with (
                patch.object(service, "_locked_schema", return_value=schema),
                patch.object(
                    service,
                    "_require_agent",
                    return_value=SimpleNamespace(provider="ultravox"),
                ),
                patch.object(db, "scalar", return_value=None),
                patch.object(db, "delete"),
                patch.object(db, "commit", side_effect=error),
                patch.object(db, "rollback") as rollback,
            ):
                with self.assertRaises(IntegrityError) as raised:
                    service.delete_schema(self.tenant.id, "schema-id", self.user.id)
                self.assertIs(raised.exception, error)
                rollback.assert_called_once_with()

    def test_delete_unknown_schema_is_not_found(self) -> None:
        self._enable_feature()
        self.assertEqual(
            self.client.delete("/api/v1/voice/context-schemas/unknown-id").status_code,
            404,
        )

    def test_delete_respects_tenant_isolation(self) -> None:
        tenant_b, _ = self._seed_tenant_user(slug="tenant-b", email="delete-b@example.com")
        agent_b = self._seed_agent(tenant_b.id, "agent-tenant-b-delete")
        self._enable_feature(tenant_b.id)
        with SessionLocal() as db:
            schema = TenantVoiceContextSchema(
                tenant_id=tenant_b.id,
                agent_config_id=agent_b,
                schema_key="tenant_b_delete",
                version=1,
                status="archived",
                name="Tenant B schema",
            )
            db.add(schema)
            db.commit()
            db.refresh(schema)
            other_id = schema.id

        self._enable_feature()
        self.assertEqual(
            self.client.delete(f"/api/v1/voice/context-schemas/{other_id}").status_code,
            404,
        )
        with SessionLocal() as db:
            self.assertIsNotNone(db.get(TenantVoiceContextSchema, other_id))

    def test_delete_write_roles_enforced(self) -> None:
        self._enable_feature()
        schema_id = self._create_ready_schema()
        self.assertEqual(
            self.client.post(f"/api/v1/voice/context-schemas/{schema_id}/archive").status_code,
            200,
        )
        for role in ("tenant_analyst", "tenant_viewer"):
            self._set_actor(role)
            self.assertEqual(
                self.client.delete(f"/api/v1/voice/context-schemas/{schema_id}").status_code,
                403,
            )
        self._set_actor("tenant_admin")
        self.assertEqual(
            self.client.delete(f"/api/v1/voice/context-schemas/{schema_id}").status_code,
            204,
        )

    def test_tenant_id_is_forbidden_in_request_body(self) -> None:
        self._enable_feature()
        response = self.client.post(
            f"/api/v1/voice/agents/{self.agent_id}/context-schemas",
            json={
                "schema_key": "lead_intake",
                "name": "Lead intake",
                "tenant_id": "attacker-tenant",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_tenant_isolation_hides_schema_on_all_mutations(self) -> None:
        tenant_b, _ = self._seed_tenant_user(slug="tenant-b", email="other@example.com")
        agent_b = self._seed_agent(tenant_b.id, "agent-b")
        self._enable_feature(tenant_b.id)
        with SessionLocal() as db:
            schema = TenantVoiceContextSchema(
                tenant_id=tenant_b.id,
                agent_config_id=agent_b,
                schema_key="private_schema",
                version=1,
                status="draft",
                name="Private",
            )
            db.add(schema)
            db.commit()
            db.refresh(schema)
            schema_id = schema.id

        self._enable_feature()
        self.assertEqual(
            self.client.get(f"/api/v1/voice/context-schemas/{schema_id}").status_code, 404
        )
        self.assertEqual(
            self.client.put(
                f"/api/v1/voice/context-schemas/{schema_id}",
                json={"name": "Attack", "description": None},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(f"/api/v1/voice/context-schemas/{schema_id}/activate").status_code,
            404,
        )

    def test_read_and_write_roles(self) -> None:
        self._enable_feature()
        schema_id = self._create_schema().json()["id"]
        for role in ("tenant_analyst", "tenant_viewer"):
            self._set_actor(role)
            self.assertEqual(
                self.client.get(f"/api/v1/voice/context-schemas/{schema_id}").status_code,
                200,
            )
            self.assertEqual(
                self.client.put(
                    f"/api/v1/voice/context-schemas/{schema_id}",
                    json={"name": "Denied", "description": None},
                ).status_code,
                403,
            )

        self._set_actor("tenant_admin")
        self.assertEqual(
            self.client.put(
                f"/api/v1/voice/context-schemas/{schema_id}",
                json={"name": "Allowed", "description": None},
            ).status_code,
            200,
        )

        self._set_actor("platform_admin", is_internal=False)
        self.assertEqual(
            self.client.get(f"/api/v1/voice/context-schemas/{schema_id}").status_code,
            403,
        )
        self._set_actor("platform_admin", is_internal=True)
        self.assertEqual(
            self.client.get(f"/api/v1/voice/context-schemas/{schema_id}").status_code,
            200,
        )

    def test_internal_platform_admin_can_operate_in_another_tenant_context(self) -> None:
        tenant_b, _ = self._seed_tenant_user(slug="tenant-b", email="other@example.com")
        agent_b = self._seed_agent(tenant_b.id, "agent-b")
        self._enable_feature(tenant_b.id)
        with SessionLocal() as db:
            db.add(
                TenantMembership(
                    tenant_id=tenant_b.id,
                    user_id=self.user.id,
                    role="platform_admin",
                    status="active",
                )
            )
            db.commit()
        self.tenant = tenant_b
        response = self._create_schema(agent_id=agent_b, schema_key="tenant_b_schema")
        self.assertEqual(response.status_code, 201, response.text)

    @staticmethod
    def _integrity_error(constraint_name: str) -> IntegrityError:
        original = Exception("duplicate")
        original.diag = SimpleNamespace(constraint_name=constraint_name)
        return IntegrityError("statement", {}, original)

    def test_alembic_has_single_expected_head(self) -> None:
        heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
        self.assertEqual(heads, ["202608310001"])


if __name__ == "__main__":
    import unittest

    unittest.main()
