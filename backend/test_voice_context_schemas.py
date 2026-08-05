from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase
from app.db.session import SessionLocal
from app.models.identity import TenantMembership, User
from app.models.integrations import TenantVoiceAgentConfig
from app.models.voice_context import TenantVoiceContextSchema
from app.services.tenant_feature_service import TenantFeatureService, VOICE_EXPERIENCES


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
    ) -> dict:
        return {
            "key": key,
            "label": key.replace("_", " ").title(),
            "field_type": field_type,
            "collection_mode": collection_mode,
            "required": True,
            "position": position,
            "sensitivity": "sensitive" if field_type in {"email", "phone"} else "standard",
            "validation_json": {},
            "options_json": [{"value": "one", "label": "One"}] if field_type == "select" else [],
        }

    def _add_field(self, schema_id: str, **overrides):
        return self.client.post(
            f"/api/v1/voice/context-schemas/{schema_id}/fields",
            json=self._field_payload(**overrides),
        )

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

    def test_max_context_fields_is_enforced(self) -> None:
        self._enable_feature(max_context_fields=1)
        schema_id = self._create_schema().json()["id"]
        self.assertEqual(self._add_field(schema_id).status_code, 201)
        response = self._add_field(schema_id, key="second_field", position=1)
        self.assertEqual(response.status_code, 422)

    def test_max_experiences_counts_non_archived_lineages_per_tenant(self) -> None:
        self._enable_feature(max_experiences=1)
        first = self._create_schema(schema_key="first")
        second = self._create_schema(schema_key="second")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 422)
        archived = self.client.post(
            f"/api/v1/voice/context-schemas/{first.json()['id']}/archive"
        )
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(self._create_schema(schema_key="second").status_code, 201)

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

    def test_alembic_has_single_expected_head(self) -> None:
        heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
        self.assertEqual(heads, ["202608050001"])


if __name__ == "__main__":
    import unittest

    unittest.main()
