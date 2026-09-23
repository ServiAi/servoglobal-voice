from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_tenant_tool_credential_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.identity import Tenant
from app.models.tools import TenantTool
from app.services.tenant_tool_credential_service import (
    TenantToolCredentialError,
    TenantToolCredentialService,
    TenantToolNotFoundError,
)


class TenantToolCredentialServiceTests(unittest.TestCase):
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

            tool = TenantTool(
                tenant_id=self.tenant_id,
                key="custom.customer_balance",
                name="Consultar saldo",
                description="...",
            )
            other_tool = TenantTool(
                tenant_id=self.other_tenant_id,
                key="custom.customer_balance",
                name="Consultar saldo",
                description="...",
            )
            db.add_all([tool, other_tool])
            db.commit()
            db.refresh(tool)
            db.refresh(other_tool)
            self.tool_id = tool.id
            self.other_tool_id = other_tool.id

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)

    def test_bearer_round_trip(self):
        with SessionLocal() as db:
            service = TenantToolCredentialService(db)
            service.set_credential(
                self.tenant_id, self.tool_id, auth_type="bearer", secrets={"token": "s3cr3t-value"}
            )
            resolved = service.resolve_for_execution(self.tenant_id, self.tool_id)
        self.assertEqual(resolved.auth_type, "bearer")
        self.assertEqual(resolved.secrets["token"], "s3cr3t-value")

    def test_api_key_round_trip_requires_header_name(self):
        with SessionLocal() as db:
            service = TenantToolCredentialService(db)
            with self.assertRaises(TenantToolCredentialError):
                service.set_credential(
                    self.tenant_id, self.tool_id, auth_type="api_key", secrets={"api_key": "abc"}
                )
            service.set_credential(
                self.tenant_id,
                self.tool_id,
                auth_type="api_key",
                secrets={"api_key": "abc123"},
                api_key_header_name="X-API-Key",
            )
            resolved = service.resolve_for_execution(self.tenant_id, self.tool_id)
        self.assertEqual(resolved.secrets["api_key"], "abc123")
        self.assertEqual(resolved.api_key_header_name, "X-API-Key")

    def test_basic_round_trip(self):
        with SessionLocal() as db:
            service = TenantToolCredentialService(db)
            service.set_credential(
                self.tenant_id,
                self.tool_id,
                auth_type="basic",
                secrets={"username": "svc", "password": "hunter2"},
            )
            resolved = service.resolve_for_execution(self.tenant_id, self.tool_id)
        self.assertEqual(resolved.secrets, {"username": "svc", "password": "hunter2"})

    def test_none_auth_type_requires_no_secrets(self):
        with SessionLocal() as db:
            service = TenantToolCredentialService(db)
            service.set_credential(self.tenant_id, self.tool_id, auth_type="none")
            resolved = service.resolve_for_execution(self.tenant_id, self.tool_id)
        self.assertEqual(resolved.secrets, {})

    def test_masked_view_never_contains_raw_secret(self):
        with SessionLocal() as db:
            service = TenantToolCredentialService(db)
            service.set_credential(
                self.tenant_id, self.tool_id, auth_type="bearer", secrets={"token": "s3cr3t-value"}
            )
            masked = service.get_masked(self.tenant_id, self.tool_id)
        self.assertTrue(masked.configured)
        self.assertNotEqual(masked.masked_fields["token"], "s3cr3t-value")
        self.assertNotIn("s3cr3t-value", masked.masked_fields["token"])

    def test_no_credential_row_is_configured_by_default(self):
        with SessionLocal() as db:
            service = TenantToolCredentialService(db)
            self.assertTrue(service.is_configured_or_not_required(self.tenant_id, self.tool_id))
            masked = service.get_masked(self.tenant_id, self.tool_id)
        self.assertEqual(masked.auth_type, "none")
        self.assertTrue(masked.configured)

    def test_cross_tenant_resolve_is_rejected(self):
        with SessionLocal() as db:
            service = TenantToolCredentialService(db)
            service.set_credential(
                self.other_tenant_id, self.other_tool_id, auth_type="bearer", secrets={"token": "other-secret"}
            )
            with self.assertRaises(TenantToolNotFoundError):
                service.resolve_for_execution(self.tenant_id, self.other_tool_id)
            with self.assertRaises(TenantToolNotFoundError):
                service.get_masked(self.tenant_id, self.other_tool_id)

    def test_rotation_replaces_old_ciphertext(self):
        with SessionLocal() as db:
            service = TenantToolCredentialService(db)
            service.set_credential(
                self.tenant_id, self.tool_id, auth_type="bearer", secrets={"token": "first-value"}
            )
            first = service.resolve_for_execution(self.tenant_id, self.tool_id)
            service.set_credential(
                self.tenant_id, self.tool_id, auth_type="bearer", secrets={"token": "second-value"}
            )
            second = service.resolve_for_execution(self.tenant_id, self.tool_id)
        self.assertEqual(first.secrets["token"], "first-value")
        self.assertEqual(second.secrets["token"], "second-value")

    def test_delete_credential_resets_to_not_required(self):
        with SessionLocal() as db:
            service = TenantToolCredentialService(db)
            service.set_credential(
                self.tenant_id, self.tool_id, auth_type="bearer", secrets={"token": "value"}
            )
            service.delete_credential(self.tenant_id, self.tool_id)
            self.assertTrue(service.is_configured_or_not_required(self.tenant_id, self.tool_id))


if __name__ == "__main__":
    unittest.main()
