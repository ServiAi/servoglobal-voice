from __future__ import annotations

import unittest
from unittest.mock import patch

from _integrations_2a_test_base import Integration2ATestCase
from app.db.session import SessionLocal
from app.models.tools import TenantHttpToolConfig, TenantTool
from app.services.tenant_feature_service import AGENT_BUILDER, CUSTOM_HTTP_TOOLS, TenantFeatureService
from app.services.tenant_tool_credential_service import TenantToolCredentialService


class AgentBuilderCustomToolsPreflightTests(Integration2ATestCase):
    def _enable_feature(self, tenant_id: str | None = None) -> None:
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(
                tenant_id or self.tenant.id, AGENT_BUILDER, True, {}, self.user.id
            )
            TenantFeatureService(db).set_feature(
                tenant_id or self.tenant.id, CUSTOM_HTTP_TOOLS, True, {}, self.user.id
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

    def _create_custom_tool(
        self, *, tenant_id: str | None = None, auth_type: str = "none", configure_credential: bool = True
    ) -> str:
        tenant_id = tenant_id or self.tenant.id
        with SessionLocal() as db:
            tool = TenantTool(
                tenant_id=tenant_id,
                key="custom.customer_balance",
                name="Consultar saldo",
                description="Consulta el saldo pendiente del cliente.",
                status="active",
            )
            db.add(tool)
            db.commit()
            db.refresh(tool)
            db.add(
                TenantHttpToolConfig(
                    tenant_id=tenant_id,
                    tenant_tool_id=tool.id,
                    method="GET",
                    base_url="https://example-api.test",
                    path_template="/customers/{document}/balance",
                    headers_json={},
                    path_mapping_json={"document": "args.document"},
                    query_mapping_json={},
                    body_mapping_json={},
                    input_schema_json={
                        "type": "object",
                        "properties": {"document": {"type": "string"}},
                        "required": ["document"],
                    },
                    response_mapping_json={},
                )
            )
            db.commit()
            if auth_type != "none":
                if configure_credential:
                    TenantToolCredentialService(db).set_credential(
                        tenant_id, tool.id, auth_type=auth_type, secrets={"token": "s3cr3t"}
                    )
                else:
                    # Simulates a tool whose auth_type was picked in the UI
                    # but no secret has been provided yet -- the row exists,
                    # secrets_json_encrypted stays null.
                    from app.models.tools import TenantToolCredential

                    db.add(
                        TenantToolCredential(
                            tenant_id=tenant_id, tenant_tool_id=tool.id, auth_type=auth_type
                        )
                    )
                    db.commit()
            return tool.key

    def test_publish_fails_when_custom_tool_requires_credential_and_none_is_set(self) -> None:
        self._enable_feature()
        tool_key = self._create_custom_tool(auth_type="bearer", configure_credential=False)
        agent_id = self._create(
            tools=[{"key": tool_key, "enabled": True, "config": {}}]
        ).json()["id"]
        with patch("app.services.ultravox_admin_service.UltravoxAdminService.get_voice"):
            response = self.client.post(f"/api/v1/agents/{agent_id}/publish", json={})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("tool_integration_not_configured", response.text)

    def test_publish_succeeds_once_credential_is_set(self) -> None:
        self._enable_feature()
        tool_key = self._create_custom_tool(auth_type="none")
        agent_id = self._create(
            tools=[{"key": tool_key, "enabled": True, "config": {}}]
        ).json()["id"]
        with patch("app.services.ultravox_admin_service.UltravoxAdminService.get_voice"):
            response = self.client.post(f"/api/v1/agents/{agent_id}/publish", json={})
        self.assertEqual(response.status_code, 200, response.text)

    def test_unknown_custom_tool_key_is_rejected_at_draft_save_time(self) -> None:
        """Draft-save-time validation is resolver-aware (not just the
        static platform Registry) -- an unknown custom.* key is rejected
        immediately, before an agent is even created, not deferred to
        publish preflight."""
        self._enable_feature()
        response = self._create(
            tools=[{"key": "custom.does_not_exist", "enabled": True, "config": {}}]
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("tool_not_found", response.text)

    def test_publish_fails_if_tool_was_disabled_after_binding(self) -> None:
        """Defense in depth: _publish_tools_preflight re-resolves at publish
        time rather than trusting the draft's state at save time -- a tool
        disabled between draft-save and publish must block publish even
        though it passed the draft-save check earlier. A disabled custom
        tool resolves to None (same as an unknown key -- ToolResolverService
        deliberately never distinguishes "disabled" from "doesn't exist" to
        an unprivileged resolve() caller), so this surfaces as
        tool_not_found rather than tool_not_available."""
        self._enable_feature()
        tool_key = self._create_custom_tool(auth_type="none")
        agent_id = self._create(tools=[{"key": tool_key, "enabled": True, "config": {}}]).json()["id"]
        with SessionLocal() as db:
            db.query(TenantTool).filter_by(key=tool_key, tenant_id=self.tenant.id).update({"status": "disabled"})
            db.commit()
        with patch("app.services.ultravox_admin_service.UltravoxAdminService.get_voice"):
            response = self.client.post(f"/api/v1/agents/{agent_id}/publish", json={})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("tool_not_found", response.text)

    def test_custom_tool_cannot_be_bound_to_provider_managed_agent(self) -> None:
        self._enable_feature()
        tool_key = self._create_custom_tool(auth_type="none")
        response = self._create(
            management_mode="provider_managed",
            provider="ultravox",
            provider_agent={"agent_id": "remote-agent-1"},
            tools=[{"key": tool_key, "enabled": True, "config": {}}],
        )
        self.assertEqual(response.status_code, 422, response.text)

    def test_custom_tool_from_another_tenant_cannot_be_bound(self) -> None:
        other_tenant, other_user = self._seed_tenant_user(slug="tenant-tools-other", email="tools-other@example.com")
        self._enable_feature()
        other_tool_key = self._create_custom_tool(tenant_id=other_tenant.id, auth_type="none")
        response = self._create(tools=[{"key": other_tool_key, "enabled": True, "config": {}}])
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("tool_not_found", response.text)


if __name__ == "__main__":
    unittest.main()
