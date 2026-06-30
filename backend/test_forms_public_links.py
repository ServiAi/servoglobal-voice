from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
import unittest

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_forms_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from sqlalchemy import func, select

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.crm import CrmActivity, CrmContact, CrmLead
from app.models.identity import Tenant
from app.services.crm_pipeline_service import CrmPipelineService
from app.services.form_service import FormService


class PublicFormsTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            self.tenant = Tenant(name="Tenant A", slug="tenant-a")
            db.add(self.tenant)
            db.commit()
            db.refresh(self.tenant)
            self.tenant_id = self.tenant.id
            stage = CrmPipelineService(db).ensure_default_pipeline(self.tenant_id)[0]
            contact = CrmContact(tenant_id=self.tenant_id, name="Juan", email="juan@example.com", phone="+573001112233")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = CrmLead(tenant_id=self.tenant_id, contact_id=contact.id, current_stage_id=stage.id)
            db.add(lead)
            db.commit()
            db.refresh(lead)
            self.lead_id = lead.id

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)

    def test_public_form_token_is_hashed(self):
        with SessionLocal() as db:
            service = FormService(db)
            form = service.ensure_default_form(self.tenant_id)
            token_row, link = service.create_token(self.tenant_id, form.id, self.lead_id, 7)

        self.assertNotIn(token_row.token_hash, link)
        self.assertEqual(len(token_row.token_hash), 64)

    def test_public_form_token_generates_link_without_pii(self):
        with SessionLocal() as db:
            service = FormService(db)
            form = service.ensure_default_form(self.tenant_id)
            _, link = service.create_token(self.tenant_id, form.id, self.lead_id, 7)

        self.assertNotIn(self.lead_id, link)
        self.assertNotIn("juan@example.com", link)
        self.assertNotIn("3001112233", link)

    def test_public_form_can_be_loaded_with_valid_token(self):
        with SessionLocal() as db:
            service = FormService(db)
            form = service.ensure_default_form(self.tenant_id)
            _, link = service.create_token(self.tenant_id, form.id, self.lead_id, 7)
            token = link.rsplit("/", 1)[-1]
            _, loaded_form = service.load_public_form(token)

        self.assertEqual(loaded_form.id, form.id)

    def test_public_form_rejects_expired_token(self):
        with SessionLocal() as db:
            service = FormService(db)
            form = service.ensure_default_form(self.tenant_id)
            token_row, link = service.create_token(self.tenant_id, form.id, self.lead_id, 7)
            token_row.expires_at = datetime.now(UTC) - timedelta(days=1)
            db.commit()
            token = link.rsplit("/", 1)[-1]
            with self.assertRaises(ValueError):
                service.load_public_form(token)

    def test_public_form_submission_creates_crm_activity(self):
        with SessionLocal() as db:
            service = FormService(db)
            form = service.ensure_default_form(self.tenant_id)
            _, link = service.create_token(self.tenant_id, form.id, self.lead_id, 7)
            token = link.rsplit("/", 1)[-1]
            service.submit_public_form(token, {"nombre": "Juan", "necesidad_principal": "Demo"})
            count = db.scalar(select(func.count()).select_from(CrmActivity).where(CrmActivity.activity_type == "form_submitted"))

        self.assertIsNotNone(count)

    def test_cross_tenant_forms_are_rejected(self):
        with SessionLocal() as db:
            other = Tenant(name="Tenant B", slug="tenant-b")
            db.add(other)
            db.commit()
            db.refresh(other)
            form = FormService(db).ensure_default_form(self.tenant_id)
            with self.assertRaises(ValueError):
                FormService(db).get_form(other.id, form.id)


if __name__ == "__main__":
    unittest.main()
