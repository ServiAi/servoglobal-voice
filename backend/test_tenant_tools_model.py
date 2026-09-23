from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_tenant_tools_model_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.identity import Tenant
from app.models.tools import TenantHttpToolConfig, TenantTool, TenantToolCredential


class TenantToolsModelTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            tenant = Tenant(name="Tenant A", slug="tenant-a")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            self.tenant_id = tenant.id

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)

    def _create_tool(self, db, key="custom.customer_balance"):
        tool = TenantTool(
            tenant_id=self.tenant_id,
            key=key,
            name="Consultar saldo",
            description="Consulta el saldo pendiente del cliente.",
        )
        db.add(tool)
        db.commit()
        db.refresh(tool)
        return tool

    def test_unique_tenant_and_key(self):
        with SessionLocal() as db:
            self._create_tool(db)
            db.add(
                TenantTool(
                    tenant_id=self.tenant_id,
                    key="custom.customer_balance",
                    name="Duplicado",
                    description="...",
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_namespace_check_constraint_rejects_non_custom_key(self):
        with SessionLocal() as db:
            db.add(
                TenantTool(
                    tenant_id=self.tenant_id,
                    key="calendar.my_tool",
                    name="Invalido",
                    description="...",
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_cascade_delete_removes_config_and_credential(self):
        with SessionLocal() as db:
            tool = self._create_tool(db)
            db.add(
                TenantHttpToolConfig(
                    tenant_id=self.tenant_id,
                    tenant_tool_id=tool.id,
                    method="GET",
                    base_url="https://example-api.test",
                    path_template="/customers/{document}/balance",
                    headers_json={},
                    path_mapping_json={},
                    query_mapping_json={},
                    body_mapping_json={},
                    input_schema_json={},
                    response_mapping_json={},
                )
            )
            db.add(
                TenantToolCredential(
                    tenant_id=self.tenant_id,
                    tenant_tool_id=tool.id,
                    auth_type="bearer",
                    secrets_json_encrypted="{}",
                )
            )
            db.commit()
            tool_id = tool.id

        with SessionLocal() as db:
            tool = db.get(TenantTool, tool_id)
            db.delete(tool)
            db.commit()

        with SessionLocal() as db:
            self.assertIsNone(db.get(TenantTool, tool_id))
            remaining_configs = (
                db.query(TenantHttpToolConfig).filter_by(tenant_tool_id=tool_id).all()
            )
            remaining_credentials = (
                db.query(TenantToolCredential).filter_by(tenant_tool_id=tool_id).all()
            )
            self.assertEqual(remaining_configs, [])
            self.assertEqual(remaining_credentials, [])


if __name__ == "__main__":
    unittest.main()
