from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_tools_custom_api_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.agents import TenantAgent, TenantAgentVersion
from app.models.identity import Tenant, TenantMembership, User
from app.models.tools import TenantHttpToolConfig
from app.services.tenant_feature_service import CUSTOM_HTTP_TOOLS, TenantFeatureService

_BASE = "/api/v1/tools/custom"

_VALID_CREATE_PAYLOAD = {
    "key": "custom.customer_balance",
    "name": "Consultar saldo",
    "description": "Consulta el saldo pendiente del cliente.",
    "method": "GET",
    "base_url": "https://example-api.test",
    "path_template": "/customers/{document}/balance",
    "path_mapping": {"document": "args.document"},
    "input_schema": {
        "type": "object",
        "properties": {"document": {"type": "string"}},
        "required": ["document"],
    },
}


class ToolsCustomApiTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        app.dependency_overrides.clear()
        self.client = TestClient(app)

        with SessionLocal() as db:
            self.tenant = Tenant(name="Tenant A", slug="tenant-a")
            self.other_tenant = Tenant(name="Tenant B", slug="tenant-b")
            db.add_all([self.tenant, self.other_tenant])
            db.commit()
            db.refresh(self.tenant)
            db.refresh(self.other_tenant)
            self.tenant_id = self.tenant.id
            self.other_tenant_id = self.other_tenant.id

            self.user_ids: dict[str, str] = {}
            for role in ("platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"):
                user = User(email=f"{role}@example.com", name=role, status="active")
                db.add(user)
                db.commit()
                db.refresh(user)
                db.add(TenantMembership(tenant_id=self.tenant_id, user_id=user.id, role=role, status="active"))
                db.commit()
                self.user_ids[role] = user.id

            other_admin = User(email="other-tenant-admin@example.com", name="Other tenant admin", status="active")
            db.add(other_admin)
            db.commit()
            db.refresh(other_admin)
            db.add(TenantMembership(tenant_id=self.other_tenant_id, user_id=other_admin.id, role="tenant_admin", status="active"))
            db.commit()
            self.other_admin_user_id = other_admin.id

            TenantFeatureService(db).set_feature(self.tenant_id, CUSTOM_HTTP_TOOLS, True, {}, self.user_ids["tenant_admin"])

        self._active_tenant_id = self.tenant_id
        self._active_user_id = self.user_ids["tenant_admin"]
        app.dependency_overrides[get_current_auth_context] = self._auth_context_override

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    async def _auth_context_override(self):
        with SessionLocal() as db:
            tenant = db.get(Tenant, self._active_tenant_id)
            user = db.get(User, self._active_user_id)
            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == self._active_tenant_id,
                    TenantMembership.user_id == self._active_user_id,
                )
            )
            return AuthContext(user=user, tenant=tenant, membership=membership)

    def _as(self, role: str) -> None:
        self._active_tenant_id = self.tenant_id
        self._active_user_id = self.user_ids[role]

    def _as_other_tenant_admin(self) -> None:
        self._active_tenant_id = self.other_tenant_id
        self._active_user_id = self.other_admin_user_id

    def _create_tool(self, **overrides) -> dict:
        payload = {**_VALID_CREATE_PAYLOAD, **overrides}
        self._as("tenant_admin")
        response = self.client.post(_BASE, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _bind_tool_to_published_agent(self, tenant_id: str, key: str) -> None:
        with SessionLocal() as db:
            agent = TenantAgent(tenant_id=tenant_id, name="Agent", status="active")
            db.add(agent)
            db.flush()
            version = TenantAgentVersion(
                tenant_id=tenant_id,
                agent_id=agent.id,
                version=1,
                status="published",
                language="es",
                timezone="America/Bogota",
                identity_json={},
                instructions_json={},
                behavior_json={},
                runtime_binding_json={
                    "pipeline_type": "realtime",
                    "realtime": {"provider": "ultravox", "model": "x", "management_mode": "serviglobal_managed"},
                    "tools": [{"key": key, "enabled": True, "config": {}}],
                },
            )
            db.add(version)
            db.flush()
            agent.published_version_id = version.id
            db.commit()

    def _bind_tool_to_draft_only(self, tenant_id: str, key: str) -> None:
        with SessionLocal() as db:
            agent = TenantAgent(tenant_id=tenant_id, name="Agent", status="draft")
            db.add(agent)
            db.flush()
            version = TenantAgentVersion(
                tenant_id=tenant_id,
                agent_id=agent.id,
                version=1,
                status="draft",
                language="es",
                timezone="America/Bogota",
                identity_json={},
                instructions_json={},
                behavior_json={},
                runtime_binding_json={
                    "pipeline_type": "realtime",
                    "realtime": {"provider": "ultravox", "model": "x", "management_mode": "serviglobal_managed"},
                    "tools": [{"key": key, "enabled": True, "config": {}}],
                },
            )
            db.add(version)
            db.flush()
            agent.draft_version_id = version.id
            db.commit()

    # ---------------------------------------------------------- CRUD happy path

    def test_crud_happy_path(self):
        created = self._create_tool()
        self.assertEqual(created["status"], "disabled")
        self.assertEqual(created["key"], "custom.customer_balance")

        listing = self.client.get(_BASE)
        self.assertEqual(listing.status_code, 200)
        self.assertIn(created["id"], [item["id"] for item in listing.json()])

        fetched = self.client.get(f"{_BASE}/{created['id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["id"], created["id"])

        updated = self.client.patch(f"{_BASE}/{created['id']}", json={"name": "Saldo actualizado"})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["name"], "Saldo actualizado")

        activated = self.client.post(f"{_BASE}/{created['id']}/activate")
        self.assertEqual(activated.status_code, 200, activated.text)
        self.assertEqual(activated.json()["status"], "active")
        self.assertTrue(activated.json()["credential"]["configured"])

        disabled = self.client.post(f"{_BASE}/{created['id']}/disable")
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(disabled.json()["status"], "disabled")

    # ---------------------------------------------------------- namespace / uniqueness

    def test_invalid_namespace_is_rejected(self):
        self._as("tenant_admin")
        response = self.client.post(_BASE, json={**_VALID_CREATE_PAYLOAD, "key": "calendar.my_tool"})
        self.assertEqual(response.status_code, 422, response.text)

    def test_invalid_url_and_sensitive_static_headers_are_rejected(self):
        self._as("tenant_admin")
        invalid_url = self.client.post(_BASE, json={**_VALID_CREATE_PAYLOAD, "base_url": "https://"})
        self.assertEqual(invalid_url.status_code, 422, invalid_url.text)
        sensitive_header = self.client.post(
            _BASE,
            json={**_VALID_CREATE_PAYLOAD, "headers": {"Authorization": "Bearer must-not-persist"}},
        )
        self.assertEqual(sensitive_header.status_code, 422, sensitive_header.text)

    def test_invalid_input_schema_is_rejected(self):
        self._as("tenant_admin")
        response = self.client.post(
            _BASE,
            json={**_VALID_CREATE_PAYLOAD, "input_schema": {"type": "object", "properties": []}},
        )
        self.assertEqual(response.status_code, 422, response.text)

    def test_duplicate_key_returns_409(self):
        self._create_tool()
        self._as("tenant_admin")
        response = self.client.post(_BASE, json=_VALID_CREATE_PAYLOAD)
        self.assertEqual(response.status_code, 409, response.text)

    # ---------------------------------------------------------- feature gate

    def test_feature_disabled_returns_403_on_every_endpoint(self):
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(self.other_tenant_id, CUSTOM_HTTP_TOOLS, False, {}, self.other_admin_user_id)
        self._as_other_tenant_admin()
        self.assertEqual(self.client.get(_BASE).status_code, 403)
        self.assertEqual(self.client.post(_BASE, json=_VALID_CREATE_PAYLOAD).status_code, 403)

    # ---------------------------------------------------------- tenant isolation

    def test_tenant_does_not_list_tools_of_other_tenant(self):
        created = self._create_tool()
        self._as_other_tenant_admin()
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(self.other_tenant_id, CUSTOM_HTTP_TOOLS, True, {}, self.other_admin_user_id)
        response = self.client.get(_BASE)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(created["id"], [item["id"] for item in response.json()])

    def test_tenant_cannot_get_tool_of_other_tenant_returns_404(self):
        created = self._create_tool()
        self._as_other_tenant_admin()
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(self.other_tenant_id, CUSTOM_HTTP_TOOLS, True, {}, self.other_admin_user_id)
        response = self.client.get(f"{_BASE}/{created['id']}")
        self.assertEqual(response.status_code, 404)

    def test_tenant_cannot_modify_tool_of_other_tenant_returns_404(self):
        created = self._create_tool()
        self._as_other_tenant_admin()
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(self.other_tenant_id, CUSTOM_HTTP_TOOLS, True, {}, self.other_admin_user_id)
        response = self.client.patch(f"{_BASE}/{created['id']}", json={"name": "Hijacked"})
        self.assertEqual(response.status_code, 404)

    def test_tenant_cannot_delete_tool_of_other_tenant_returns_404(self):
        created = self._create_tool()
        self._as_other_tenant_admin()
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(self.other_tenant_id, CUSTOM_HTTP_TOOLS, True, {}, self.other_admin_user_id)
        response = self.client.delete(f"{_BASE}/{created['id']}")
        self.assertEqual(response.status_code, 404)

    # ---------------------------------------------------------- secrets

    def test_secrets_never_appear_in_any_response(self):
        created = self._create_tool(
            auth_type="bearer",
            secrets={"token": "s3cr3t-value-12345"},
        )
        self.assertNotIn("s3cr3t-value-12345", str(created))
        fetched = self.client.get(f"{_BASE}/{created['id']}")
        self.assertNotIn("s3cr3t-value-12345", fetched.text)
        listing = self.client.get(_BASE)
        self.assertNotIn("s3cr3t-value-12345", listing.text)
        self.assertTrue(created["credential"]["configured"])
        self.assertNotEqual(created["credential"]["masked_fields"]["token"], "s3cr3t-value-12345")

    def test_legacy_sensitive_static_header_is_redacted_from_readers(self):
        created = self._create_tool()
        with SessionLocal() as db:
            config = db.scalar(
                select(TenantHttpToolConfig).where(TenantHttpToolConfig.tenant_tool_id == created["id"])
            )
            config.headers_json = {"Authorization": "Bearer legacy-secret", "X-Region": "co"}
            db.commit()
        self._as("tenant_viewer")
        response = self.client.get(f"{_BASE}/{created['id']}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["headers"], {"X-Region": "co"})

    def test_invalid_credential_does_not_leave_a_tool_behind(self):
        self._as("tenant_admin")
        response = self.client.post(
            _BASE,
            json={**_VALID_CREATE_PAYLOAD, "auth_type": "bearer", "secrets": {"wrong": "value"}},
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.get(_BASE).json(), [])

    def test_rejected_patch_does_not_persist_other_fields(self):
        created = self._create_tool()
        response = self.client.patch(
            f"{_BASE}/{created['id']}",
            json={"name": "Must roll back", "auth_type": "bearer", "secrets": {"wrong": "value"}},
        )
        self.assertEqual(response.status_code, 422, response.text)
        fetched = self.client.get(f"{_BASE}/{created['id']}")
        self.assertEqual(fetched.json()["name"], created["name"])

    def test_api_key_header_can_change_without_rotating_secret(self):
        created = self._create_tool(
            auth_type="api_key",
            api_key_header_name="X-Old-Key",
            secrets={"api_key": "s3cr3t-value"},
        )
        response = self.client.patch(
            f"{_BASE}/{created['id']}",
            json={"auth_type": "api_key", "api_key_header_name": "X-New-Key"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["credential"]["api_key_header_name"], "X-New-Key")
        self.assertTrue(response.json()["credential"]["configured"])

        preserved = self.client.patch(
            f"{_BASE}/{created['id']}", json={"auth_type": "api_key", "name": "Renamed"}
        )
        self.assertEqual(preserved.status_code, 200, preserved.text)
        self.assertEqual(preserved.json()["credential"]["api_key_header_name"], "X-New-Key")

    # ---------------------------------------------------------- delete in use

    def test_delete_blocked_when_bound_to_published_agent(self):
        created = self._create_tool()
        self._bind_tool_to_published_agent(self.tenant_id, created["key"])
        self._as("tenant_admin")
        response = self.client.delete(f"{_BASE}/{created['id']}")
        self.assertEqual(response.status_code, 409, response.text)

    def test_delete_allowed_when_bound_only_to_draft(self):
        created = self._create_tool()
        self._bind_tool_to_draft_only(self.tenant_id, created["key"])
        self._as("tenant_admin")
        response = self.client.delete(f"{_BASE}/{created['id']}")
        self.assertEqual(response.status_code, 204, response.text)

    # ---------------------------------------------------------- activation

    def test_activate_fails_without_credential_when_required(self):
        created = self._create_tool(auth_type="bearer")
        self._as("tenant_admin")
        response = self.client.post(f"{_BASE}/{created['id']}/activate")
        self.assertEqual(response.status_code, 422, response.text)

    # ---------------------------------------------------------- test endpoint

    def test_test_tool_does_not_require_active_status(self):
        created = self._create_tool()
        self.assertEqual(created["status"], "disabled")
        self._as("tenant_admin")
        response = self.client.post(f"{_BASE}/{created['id']}/test", json={"arguments": {"document": "1"}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["success"])

    def test_test_tool_reports_missing_credential_without_500(self):
        created = self._create_tool(auth_type="bearer")
        response = self.client.post(
            f"{_BASE}/{created['id']}/test", json={"arguments": {"document": "1"}}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["success"])
        self.assertEqual(response.json()["error_code"], "tool_credential_not_configured")


if __name__ == "__main__":
    unittest.main()
