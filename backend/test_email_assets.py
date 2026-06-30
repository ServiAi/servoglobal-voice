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
from app.services.storage_service import StorageService


class _FakeBody:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def read(self) -> bytes:
        return self.content


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.deleted: list[tuple[str, str]] = []

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        return {"Body": _FakeBody(self.objects[(Bucket, Key)])}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.deleted.append((Bucket, Key))


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
            self.tenant_id = self.tenant.id
            self.user_id = self.user.id
            db.add(TenantMembership(tenant_id=self.tenant_id, user_id=self.user_id, role="tenant_admin", status="active"))
            db.commit()
        app.dependency_overrides[get_current_auth_context] = self._auth_context_override

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    async def _auth_context_override(self):
        with SessionLocal() as db:
            tenant = db.get(Tenant, self.tenant_id)
            user = db.get(User, self.user_id)
            membership = db.scalar(select(TenantMembership).where(TenantMembership.tenant_id == tenant.id))
            return AuthContext(user=user, tenant=tenant, membership=membership)

    def test_upload_email_asset_validates_file_type(self):
        response = self.client.post(
            "/api/v1/integrations/resend/assets",
            files={"file": ("proposal.pdf", b"pdf", "application/pdf")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["original_filename"], "proposal.pdf")

    def test_upload_uses_required_storage_key_prefix(self):
        response = self.client.post(
            "/api/v1/integrations/resend/assets",
            files={"file": ("proposal.pdf", b"pdf", "application/pdf")},
        )

        self.assertEqual(response.status_code, 200)
        asset_id = response.json()["id"]
        with SessionLocal() as db:
            asset = db.get(TenantEmailAsset, asset_id)
        self.assertTrue(asset.storage_key.startswith(f"tenants/{self.tenant_id}/email-assets/{asset_id}/"))

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
                EmailAssetService(db).validate_assets(self.tenant_id, [asset.id])

    def test_s3_storage_upload_read_delete_uses_client(self):
        fake = _FakeS3Client()
        storage = StorageService(driver="s3", bucket="bucket-a", s3_client=fake)
        key = "tenants/tenant-a/email-assets/asset-1/proposal.pdf"

        stored_key = storage.upload_bytes(key, b"pdf")
        content = storage.read_bytes(key)
        storage.delete(key)

        self.assertEqual(stored_key, key)
        self.assertEqual(content, b"pdf")
        self.assertEqual(fake.objects[("bucket-a", key)], b"pdf")
        self.assertEqual(fake.deleted, [("bucket-a", key)])

    def test_s3_storage_requires_bucket(self):
        storage = StorageService(driver="s3", bucket="", s3_client=_FakeS3Client())

        with self.assertRaises(ValueError):
            storage.upload_bytes("tenants/a/email-assets/b/file.pdf", b"pdf")


if __name__ == "__main__":
    unittest.main()
