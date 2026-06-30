from __future__ import annotations

import os
from pathlib import Path
import unittest

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_email_assets_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"
os.environ["EMAIL_MAX_ATTACHMENT_BYTES"] = "16"
os.environ["EMAIL_MAX_TOTAL_ATTACHMENTS_BYTES"] = "32"
os.environ["EMAIL_ASSETS_STORAGE_PATH"] = "storage/test-email-assets"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.identity import Tenant, TenantMembership, User
from app.models.integrations import TenantEmailAsset
from app.services.email_asset_service import EmailAssetService


class EmailAssetsTests(unittest.TestCase):
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
            self.user = User(email="admin@example.com", name="Admin", status="active")
            db.add_all([self.tenant, self.user])
            db.commit()
            db.refresh(self.tenant)
            db.refresh(self.user)
            db.add(TenantMembership(tenant_id=self.tenant.id, user_id=self.user.id, role="tenant_admin", status="active"))
            db.commit()
        app.dependency_overrides[get_current_auth_context] = self._auth_context_override

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    async def _auth_context_override(self):
        with SessionLocal() as db:
            tenant = db.get(Tenant, self.tenant.id)
            user = db.get(User, self.user.id)
            membership = db.scalar(select(TenantMembership).where(TenantMembership.tenant_id == tenant.id))
            return AuthContext(user=user, tenant=tenant, membership=membership)

    def test_upload_email_asset_validates_file_type(self):
        response = self.client.post(
            "/api/v1/integrations/resend/assets",
            files={"file": ("proposal.pdf", b"pdf", "application/pdf")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["original_filename"], "proposal.pdf")

    def test_upload_email_asset_blocks_executable(self):
        response = self.client.post(
            "/api/v1/integrations/resend/assets",
            files={"file": ("run.exe", b"x", "application/octet-stream")},
        )

        self.assertEqual(response.status_code, 422)

    def test_upload_email_asset_enforces_size_limit(self):
        response = self.client.post(
            "/api/v1/integrations/resend/assets",
            files={"file": ("big.pdf", b"x" * 17, "application/pdf")},
        )

        self.assertEqual(response.status_code, 422)

    def test_cross_tenant_assets_are_rejected(self):
        with SessionLocal() as db:
            other = Tenant(name="Tenant B", slug="tenant-b")
            db.add(other)
            db.commit()
            db.refresh(other)
            db.add(
                TenantEmailAsset(
                    tenant_id=other.id,
                    original_filename="other.pdf",
                    storage_key="other/asset.pdf",
                    mime_type="application/pdf",
                    file_size_bytes=3,
                    checksum_sha256="0" * 64,
                    visibility="private",
                    status="uploaded",
                )
            )
            db.commit()
            asset = db.scalar(select(TenantEmailAsset).where(TenantEmailAsset.tenant_id == other.id))

        with SessionLocal() as db:
            with self.assertRaises(ValueError):
                EmailAssetService(db).validate_assets(self.tenant.id, [asset.id])


if __name__ == "__main__":
    unittest.main()
