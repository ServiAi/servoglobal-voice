from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase
from app.db.session import SessionLocal
from app.models.integrations import TenantIntegrationEvent, TenantVoiceAgentConfig
from app.schemas.agents import AgentCreateRequest
from app.services.agent_service import AgentService
from app.services.tenant_feature_service import AGENT_BUILDER, TenantFeatureService
from app.schemas.ultravox_admin import UltravoxToolSummary


class AgentBuilderTests(Integration2ATestCase):
    def setUp(self) -> None:
        super().setUp()
        self.voice_agent_config_id = self._seed_voice_agent_config(self.tenant.id, "va-1")

    @staticmethod
    def _seed_voice_agent_config(tenant_id: str, provider_agent_id: str) -> str:
        with SessionLocal() as db:
            config = TenantVoiceAgentConfig(
                tenant_id=tenant_id,
                provider="ultravox",
                provider_agent_id=provider_agent_id,
                display_name="Legacy agent",
                default_voice="nova",
                default_system_prompt="legacy prompt",
            )
            db.add(config)
            db.commit()
            db.refresh(config)
            return config.id

    def _enable_feature(self, tenant_id: str | None = None) -> None:
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(
                tenant_id or self.tenant.id, AGENT_BUILDER, True, {}, self.user.id
            )

    def _payload(self, **overrides) -> dict:
        payload = {
            "name": "Sandra",
            "description": "Asesora comercial",
            "language": "es",
            "timezone": "America/Bogota",
            "instructions": {
                "role": "Asesora comercial",
                "objective": "Agendar una cita",
                "system_prompt": "Eres Sandra, asesora comercial de ServiGlobal.",
                "greeting": "Hola, soy Sandra",
                "closing": "Gracias por tu tiempo",
            },
            "behavior": {
                "response_style": "balanced",
                "interruptions": "balanced",
                "turn_detection": "automatic",
                "confirmation_strategy": "important_data",
                "agent_first": True,
            },
        }
        payload.update(overrides)
        return payload

    def _create(self, **overrides):
        return self.client.post("/api/v1/agents", json=self._payload(**overrides))

    def _draft_payload(self, name: str = "Sandra", description: str | None = "Asesora comercial", **overrides) -> dict:
        payload = {
            "name": name,
            "description": description,
            "language": "es",
            "timezone": "America/Bogota",
            "instructions": {
                "role": "Asesora comercial",
                "objective": "Vender",
                "system_prompt": "Prompt actualizado",
                "greeting": "Hola",
                "closing": "Gracias",
            },
            "behavior": self._payload()["behavior"],
        }
        payload.update(overrides)
        return payload

    # -- feature gate --

    def test_feature_disabled_returns_403(self) -> None:
        self.assertEqual(self.client.get("/api/v1/agents").status_code, 403)
        self.assertEqual(self._create().status_code, 403)

    # -- create / draft --

    def test_create_agent_creates_draft_v1(self) -> None:
        self._enable_feature()
        response = self._create()
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["status"], "draft")
        self.assertIsNotNone(body["draft_version_id"])
        self.assertIsNone(body["published_version_id"])

        draft = self.client.get(f"/api/v1/agents/{body['id']}/draft").json()
        self.assertEqual(draft["version"], 1)
        self.assertEqual(draft["status"], "draft")
        self.assertEqual(
            draft["instructions"]["system_prompt"],
            self._payload()["instructions"]["system_prompt"],
        )

    def test_create_agent_records_sanitized_event(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        with SessionLocal() as db:
            event = db.scalar(
                select(TenantIntegrationEvent).where(
                    TenantIntegrationEvent.tenant_id == self.tenant.id,
                    TenantIntegrationEvent.event_type == "agent_created",
                    TenantIntegrationEvent.resource_id == agent_id,
                )
            )
            self.assertIsNotNone(event)
            self.assertNotIn("system_prompt", str(event.metadata_json))
            self.assertNotIn("Sandra, asesora", str(event.metadata_json))

    def test_voice_agent_config_must_belong_to_tenant(self) -> None:
        tenant_b, _ = self._seed_tenant_user(slug="tenant-b", email="config-b@example.com")
        config_b = self._seed_voice_agent_config(tenant_b.id, "va-b")
        self._enable_feature()
        response = self._create(voice_agent_config_id=config_b)
        self.assertEqual(response.status_code, 422, response.text)

    # -- runtime binding / registry validation --

    def test_create_rejects_unsupported_pipeline_type(self) -> None:
        self._enable_feature()
        response = self._create(pipeline_type="cascade")
        self.assertEqual(response.status_code, 422, response.text)

    def test_create_rejects_unavailable_provider(self) -> None:
        self._enable_feature()
        response = self._create(provider="openai", model="gpt-realtime")
        self.assertEqual(response.status_code, 422, response.text)

    def test_create_default_runtime_binding_is_ultravox(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        draft = self.client.get(f"/api/v1/agents/{agent_id}/draft").json()
        self.assertEqual(
            draft["runtime_binding"],
            {
                "pipeline_type": "realtime",
                "realtime": {
                    "provider": "ultravox",
                    "model": "ultravox",
                    "management_mode": "serviglobal_managed",
                },
            },
        )

    def test_update_draft_rejects_unavailable_model(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        payload = self._payload()
        update_payload = {
            "name": payload["name"],
            "description": payload["description"],
            "language": payload["language"],
            "timezone": payload["timezone"],
            "instructions": payload["instructions"],
            "behavior": payload["behavior"],
            "provider": "ultravox",
            "model": "does-not-exist",
        }
        response = self.client.patch(f"/api/v1/agents/{agent_id}/draft", json=update_payload)
        self.assertEqual(response.status_code, 422, response.text)

    # -- publish / versioning --

    def test_publish_requires_system_prompt(self) -> None:
        self._enable_feature()
        payload = self._payload()
        payload["instructions"]["system_prompt"] = ""
        agent_id = self._create(**payload).json()["id"]
        response = self.client.post(f"/api/v1/agents/{agent_id}/publish")
        self.assertEqual(response.status_code, 422, response.text)

    def test_update_draft_then_publish(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        update_payload = {
            "name": "Sandra renombrada",
            "description": "Descripcion actualizada",
            "language": "es",
            "timezone": "America/Bogota",
            "instructions": {
                "role": "Asesora comercial",
                "objective": "Vender",
                "system_prompt": "Prompt actualizado",
                "greeting": "Hola",
                "closing": "Gracias",
            },
            "behavior": self._payload()["behavior"],
            "voice_agent_config_id": self.voice_agent_config_id,
        }
        patch_response = self.client.patch(
            f"/api/v1/agents/{agent_id}/draft", json=update_payload
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.text)
        self.assertEqual(
            patch_response.json()["instructions"]["system_prompt"], "Prompt actualizado"
        )
        self.assertEqual(
            patch_response.json()["runtime_binding"]["realtime"]["provider"], "ultravox"
        )
        self.assertEqual(patch_response.json()["identity"]["name"], "Sandra renombrada")

        agent_after_draft_save = self.client.get(f"/api/v1/agents/{agent_id}").json()
        self.assertEqual(agent_after_draft_save["name"], "Sandra renombrada")

        publish_response = self.client.post(f"/api/v1/agents/{agent_id}/publish")
        self.assertEqual(publish_response.status_code, 200, publish_response.text)
        body = publish_response.json()
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["name"], "Sandra renombrada")
        self.assertIsNone(body["draft_version_id"])
        self.assertIsNotNone(body["published_version_id"])

        versions = self.client.get(f"/api/v1/agents/{agent_id}/versions").json()
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["status"], "published")

    def test_publish_matching_expected_draft_version_id_succeeds(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        draft = self.client.get(f"/api/v1/agents/{agent_id}/draft").json()
        response = self.client.post(
            f"/api/v1/agents/{agent_id}/publish",
            json={"expected_draft_version_id": draft["id"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["published_version_id"], draft["id"])

    def test_publish_rejects_stale_expected_draft_version_id(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        response = self.client.post(
            f"/api/v1/agents/{agent_id}/publish",
            json={"expected_draft_version_id": "not-the-current-draft"},
        )
        self.assertEqual(response.status_code, 409, response.text)

        # Nothing was published: the agent is still in draft with the
        # original draft version untouched.
        agent = self.client.get(f"/api/v1/agents/{agent_id}").json()
        self.assertEqual(agent["status"], "draft")
        self.assertIsNone(agent["published_version_id"])
        self.assertIsNotNone(agent["draft_version_id"])

    def test_publish_saves_and_publishes_exactly_the_edited_content(self) -> None:
        # Reproduces the "Save Draft" -> "Publish" flow the frontend now
        # always performs: PATCH the draft with the on-screen content, then
        # publish the exact version id that PATCH returned.
        self._enable_feature()
        agent_id = self._create().json()["id"]
        draft_response = self.client.patch(
            f"/api/v1/agents/{agent_id}/draft",
            json=self._draft_payload(
                name="Editado en pantalla", description="Texto visible"
            ),
        )
        self.assertEqual(draft_response.status_code, 200, draft_response.text)
        saved_draft_id = draft_response.json()["id"]

        publish_response = self.client.post(
            f"/api/v1/agents/{agent_id}/publish",
            json={"expected_draft_version_id": saved_draft_id},
        )
        self.assertEqual(publish_response.status_code, 200, publish_response.text)
        self.assertEqual(publish_response.json()["published_version_id"], saved_draft_id)
        self.assertEqual(publish_response.json()["name"], "Editado en pantalla")

        versions = self.client.get(f"/api/v1/agents/{agent_id}/versions").json()
        published = next(v for v in versions if v["id"] == saved_draft_id)
        self.assertEqual(published["instructions"]["system_prompt"], "Prompt actualizado")

    def test_update_draft_rollback_leaves_agent_and_version_consistent(self) -> None:
        # An invalid voice_agent_config_id fails validation mid-update; the
        # whole transaction (agent identity + version snapshot) must roll
        # back together rather than leaving name/description half-applied.
        self._enable_feature()
        agent_id = self._create(name="Nombre original").json()["id"]
        tenant_b, _ = self._seed_tenant_user(slug="tenant-rollback", email="rollback@example.com")
        config_b = self._seed_voice_agent_config(tenant_b.id, "va-rollback")

        response = self.client.patch(
            f"/api/v1/agents/{agent_id}/draft",
            json=self._draft_payload(name="Nombre que no debe quedar", voice_agent_config_id=config_b),
        )
        self.assertEqual(response.status_code, 422, response.text)

        agent = self.client.get(f"/api/v1/agents/{agent_id}").json()
        self.assertEqual(agent["name"], "Nombre original")
        draft = self.client.get(f"/api/v1/agents/{agent_id}/draft").json()
        self.assertEqual(draft["identity"]["name"], "Nombre original")

    def test_edit_after_publish_creates_v2_and_supersedes_v1(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        self.client.post(f"/api/v1/agents/{agent_id}/publish")

        # No editable draft right after publish.
        self.assertEqual(self.client.get(f"/api/v1/agents/{agent_id}/draft").status_code, 409)

        next_draft = self.client.post(f"/api/v1/agents/{agent_id}/draft")
        self.assertEqual(next_draft.status_code, 201, next_draft.text)
        self.assertEqual(next_draft.json()["version"], 2)
        self.assertEqual(next_draft.json()["identity"]["name"], "Sandra")
        self.assertEqual(
            next_draft.json()["instructions"]["system_prompt"],
            self._payload()["instructions"]["system_prompt"],
        )

        # Cannot branch a second draft while one is already open.
        self.assertEqual(self.client.post(f"/api/v1/agents/{agent_id}/draft").status_code, 409)

        self.client.post(f"/api/v1/agents/{agent_id}/publish")
        versions = self.client.get(f"/api/v1/agents/{agent_id}/versions").json()
        by_version = {v["version"]: v["status"] for v in versions}
        self.assertEqual(by_version, {1: "superseded", 2: "published"})

    def test_unpublish_opens_a_fully_editable_draft(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        self.client.post(f"/api/v1/agents/{agent_id}/publish")

        response = self.client.post(f"/api/v1/agents/{agent_id}/unpublish")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "draft")
        self.assertIsNone(response.json()["published_version_id"])
        self.assertIsNotNone(response.json()["draft_version_id"])

        payload = self._draft_payload(
            name="Agente editable",
            description="Todo editable",
            language="en",
            timezone="America/New_York",
            voice_agent_config_id=self.voice_agent_config_id,
        )
        updated = self.client.patch(f"/api/v1/agents/{agent_id}/draft", json=payload)
        self.assertEqual(updated.status_code, 200, updated.text)
        body = updated.json()
        self.assertEqual(body["identity"]["name"], "Agente editable")
        self.assertEqual(body["language"], "en")
        self.assertEqual(body["timezone"], "America/New_York")
        self.assertEqual(body["instructions"], payload["instructions"])
        self.assertEqual(body["behavior"], payload["behavior"])
        self.assertEqual(body["voice_agent_config_id"], self.voice_agent_config_id)
        self.assertEqual(
            body["runtime_binding"]["realtime"],
            {
                "provider": "ultravox",
                "model": "ultravox",
                "management_mode": "serviglobal_managed",
            },
        )

    def test_provider_managed_link_is_stored_only_in_version_binding(self) -> None:
        self._enable_feature()
        remote = SimpleNamespace(
            agent_id="remote-agent-1",
            published_revision_id="revision-live",
            tools=[UltravoxToolSummary(name="hangUp", classification="provider_native")],
            has_unsupported_client_tools=False,
        )
        with patch(
            "app.services.ultravox_admin_service.UltravoxAdminService.validate_provider_agent_link",
            return_value=remote,
        ):
            response = self._create(
                model="ultravox-v0.7",
                management_mode="provider_managed",
                provider_agent={
                    "agent_id": "remote-agent-1",
                    "observed_published_revision_id": "revision-stale",
                },
            )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        draft = self.client.get(f"/api/v1/agents/{body['id']}/draft").json()
        self.assertEqual(
            draft["runtime_binding"]["realtime"]["provider_agent"],
            {
                "agent_id": "remote-agent-1",
                "observed_published_revision_id": "revision-live",
            },
        )
        self.assertNotIn("provider_agent_id", body)

    def test_unpublish_reuses_an_existing_editable_draft(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        self.client.post(f"/api/v1/agents/{agent_id}/publish")
        draft_id = self.client.post(f"/api/v1/agents/{agent_id}/draft").json()["id"]

        response = self.client.post(f"/api/v1/agents/{agent_id}/unpublish")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["draft_version_id"], draft_id)
        versions = self.client.get(f"/api/v1/agents/{agent_id}/versions").json()
        self.assertEqual(len([version for version in versions if version["status"] == "draft"]), 1)

    def test_archived_agent_is_immutable(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        self.client.post(f"/api/v1/agents/{agent_id}/publish")
        archive_response = self.client.post(f"/api/v1/agents/{agent_id}/archive")
        self.assertEqual(archive_response.status_code, 200, archive_response.text)
        self.assertEqual(archive_response.json()["status"], "archived")

        self.assertEqual(self.client.post(f"/api/v1/agents/{agent_id}/draft").status_code, 409)
        self.assertEqual(
            self.client.patch(
                f"/api/v1/agents/{agent_id}",
                json={"name": "Renombrado", "description": None},
            ).status_code,
            409,
        )

    def test_only_an_archived_agent_can_be_deleted(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        self.assertEqual(self.client.post(f"/api/v1/agents/{agent_id}/delete").status_code, 409)

        self.client.post(f"/api/v1/agents/{agent_id}/publish")
        self.client.post(f"/api/v1/agents/{agent_id}/archive")
        response = self.client.post(f"/api/v1/agents/{agent_id}/delete")
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(self.client.get(f"/api/v1/agents/{agent_id}").status_code, 404)

    def test_delete_method_remains_supported(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        self.client.post(f"/api/v1/agents/{agent_id}/archive")

        response = self.client.delete(f"/api/v1/agents/{agent_id}")
        self.assertEqual(response.status_code, 204, response.text)

    def test_agent_with_voice_sessions_keeps_its_audit_history(self) -> None:
        from app.models.voice_sessions import VoiceSession

        self._enable_feature()
        agent_id = self._create().json()["id"]
        published_version_id = self.client.post(
            f"/api/v1/agents/{agent_id}/publish"
        ).json()["published_version_id"]
        with SessionLocal() as db:
            db.add(
                VoiceSession(
                    tenant_id=self.tenant.id,
                    agent_id=agent_id,
                    agent_version_id=published_version_id,
                    channel="internal_test",
                    direction="internal",
                    provider="ultravox",
                )
            )
            db.commit()

        self.client.post(f"/api/v1/agents/{agent_id}/archive")
        response = self.client.delete(f"/api/v1/agents/{agent_id}")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.client.get(f"/api/v1/agents/{agent_id}").status_code, 200)

    # -- legacy compatibility --

    def test_agent_builder_does_not_mutate_legacy_voice_agent_config(self) -> None:
        self._enable_feature()
        agent_id = self._create(voice_agent_config_id=self.voice_agent_config_id).json()["id"]
        self.client.post(f"/api/v1/agents/{agent_id}/publish")
        with SessionLocal() as db:
            config = db.get(TenantVoiceAgentConfig, self.voice_agent_config_id)
            self.assertEqual(config.display_name, "Legacy agent")
            self.assertEqual(config.default_system_prompt, "legacy prompt")
            self.assertEqual(config.default_voice, "nova")

    # -- multi-tenant isolation --

    def test_multi_tenant_isolation(self) -> None:
        tenant_b, user_b = self._seed_tenant_user(slug="tenant-b", email="agent-b@example.com")
        self._enable_feature(tenant_b.id)
        with SessionLocal() as db:
            other = AgentService(db).create_agent(
                tenant_b.id,
                AgentCreateRequest.model_validate(self._payload()),
                user_b.id,
            )
            other_id = other.id

        self._enable_feature()
        self.assertEqual(self.client.get(f"/api/v1/agents/{other_id}").status_code, 404)
        self.assertEqual(
            self.client.patch(
                f"/api/v1/agents/{other_id}",
                json={"name": "Hacked", "description": None},
            ).status_code,
            404,
        )
        self.assertEqual(self.client.get(f"/api/v1/agents/{other_id}/draft").status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/agents/{other_id}/publish").status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/agents/{other_id}/unpublish").status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/agents/{other_id}/archive").status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/agents/{other_id}/delete").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/v1/agents/{other_id}").status_code, 404)
        self.assertEqual(
            self.client.get(f"/api/v1/agents/{other_id}/versions").status_code, 404
        )


if __name__ == "__main__":
    unittest.main()
