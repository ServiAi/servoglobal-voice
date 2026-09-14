from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase
from app.db.session import SessionLocal
from app.models.integrations import TenantIntegrationEvent, TenantVoiceAgentConfig, TenantWhatsAppConfig
from app.schemas.agents import AgentCreateRequest
from app.services.agent_service import AgentService
from app.services.secret_manager_service import SecretManager
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

    # -- model settings (temperature etc.) --

    def test_create_accepts_supported_model_setting(self) -> None:
        self._enable_feature()
        response = self._create(settings={"temperature": 0.4})
        self.assertEqual(response.status_code, 201, response.text)
        draft = self.client.get(f"/api/v1/agents/{response.json()['id']}/draft").json()
        self.assertEqual(draft["runtime_binding"]["realtime"]["settings"], {"temperature": 0.4})

    def test_create_without_settings_stays_backward_compatible(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        draft = self.client.get(f"/api/v1/agents/{agent_id}/draft").json()
        self.assertNotIn("settings", draft["runtime_binding"]["realtime"])

    def test_create_rejects_unsupported_setting_key(self) -> None:
        self._enable_feature()
        response = self._create(settings={"top_p": 0.9})
        self.assertEqual(response.status_code, 422, response.text)

    def test_create_rejects_out_of_range_temperature(self) -> None:
        self._enable_feature()
        response = self._create(settings={"temperature": 1.5})
        self.assertEqual(response.status_code, 422, response.text)

    def test_create_rejects_secret_like_setting_key(self) -> None:
        self._enable_feature()
        response = self._create(settings={"api_key": "sk-test"})
        self.assertEqual(response.status_code, 422, response.text)

    def test_provider_managed_rejects_settings(self) -> None:
        # settings is rejected before any remote Ultravox call is made -- no
        # need to mock validate_provider_agent_link here.
        self._enable_feature()
        response = self._create(
            management_mode="provider_managed",
            model="ultravox-v0.7",
            provider_agent={"agent_id": "remote-1", "observed_published_revision_id": None},
            settings={"temperature": 0.5},
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("settings", response.text)

    def test_update_draft_persists_settings_and_clones_on_next_draft(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        draft_payload = self._draft_payload(settings={"temperature": 0.2})
        response = self.client.patch(f"/api/v1/agents/{agent_id}/draft", json=draft_payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["runtime_binding"]["realtime"]["settings"], {"temperature": 0.2})

        publish = self.client.post(f"/api/v1/agents/{agent_id}/publish", json={})
        self.assertEqual(publish.status_code, 200, publish.text)
        next_draft = self.client.post(f"/api/v1/agents/{agent_id}/draft")
        self.assertEqual(next_draft.status_code, 201, next_draft.text)
        self.assertEqual(next_draft.json()["runtime_binding"]["realtime"]["settings"], {"temperature": 0.2})

    # -- tools --

    @staticmethod
    def _configure_whatsapp(tenant_id: str) -> None:
        with SessionLocal() as db:
            db.add(TenantWhatsAppConfig(
                tenant_id=tenant_id,
                provider="whatsapp_cloud",
                status="active",
                phone_number_id="phone-1",
                display_phone_number="+573000000000",
                default_language="es",
                access_token_encrypted=SecretManager().encrypt_secret("EA_test_token_1234567890"),
            ))
            db.commit()

    def test_create_persists_enabled_tool_binding(self) -> None:
        self._enable_feature()
        response = self._create(tools=[{"key": "calendar.check_availability", "enabled": True, "config": {}}])
        self.assertEqual(response.status_code, 201, response.text)
        draft = self.client.get(f"/api/v1/agents/{response.json()['id']}/draft").json()
        self.assertEqual(
            draft["runtime_binding"]["tools"],
            [{"key": "calendar.check_availability", "enabled": True, "config": {}}],
        )

    def test_create_without_tools_stays_backward_compatible(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        draft = self.client.get(f"/api/v1/agents/{agent_id}/draft").json()
        self.assertNotIn("tools", draft["runtime_binding"])

    def test_create_rejects_unknown_tool_key(self) -> None:
        self._enable_feature()
        response = self._create(tools=[{"key": "does.not_exist", "enabled": True, "config": {}}])
        self.assertEqual(response.status_code, 422, response.text)

    def test_create_rejects_planned_tool_key(self) -> None:
        self._enable_feature()
        response = self._create(tools=[{"key": "handoff.chatwoot", "enabled": True, "config": {}}])
        self.assertEqual(response.status_code, 422, response.text)

    def test_create_rejects_duplicate_tool_key(self) -> None:
        self._enable_feature()
        response = self._create(tools=[
            {"key": "calendar.check_availability", "enabled": True, "config": {}},
            {"key": "calendar.check_availability", "enabled": False, "config": {}},
        ])
        self.assertEqual(response.status_code, 422, response.text)

    def test_provider_managed_rejects_tools(self) -> None:
        self._enable_feature()
        response = self._create(
            management_mode="provider_managed",
            model="ultravox-v0.7",
            provider_agent={"agent_id": "remote-1", "observed_published_revision_id": None},
            tools=[{"key": "calendar.check_availability", "enabled": True, "config": {}}],
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("tools", response.text)

    def test_publish_blocks_when_tool_integration_not_configured(self) -> None:
        self._enable_feature()
        agent_id = self._create(tools=[{"key": "whatsapp.send_message", "enabled": True, "config": {}}]).json()["id"]
        with patch("app.services.ultravox_admin_service.UltravoxAdminService.get_voice"):
            response = self.client.post(f"/api/v1/agents/{agent_id}/publish", json={})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("tool_integration_not_configured", response.text)

    def test_publish_succeeds_when_tool_integration_configured(self) -> None:
        self._enable_feature()
        self._configure_whatsapp(self.tenant.id)
        agent_id = self._create(tools=[{"key": "whatsapp.send_message", "enabled": True, "config": {}}]).json()["id"]
        with patch("app.services.ultravox_admin_service.UltravoxAdminService.get_voice"):
            response = self.client.post(f"/api/v1/agents/{agent_id}/publish", json={})
        self.assertEqual(response.status_code, 200, response.text)

    def test_publish_ignores_disabled_tool_with_missing_integration(self) -> None:
        self._enable_feature()
        agent_id = self._create(tools=[{"key": "whatsapp.send_message", "enabled": False, "config": {}}]).json()["id"]
        with patch("app.services.ultravox_admin_service.UltravoxAdminService.get_voice"):
            response = self.client.post(f"/api/v1/agents/{agent_id}/publish", json={})
        self.assertEqual(response.status_code, 200, response.text)

    def test_next_draft_clones_tool_bindings(self) -> None:
        self._enable_feature()
        self._configure_whatsapp(self.tenant.id)
        agent_id = self._create(tools=[{"key": "whatsapp.send_message", "enabled": True, "config": {}}]).json()["id"]
        with patch("app.services.ultravox_admin_service.UltravoxAdminService.get_voice"):
            self.client.post(f"/api/v1/agents/{agent_id}/publish", json={})
        next_draft = self.client.post(f"/api/v1/agents/{agent_id}/draft")
        self.assertEqual(next_draft.status_code, 201, next_draft.text)
        self.assertEqual(
            next_draft.json()["runtime_binding"]["tools"],
            [{"key": "whatsapp.send_message", "enabled": True, "config": {}}],
        )

    def test_tool_catalog_reflects_tenant_integration_status(self) -> None:
        self._enable_feature()
        before = self.client.get("/api/v1/agents/tools/catalog")
        self.assertEqual(before.status_code, 200, before.text)
        by_key = {item["key"]: item for item in before.json()}
        self.assertFalse(by_key["whatsapp.send_message"]["available"])
        self.assertEqual(by_key["whatsapp.send_message"]["status"], "available")
        self.assertFalse(by_key["handoff.chatwoot"]["available"])
        self.assertEqual(by_key["handoff.chatwoot"]["status"], "planned")

        self._configure_whatsapp(self.tenant.id)
        after = self.client.get("/api/v1/agents/tools/catalog").json()
        after_by_key = {item["key"]: item for item in after}
        self.assertTrue(after_by_key["whatsapp.send_message"]["available"])

    def test_tool_catalog_requires_feature_enabled(self) -> None:
        self.assertEqual(self.client.get("/api/v1/agents/tools/catalog").status_code, 403)

    def test_tool_catalog_is_tenant_isolated(self) -> None:
        tenant_b, user_b = self._seed_tenant_user(slug="tenant-tools-b", email="tools-b@example.com")
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(tenant_b.id, AGENT_BUILDER, True, {}, user_b.id)
        self._configure_whatsapp(tenant_b.id)
        self._enable_feature()
        response = self.client.get("/api/v1/agents/tools/catalog")
        by_key = {item["key"]: item for item in response.json()}
        self.assertFalse(by_key["whatsapp.send_message"]["available"])

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

    # -- voice contract (Phase A: provider / provider_external) --

    def test_create_accepts_provider_voice(self) -> None:
        self._enable_feature()
        response = self._create(voice={"mode": "provider", "provider": "ultravox", "voice_id": "Mark"})
        self.assertEqual(response.status_code, 201, response.text)
        draft = self.client.get(f"/api/v1/agents/{response.json()['id']}/draft").json()
        self.assertEqual(
            draft["runtime_binding"]["realtime"]["voice"],
            {"mode": "provider", "provider": "ultravox", "voice_id": "Mark", "settings": {}},
        )

    def test_create_accepts_provider_external_elevenlabs_voice(self) -> None:
        self._enable_feature()
        response = self._create(voice={
            "mode": "provider_external", "provider": "elevenlabs", "voice_id": "21m00Tcm4TlvDq8ikWAM",
            "settings": {"model": "eleven_turbo_v2_5", "speed": 1.0, "stability": 0.8},
        })
        self.assertEqual(response.status_code, 201, response.text)
        draft = self.client.get(f"/api/v1/agents/{response.json()['id']}/draft").json()
        self.assertEqual(draft["runtime_binding"]["realtime"]["voice"]["provider"], "elevenlabs")
        self.assertEqual(draft["runtime_binding"]["realtime"]["voice"]["settings"]["speed"], 1.0)

    def test_external_voice_without_model_cannot_be_saved_or_published(self) -> None:
        self._enable_feature()
        invalid_voice = {
            "mode": "provider_external", "provider": "elevenlabs",
            "voice_id": "ABC123", "settings": {},
        }
        agents_before = self.client.get("/api/v1/agents").json()
        response = self._create(voice=invalid_voice)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.get("/api/v1/agents").json(), agents_before)

        agent_id = self._create().json()["id"]
        draft_before = self.client.get(f"/api/v1/agents/{agent_id}/draft").json()
        response = self.client.patch(
            f"/api/v1/agents/{agent_id}/draft",
            json=self._draft_payload(voice=invalid_voice),
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(
            self.client.get(f"/api/v1/agents/{agent_id}/draft").json()["runtime_binding"],
            draft_before["runtime_binding"],
        )
        response = self.client.post(f"/api/v1/agents/{agent_id}/publish")
        self.assertEqual(response.status_code, 200, response.text)
        published = self.client.get(f"/api/v1/agents/{agent_id}/versions").json()[0]
        self.assertNotIn("voice", published["runtime_binding"]["realtime"])

    def test_create_rejects_provider_voice_from_a_different_provider(self) -> None:
        self._enable_feature()
        response = self._create(voice={"mode": "provider", "provider": "elevenlabs", "voice_id": "x"})
        self.assertEqual(response.status_code, 422, response.text)

    def test_create_rejects_unsupported_external_voice_provider(self) -> None:
        self._enable_feature()
        response = self._create(voice={"mode": "provider_external", "provider": "cartesia", "voice_id": "x"})
        self.assertEqual(response.status_code, 422, response.text)

    def test_update_draft_accepts_voice(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        response = self.client.patch(
            f"/api/v1/agents/{agent_id}/draft",
            json=self._draft_payload(voice={"mode": "provider", "provider": "ultravox", "voice_id": "Jessica"}),
        )
        self.assertEqual(response.status_code, 200, response.text)
        draft = self.client.get(f"/api/v1/agents/{agent_id}/draft").json()
        self.assertEqual(draft["runtime_binding"]["realtime"]["voice"]["voice_id"], "Jessica")

    def test_create_rejects_voice_for_provider_managed_agent(self) -> None:
        self._enable_feature()
        # No UltravoxAdminService mock needed: the voice+provider_managed
        # rejection must happen before any remote provider_agent validation.
        response = self._create(
            model="ultravox-v0.7",
            management_mode="provider_managed",
            provider_agent={"agent_id": "remote-agent-1"},
            voice={"mode": "provider", "provider": "ultravox", "voice_id": "Mark"},
        )
        self.assertEqual(response.status_code, 422, response.text)

    def test_update_draft_rejects_voice_for_provider_managed_agent(self) -> None:
        self._enable_feature()
        remote = SimpleNamespace(
            agent_id="remote-agent-1", published_revision_id="revision-live",
            tools=[], has_unsupported_client_tools=False,
        )
        with patch(
            "app.services.ultravox_admin_service.UltravoxAdminService.validate_provider_agent_link",
            return_value=remote,
        ):
            agent_id = self._create(
                model="ultravox-v0.7",
                management_mode="provider_managed",
                provider_agent={"agent_id": "remote-agent-1"},
            ).json()["id"]
            response = self.client.patch(
                f"/api/v1/agents/{agent_id}/draft",
                json=self._draft_payload(
                    model="ultravox-v0.7",
                    management_mode="provider_managed",
                    provider_agent={"agent_id": "remote-agent-1"},
                    voice={"mode": "provider", "provider": "ultravox", "voice_id": "Mark"},
                ),
            )
        self.assertEqual(response.status_code, 422, response.text)

    def test_create_and_update_draft_with_voice_never_call_ultravox_provider_client(self) -> None:
        self._enable_feature()
        guard = AssertionError("saving a draft must never call the Ultravox provider client")
        with patch("app.services.ultravox_provider_client.UltravoxProviderClient.list_agents", side_effect=guard), \
             patch("app.services.ultravox_provider_client.UltravoxProviderClient.get_agent", side_effect=guard), \
             patch("app.services.ultravox_provider_client.UltravoxProviderClient.list_voices", side_effect=guard), \
             patch("app.services.ultravox_provider_client.UltravoxProviderClient.get_voice", side_effect=guard), \
             patch("app.services.ultravox_provider_client.UltravoxProviderClient.get_voice_preview", side_effect=guard), \
             patch("app.services.ultravox_provider_client.UltravoxProviderClient.get_tts_api_keys", side_effect=guard), \
             patch("app.services.ultravox_provider_client.UltravoxProviderClient.preview_external_voice", side_effect=guard):
            create_response = self._create(
                voice={"mode": "provider", "provider": "ultravox", "voice_id": "Mark"}
            )
            self.assertEqual(create_response.status_code, 201, create_response.text)
            agent_id = create_response.json()["id"]
            update_response = self.client.patch(
                f"/api/v1/agents/{agent_id}/draft",
                json=self._draft_payload(voice={
                    "mode": "provider_external", "provider": "elevenlabs", "voice_id": "eleven-x",
                    "settings": {"model": "eleven_turbo_v2_5"},
                }),
            )
            self.assertEqual(update_response.status_code, 200, update_response.text)

    # -- publish preflight: voice (Phase D) --

    def test_publish_provider_voice_checks_accessibility_and_succeeds(self) -> None:
        self._enable_feature()
        agent_id = self._create(voice={"mode": "provider", "provider": "ultravox", "voice_id": "Mark"}).json()["id"]
        with patch("app.services.ultravox_admin_service.UltravoxAdminService.get_voice") as mock_get_voice:
            response = self.client.post(f"/api/v1/agents/{agent_id}/publish")
        self.assertEqual(response.status_code, 200, response.text)
        mock_get_voice.assert_called_once_with(self.tenant.id, "Mark")

    def test_publish_provider_voice_blocked_when_not_accessible(self) -> None:
        self._enable_feature()
        agent_id = self._create(voice={"mode": "provider", "provider": "ultravox", "voice_id": "Mark"}).json()["id"]
        from app.services.ultravox_provider_client import UltravoxProviderError
        with patch(
            "app.services.ultravox_admin_service.UltravoxAdminService.get_voice",
            side_effect=UltravoxProviderError("provider_resource_not_found", 404),
        ):
            response = self.client.post(f"/api/v1/agents/{agent_id}/publish")
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["detail"], "voice_not_accessible")
        self.assertIsNone(self.client.get(f"/api/v1/agents/{agent_id}").json()["published_version_id"])

    def test_publish_provider_voice_outage_preserves_the_safe_provider_error_code(self) -> None:
        self._enable_feature()
        agent_id = self._create(voice={"mode": "provider", "provider": "ultravox", "voice_id": "Mark"}).json()["id"]
        from app.services.ultravox_provider_client import UltravoxProviderError
        with patch(
            "app.services.ultravox_admin_service.UltravoxAdminService.get_voice",
            side_effect=UltravoxProviderError("provider_unavailable", 503),
        ):
            response = self.client.post(f"/api/v1/agents/{agent_id}/publish")
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["detail"], "provider_unavailable")

    def test_publish_provider_external_blocked_without_elevenlabs_byok(self) -> None:
        self._enable_feature()
        agent_id = self._create(voice={
            "mode": "provider_external", "provider": "elevenlabs", "voice_id": "x",
            "settings": {"model": "eleven_turbo_v2_5"},
        }).json()["id"]
        with patch(
            "app.services.ultravox_admin_service.UltravoxAdminService.validate_external_voice_credentials",
            side_effect=ValueError("external_tts_credentials_unavailable"),
        ), patch(
            "app.services.ultravox_admin_service.UltravoxAdminService.preview_external_voice",
            side_effect=AssertionError("publish must never generate a preview"),
        ):
            response = self.client.post(f"/api/v1/agents/{agent_id}/publish")
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["detail"], "external_tts_credentials_unavailable")
        self.assertIsNone(self.client.get(f"/api/v1/agents/{agent_id}").json()["published_version_id"])

    def test_publish_provider_external_succeeds_with_byok_and_never_generates_preview(self) -> None:
        self._enable_feature()
        agent_id = self._create(voice={
            "mode": "provider_external", "provider": "elevenlabs", "voice_id": "x",
            "settings": {"model": "eleven_turbo_v2_5"},
        }).json()["id"]
        with patch(
            "app.services.ultravox_admin_service.UltravoxAdminService.validate_external_voice_credentials"
        ) as mock_validate, patch(
            "app.services.ultravox_admin_service.UltravoxAdminService.preview_external_voice",
            side_effect=AssertionError("publish must never generate a preview"),
        ):
            response = self.client.post(f"/api/v1/agents/{agent_id}/publish")
        self.assertEqual(response.status_code, 200, response.text)
        mock_validate.assert_called_once_with(self.tenant.id, "elevenlabs")

    def test_publish_without_voice_configured_skips_voice_preflight(self) -> None:
        self._enable_feature()
        agent_id = self._create().json()["id"]
        guard = AssertionError("no voice configured: publish must not call Ultravox for voice")
        with patch("app.services.ultravox_admin_service.UltravoxAdminService.get_voice", side_effect=guard), \
             patch("app.services.ultravox_admin_service.UltravoxAdminService.validate_external_voice_credentials", side_effect=guard):
            response = self.client.post(f"/api/v1/agents/{agent_id}/publish")
        self.assertEqual(response.status_code, 200, response.text)

    def test_publish_treats_legacy_default_voice_as_provider_voice_preflight(self) -> None:
        self._enable_feature()
        agent_id = self._create(voice_agent_config_id=self.voice_agent_config_id).json()["id"]
        with patch("app.services.ultravox_admin_service.UltravoxAdminService.get_voice") as mock_get_voice:
            response = self.client.post(f"/api/v1/agents/{agent_id}/publish")
        self.assertEqual(response.status_code, 200, response.text)
        # self.voice_agent_config_id was seeded in setUp with default_voice="nova".
        mock_get_voice.assert_called_once_with(self.tenant.id, "nova")

    def test_publish_provider_managed_preflight_is_unaffected_by_the_new_voice_preflight(self) -> None:
        self._enable_feature()
        remote = SimpleNamespace(
            agent_id="remote-agent-1", published_revision_id="revision-live",
            tools=[], has_unsupported_client_tools=False,
        )
        guard = AssertionError("provider_managed publish must not run the serviglobal_managed voice preflight")
        with patch(
            "app.services.ultravox_admin_service.UltravoxAdminService.validate_provider_agent_link",
            return_value=remote,
        ):
            agent_id = self._create(
                model="ultravox-v0.7",
                management_mode="provider_managed",
                provider_agent={"agent_id": "remote-agent-1"},
            ).json()["id"]
        with patch(
            "app.services.ultravox_admin_service.UltravoxAdminService.validate_execution_preflight",
            return_value=remote,
        ), patch("app.services.ultravox_admin_service.UltravoxAdminService.get_voice", side_effect=guard), \
             patch("app.services.ultravox_admin_service.UltravoxAdminService.validate_external_voice_credentials", side_effect=guard):
            response = self.client.post(f"/api/v1/agents/{agent_id}/publish")
        self.assertEqual(response.status_code, 200, response.text)

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

        with patch("app.services.ultravox_admin_service.UltravoxAdminService.get_voice"):
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
        with patch("app.services.ultravox_admin_service.UltravoxAdminService.get_voice"):
            republished = self.client.post(
                f"/api/v1/agents/{agent_id}/publish",
                json={"expected_draft_version_id": body["id"]},
            )
        self.assertEqual(republished.status_code, 200, republished.text)
        self.assertEqual(republished.json()["published_version_id"], body["id"])
        self.assertEqual(republished.json()["name"], "Agente editable")

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
        conflict = self.client.post(f"/api/v1/agents/{agent_id}/delete")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"], "agent_delete_requires_archived")

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

    def test_archived_agent_with_ended_voice_sessions_can_be_deleted_without_losing_history(self) -> None:
        from app.models.voice_sessions import VoiceSession, VoiceSessionEvent

        self._enable_feature()
        agent_id = self._create().json()["id"]
        published_version_id = self.client.post(
            f"/api/v1/agents/{agent_id}/publish"
        ).json()["published_version_id"]
        with SessionLocal() as db:
            session = VoiceSession(
                    tenant_id=self.tenant.id,
                    agent_id=agent_id,
                    agent_version_id=published_version_id,
                    channel="internal_test",
                    direction="internal",
                    provider="ultravox",
                    status="ended",
                    provider_session_id="provider-call-1",
                )
            db.add(session)
            db.flush()
            db.add(VoiceSessionEvent(tenant_id=self.tenant.id, voice_session_id=session.id, event_type="voice.session.ended", source="control-plane"))
            db.commit()
            session_id = session.id

        self.client.post(f"/api/v1/agents/{agent_id}/archive")
        response = self.client.post(f"/api/v1/agents/{agent_id}/delete")
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(self.client.get(f"/api/v1/agents/{agent_id}").status_code, 404)
        with SessionLocal() as db:
            history = db.get(VoiceSession, session_id)
            self.assertIsNotNone(history)
            self.assertIsNone(history.agent_id)
            self.assertIsNone(history.agent_version_id)
            self.assertEqual(history.deleted_agent_id, agent_id)
            self.assertEqual(history.deleted_agent_version_id, published_version_id)
            self.assertEqual(history.provider_session_id, "provider-call-1")
            self.assertEqual(len(history.events), 1)

    def test_archived_agent_with_live_voice_session_closes_room_and_preserves_history(self) -> None:
        from app.models.voice_sessions import VoiceSession
        from unittest.mock import AsyncMock, patch

        self._enable_feature()
        agent_id = self._create().json()["id"]
        version_id = self.client.post(f"/api/v1/agents/{agent_id}/publish").json()["published_version_id"]
        with SessionLocal() as db:
            session = VoiceSession(tenant_id=self.tenant.id, agent_id=agent_id, agent_version_id=version_id, channel="internal_test", direction="internal", provider="ultravox", status="connected")
            db.add(session)
            db.commit()
            session_id = session.id
        self.client.post(f"/api/v1/agents/{agent_id}/archive")
        with patch("app.services.livekit_runtime_backend.LiveKitRuntimeBackend.close_session_room", new_callable=AsyncMock) as close:
            response = self.client.post(f"/api/v1/agents/{agent_id}/delete")
            close.assert_awaited_once_with(session_id)
        self.assertEqual(response.status_code, 204, response.text)
        with SessionLocal() as db:
            history = db.get(VoiceSession, session_id)
            self.assertEqual(history.status, "cancelled")
            self.assertEqual(history.end_reason, "agent_deleted")
            self.assertEqual(history.deleted_agent_id, agent_id)
            self.assertIsNone(history.agent_id)
            self.assertIn("voice.session.cancelled", [event.event_type for event in history.events])

    def test_archived_agent_room_close_failure_keeps_agent_and_session(self) -> None:
        from app.models.voice_sessions import VoiceSession
        from unittest.mock import AsyncMock, patch

        self._enable_feature()
        agent_id = self._create().json()["id"]
        version_id = self.client.post(f"/api/v1/agents/{agent_id}/publish").json()["published_version_id"]
        with SessionLocal() as db:
            session = VoiceSession(tenant_id=self.tenant.id, agent_id=agent_id, agent_version_id=version_id, channel="webrtc", direction="internal", provider="ultravox", status="connected")
            db.add(session)
            db.commit()
            session_id = session.id
        self.client.post(f"/api/v1/agents/{agent_id}/archive")
        with patch("app.services.livekit_runtime_backend.LiveKitRuntimeBackend.close_session_room", new_callable=AsyncMock, side_effect=RuntimeError("unavailable")):
            response = self.client.post(f"/api/v1/agents/{agent_id}/delete")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"], "agent_delete_room_close_failed")
        self.assertEqual(self.client.get(f"/api/v1/agents/{agent_id}").json()["status"], "archived")
        with SessionLocal() as db:
            history = db.get(VoiceSession, session_id)
            self.assertEqual(history.status, "connected")
            self.assertEqual(history.agent_id, agent_id)

    def test_archived_agent_with_dispatch_in_flight_can_retry_after_room_is_known(self) -> None:
        from app.models.voice_sessions import VoiceSession
        from unittest.mock import AsyncMock, patch

        self._enable_feature()
        agent_id = self._create().json()["id"]
        version_id = self.client.post(f"/api/v1/agents/{agent_id}/publish").json()["published_version_id"]
        with SessionLocal() as db:
            session = VoiceSession(tenant_id=self.tenant.id, agent_id=agent_id, agent_version_id=version_id, channel="webrtc", direction="internal", provider="ultravox", status="dispatching")
            db.add(session)
            db.commit()
            session_id = session.id
        self.client.post(f"/api/v1/agents/{agent_id}/archive")
        response = self.client.post(f"/api/v1/agents/{agent_id}/delete")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"], "agent_delete_session_dispatching")
        with SessionLocal() as db:
            db.get(VoiceSession, session_id).livekit_room_name = f"sg-vs-{session_id}"
            db.commit()
        with patch("app.services.livekit_runtime_backend.LiveKitRuntimeBackend.close_session_room", new_callable=AsyncMock) as close:
            response = self.client.post(f"/api/v1/agents/{agent_id}/delete")
            close.assert_awaited_once_with(session_id)
        self.assertEqual(response.status_code, 204, response.text)

    def test_archived_agent_with_stale_voice_session_is_deleted_and_history_reconciled(self) -> None:
        from app.models.voice_sessions import VoiceSession
        from unittest.mock import AsyncMock, patch

        self._enable_feature()
        agent_id = self._create().json()["id"]
        version_id = self.client.post(f"/api/v1/agents/{agent_id}/publish").json()["published_version_id"]
        stale_at = datetime.now(timezone.utc) - timedelta(days=2)
        with SessionLocal() as db:
            session = VoiceSession(
                tenant_id=self.tenant.id, agent_id=agent_id, agent_version_id=version_id,
                channel="internal_test", direction="internal", provider="ultravox",
                status="connected", requested_at=stale_at, updated_at=stale_at,
            )
            db.add(session)
            db.commit()
            session_id = session.id
        self.client.post(f"/api/v1/agents/{agent_id}/archive")
        with patch("app.services.livekit_runtime_backend.LiveKitRuntimeBackend.close_session_room", new_callable=AsyncMock):
            response = self.client.post(f"/api/v1/agents/{agent_id}/delete")
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(self.client.get(f"/api/v1/agents/{agent_id}").status_code, 404)
        with SessionLocal() as db:
            history = db.get(VoiceSession, session_id)
            self.assertEqual(history.status, "cancelled")
            self.assertEqual(history.end_reason, "agent_deleted")
            self.assertEqual(history.deleted_agent_id, agent_id)
            self.assertEqual(history.deleted_agent_version_id, version_id)
            self.assertIsNone(history.agent_id)
            self.assertIsNone(history.agent_version_id)
            self.assertIn("voice.session.cancelled", [event.event_type for event in history.events])

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
