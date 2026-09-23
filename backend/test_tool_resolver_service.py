from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_tool_resolver_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.identity import Tenant
from app.models.tools import TenantHttpToolConfig, TenantTool
from app.services.tool_resolver_service import ToolResolverService
from app.services.tenant_feature_service import CUSTOM_HTTP_TOOLS, TenantFeatureService


class ToolResolverServiceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            self.tenant = Tenant(name="Tenant A", slug="tenant-a")
            self.other_tenant = Tenant(name="Tenant B", slug="tenant-b")
            db.add_all([self.tenant, self.other_tenant])
            db.commit()
            db.refresh(self.tenant)
            db.refresh(self.other_tenant)
            self.tenant_id = self.tenant.id
            self.other_tenant_id = self.other_tenant.id
            TenantFeatureService(db).set_feature(
                self.tenant_id, CUSTOM_HTTP_TOOLS, True, {}, None
            )
            TenantFeatureService(db).set_feature(
                self.other_tenant_id, CUSTOM_HTTP_TOOLS, True, {}, None
            )

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)

    def _create_custom_tool(self, db, tenant_id, key="custom.customer_balance", status="active"):
        tool = TenantTool(
            tenant_id=tenant_id,
            key=key,
            name="Consultar saldo",
            description="Consulta el saldo pendiente del cliente.",
            status=status,
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
                path_mapping_json={},
                query_mapping_json={},
                body_mapping_json={},
                input_schema_json={"type": "object", "properties": {}},
                response_mapping_json={},
            )
        )
        db.commit()
        return tool

    def test_resolve_returns_platform_tool_unchanged(self):
        with SessionLocal() as db:
            resolved = ToolResolverService(db).resolve(self.tenant_id, "calendar.check_availability")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.source, "platform")
        self.assertEqual(resolved.status, "available")
        self.assertIsNone(resolved.custom_tool_id)

    def test_resolve_returns_none_for_unknown_custom_key(self):
        with SessionLocal() as db:
            resolved = ToolResolverService(db).resolve(self.tenant_id, "custom.does_not_exist")
        self.assertIsNone(resolved)

    def test_resolve_returns_active_custom_tool(self):
        with SessionLocal() as db:
            self._create_custom_tool(db, self.tenant_id)
            resolved = ToolResolverService(db).resolve(self.tenant_id, "custom.customer_balance")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.source, "custom")
        self.assertEqual(resolved.status, "available")
        self.assertIsNone(resolved.required_integration)
        self.assertIsNotNone(resolved.custom_tool_id)

    def test_resolve_returns_none_for_disabled_custom_tool(self):
        with SessionLocal() as db:
            self._create_custom_tool(db, self.tenant_id, status="disabled")
            resolved = ToolResolverService(db).resolve(self.tenant_id, "custom.customer_balance")
        self.assertIsNone(resolved)

    def test_resolve_never_crosses_tenants(self):
        with SessionLocal() as db:
            self._create_custom_tool(db, self.other_tenant_id)
            resolved = ToolResolverService(db).resolve(self.tenant_id, "custom.customer_balance")
        self.assertIsNone(resolved)

    def test_list_all_merges_platform_and_custom(self):
        with SessionLocal() as db:
            self._create_custom_tool(db, self.tenant_id)
            resolved = ToolResolverService(db).list_all(self.tenant_id, status="available")
        sources = {(r.key, r.source) for r in resolved}
        self.assertIn(("calendar.check_availability", "platform"), sources)
        self.assertIn(("custom.customer_balance", "custom"), sources)

    def test_list_all_never_leaks_other_tenants_custom_tools(self):
        with SessionLocal() as db:
            self._create_custom_tool(db, self.other_tenant_id)
            resolved = ToolResolverService(db).list_all(self.tenant_id, status="available")
        self.assertNotIn("custom.customer_balance", {r.key for r in resolved})


if __name__ == "__main__":
    unittest.main()
