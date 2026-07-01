from __future__ import annotations

import os
from pathlib import Path
import unittest

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_integrations_2a_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.crm import CrmCallContext, CrmContact, CrmLead, CrmPipelineStage
from app.models.identity import Tenant, TenantMembership, User
from app.schemas.integrations import BookingConfigRequest
from app.services.booking_config_service import BookingConfigService


class Integration2ATestCase(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        app.dependency_overrides.clear()
        self.client = TestClient(app)
        self.tenant, self.user = self._seed_tenant_user()
        app.dependency_overrides[get_current_auth_context] = self._auth_context_override

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def _seed_tenant_user(self, *, slug: str = "tenant-a", email: str = "admin@example.com"):
        with SessionLocal() as db:
            tenant = Tenant(name=slug.title(), slug=slug)
            user = User(email=email, name="Admin", status="active", is_internal=True)
            db.add_all([tenant, user])
            db.commit()
            db.refresh(tenant)
            db.refresh(user)
            membership = TenantMembership(
                tenant_id=tenant.id,
                user_id=user.id,
                role="tenant_admin",
                status="active",
            )
            db.add(membership)
            db.commit()
            return tenant, user

    async def _auth_context_override(self):
        with SessionLocal() as db:
            tenant = db.get(Tenant, self.tenant.id)
            user = db.get(User, self.user.id)
            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant.id,
                    TenantMembership.user_id == user.id,
                )
            )
            return AuthContext(user=user, tenant=tenant, membership=membership)

    def configure_calcom(self, *, tenant_id: str | None = None, calendar_mode: str = "cal_managed"):
        with SessionLocal() as db:
            return BookingConfigService(db).upsert_calcom_config(
                tenant_id or self.tenant.id,
                BookingConfigRequest(
                    status="active",
                    calendar_mode=calendar_mode,
                    cal_api_key="cal_secret_test",
                    default_event_type_id=123,
                    default_timezone="America/Bogota",
                    default_language="es",
                    default_length_minutes=30,
                ),
            )

    def seed_lead(self, *, tenant_id: str | None = None, email: str | None = "lead@example.com", context_id: str | None = None):
        tenant_id = tenant_id or self.tenant.id
        with SessionLocal() as db:
            stage = CrmPipelineStage(tenant_id=tenant_id, key="new", name="Nuevo", position=1, is_default=True)
            contact = CrmContact(tenant_id=tenant_id, name="Pedro Gomez", email=email, phone="+573001112233")
            db.add_all([stage, contact])
            db.commit()
            db.refresh(stage)
            db.refresh(contact)
            lead = CrmLead(
                tenant_id=tenant_id,
                contact_id=contact.id,
                current_stage_id=stage.id,
                status="open",
                context_id=context_id,
            )
            db.add(lead)
            db.commit()
            db.refresh(lead)
            return lead.id, contact.id

    def seed_call_context(self, *, tenant_id: str | None = None, context_id: str = "ctx-voice"):
        tenant_id = tenant_id or self.tenant.id
        with SessionLocal() as db:
            context = CrmCallContext(
                tenant_id=tenant_id,
                external_provider="ultravox",
                external_call_id="call-1",
                context_id=context_id,
                email="lead@example.com",
                name="Pedro Gomez",
            )
            db.add(context)
            db.commit()
            db.refresh(context)
            return context.id
