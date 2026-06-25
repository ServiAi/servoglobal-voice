import os
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import select

TEST_DB_PATH = Path("serviai_crm_dashboard_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.api.auth.deps import AuthContext, get_current_auth_context
from app.models.analytics import Agent, Call, CallEvent
from app.models.identity import Tenant, User, TenantMembership
from app.models.crm import CrmContact, CrmPipelineStage, CrmLead, CrmActivity, CrmTask
from app.services.crm_pipeline_service import CrmPipelineService
from app.services.crm_dashboard_metrics_service import CrmDashboardMetricsService


class CrmDashboardMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_DB_PATH.unlink(missing_ok=True)
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        with SessionLocal() as db:
            db.query(CrmTask).delete()
            db.query(CrmActivity).delete()
            db.query(CrmLead).delete()
            db.query(CrmPipelineStage).delete()
            db.query(CrmContact).delete()
            db.query(CallEvent).delete()
            db.query(Call).delete()
            db.query(Agent).delete()
            db.query(TenantMembership).delete()
            db.query(User).delete()
            db.query(Tenant).delete()
            db.commit()

        app.dependency_overrides.clear()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def seed_tenant_agent_user(self, slug="tenant-a", name="Tenant A", email="user@test.com") -> tuple[Tenant, Agent, User]:
        with SessionLocal() as db:
            tenant = Tenant(name=name, slug=slug, timezone="America/Bogota")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

            agent = Agent(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_agent_id=f"agent-{slug}",
                name="Agente Ventas IA",
            )
            db.add(agent)

            user = User(
                email=email,
                name=f"User {name}",
                status="active",
                external_auth_id=f"auth0|{slug}-user",
            )
            db.add(user)
            db.commit()
            db.refresh(agent)
            db.refresh(user)

            membership = TenantMembership(
                tenant_id=tenant.id,
                user_id=user.id,
                role="tenant_admin",
                status="active",
            )
            db.add(membership)
            db.commit()

            return tenant, agent, user

    def override_auth(self, user: User, tenant: Tenant):
        async def _auth_context_override():
            with SessionLocal() as db:
                membership = db.scalar(
                    select(TenantMembership).where(
                        TenantMembership.tenant_id == tenant.id,
                        TenantMembership.user_id == user.id,
                    )
                )
            return AuthContext(user=user, tenant=tenant, membership=membership)
        app.dependency_overrides[get_current_auth_context] = _auth_context_override

    def seed_lead(self, db, tenant_id, stage_id, name="Lead Test", **kwargs) -> CrmLead:
        contact = CrmContact(tenant_id=tenant_id, name=name)
        db.add(contact)
        db.commit()
        db.refresh(contact)

        lead = CrmLead(
            tenant_id=tenant_id,
            contact_id=contact.id,
            current_stage_id=stage_id,
            status="open",
            **kwargs,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead

    # 1. test_dashboard_empty_state_returns_zero
    def test_dashboard_empty_state_returns_zero(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        self.override_auth(user, tenant)

        response = self.client.get("/api/v1/crm/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # KPIs
        kpis = data["kpis"]
        self.assertEqual(kpis["total_leads"], 0)
        self.assertEqual(kpis["new_leads"], 0)
        self.assertEqual(kpis["contacted_leads"], 0)
        self.assertEqual(kpis["open_leads"], 0)

        # Conversion
        conv = data["conversion"]
        self.assertEqual(conv["contact_rate"], 0.0)
        self.assertEqual(conv["win_rate"], 0.0)

        # Funnel
        funnel = {item["stage"]: item["count"] for item in data["funnel"]}
        self.assertEqual(funnel["new"], 0)
        self.assertEqual(funnel["won"], 0)

        # Sources & Campaigns
        self.assertEqual(len(data["sources"]), 0)
        self.assertEqual(len(data["campaigns"]), 0)

        # Calls
        calls = data["calls"]
        self.assertEqual(calls["total_calls"], 0)
        self.assertEqual(calls["total_billed_minutes"], 0.0)

        # Pending Actions
        self.assertEqual(len(data["pending_actions"]), 0)

    # 2. test_dashboard_kpis_total_leads
    def test_dashboard_kpis_total_leads(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        self.override_auth(user, tenant)

        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stages = pipeline.ensure_default_pipeline(tenant.id)
            stage_map = {s.key: s for s in stages}

            self.seed_lead(db, tenant.id, stage_map["new"].id, name="Lead 1")
            self.seed_lead(db, tenant.id, stage_map["contacted"].id, name="Lead 2")

        response = self.client.get("/api/v1/crm/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["kpis"]["total_leads"], 2)

    # 3. test_dashboard_counts_by_stage
    def test_dashboard_counts_by_stage(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        self.override_auth(user, tenant)

        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stages = pipeline.ensure_default_pipeline(tenant.id)
            stage_map = {s.key: s for s in stages}

            self.seed_lead(db, tenant.id, stage_map["new"].id)
            self.seed_lead(db, tenant.id, stage_map["new"].id)
            self.seed_lead(db, tenant.id, stage_map["contacted"].id)

        response = self.client.get("/api/v1/crm/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        kpis = data["kpis"]
        self.assertEqual(kpis["new_leads"], 2)
        self.assertEqual(kpis["contacted_leads"], 1)

    # 4. test_dashboard_conversion_rates
    def test_dashboard_conversion_rates(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        self.override_auth(user, tenant)

        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stages = pipeline.ensure_default_pipeline(tenant.id)
            stage_map = {s.key: s for s in stages}

            # 4 total leads:
            # 1 new
            # 1 contacted
            # 1 scheduled
            # 1 won
            self.seed_lead(db, tenant.id, stage_map["new"].id)
            self.seed_lead(db, tenant.id, stage_map["contacted"].id)
            self.seed_lead(db, tenant.id, stage_map["scheduled"].id)
            self.seed_lead(db, tenant.id, stage_map["won"].id)

        response = self.client.get("/api/v1/crm/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        conv = data["conversion"]
        # contacted_cum = contacted (1) + scheduled (1) + won (1) = 3
        # total = 4
        # contact_rate = 3 / 4 * 100 = 75.0%
        self.assertEqual(conv["contact_rate"], 75.0)

        # connected_cum = scheduled (1) + won (1) = 2
        # connection_rate = 2 / 3 * 100 = 66.67%
        self.assertEqual(conv["connection_rate"], 66.67)

        # won_cum = 1
        # scheduled_cum = scheduled (1) + won (1) = 2
        # win_rate = 1 / 2 * 100 = 50.0%
        self.assertEqual(conv["win_rate"], 50.0)

    # 5. test_dashboard_filters_by_date_range
    def test_dashboard_filters_by_date_range(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        self.override_auth(user, tenant)

        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stages = pipeline.ensure_default_pipeline(tenant.id)
            stage_map = {s.key: s for s in stages}

            # 1 lead created 5 days ago
            lead_old = self.seed_lead(db, tenant.id, stage_map["new"].id)
            lead_old.created_at = datetime.now(UTC) - timedelta(days=5)
            db.add(lead_old)

            # 1 lead created today
            self.seed_lead(db, tenant.id, stage_map["new"].id)
            db.commit()

        # range=today
        response = self.client.get("/api/v1/crm/dashboard?range=today")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kpis"]["total_leads"], 1)

        # range=7d
        response = self.client.get("/api/v1/crm/dashboard?range=7d")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kpis"]["total_leads"], 2)

    # 6. test_dashboard_filters_by_source
    def test_dashboard_filters_by_source(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        self.override_auth(user, tenant)

        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stages = pipeline.ensure_default_pipeline(tenant.id)
            stage_map = {s.key: s for s in stages}

            self.seed_lead(db, tenant.id, stage_map["new"].id, source="facebook")
            self.seed_lead(db, tenant.id, stage_map["new"].id, source="landing")
            db.commit()

        response = self.client.get("/api/v1/crm/dashboard?source=facebook")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kpis"]["total_leads"], 1)

    # 7. test_dashboard_filters_by_campaign
    def test_dashboard_filters_by_campaign(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        self.override_auth(user, tenant)

        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stages = pipeline.ensure_default_pipeline(tenant.id)
            stage_map = {s.key: s for s in stages}

            self.seed_lead(db, tenant.id, stage_map["new"].id, campaign="black-friday")
            self.seed_lead(db, tenant.id, stage_map["new"].id, campaign="cyber-monday")
            db.commit()

        response = self.client.get("/api/v1/crm/dashboard?campaign=black-friday")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kpis"]["total_leads"], 1)

    # 8. test_dashboard_pending_actions
    def test_dashboard_pending_actions(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        self.override_auth(user, tenant)

        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stages = pipeline.ensure_default_pipeline(tenant.id)
            stage_map = {s.key: s for s in stages}

            # Lead 1: stage=follow_up
            self.seed_lead(db, tenant.id, stage_map["follow_up"].id, name="FollowUp Lead")

            # Lead 2: has next_action
            self.seed_lead(db, tenant.id, stage_map["new"].id, name="Action Lead", next_action="llamar mañana")

            # Lead 3: stage=contacted and no call
            self.seed_lead(db, tenant.id, stage_map["contacted"].id, name="ContactedNoCall Lead")

            # Lead 4: regular new lead (should NOT be in pending actions)
            self.seed_lead(db, tenant.id, stage_map["new"].id, name="Regular Lead")

        response = self.client.get("/api/v1/crm/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        actions = data["pending_actions"]
        self.assertEqual(len(actions), 3)
        names = {a["contact_name"] for a in actions}
        self.assertIn("FollowUp Lead", names)
        self.assertIn("Action Lead", names)
        self.assertIn("ContactedNoCall Lead", names)
        self.assertNotIn("Regular Lead", names)

    # 9. test_dashboard_does_not_cross_tenant_data
    def test_dashboard_does_not_cross_tenant_data(self):
        tenant_a, agent_a, user_a = self.seed_tenant_agent_user(slug="tenant-a", name="Tenant A", email="user-a@test.com")
        tenant_b, agent_b, user_b = self.seed_tenant_agent_user(slug="tenant-b", name="Tenant B", email="user-b@test.com")

        with SessionLocal() as db:
            pipeline_a = CrmPipelineService(db)
            stages_a = pipeline_a.ensure_default_pipeline(tenant_a.id)
            stage_map_a = {s.key: s for s in stages_a}

            pipeline_b = CrmPipelineService(db)
            stages_b = pipeline_b.ensure_default_pipeline(tenant_b.id)
            stage_map_b = {s.key: s for s in stages_b}

            # Lead in tenant A
            self.seed_lead(db, tenant_a.id, stage_map_a["new"].id, name="Lead A")
            # Lead in tenant B
            self.seed_lead(db, tenant_b.id, stage_map_b["new"].id, name="Lead B")

        # Query A
        self.override_auth(user_a, tenant_a)
        response = self.client.get("/api/v1/crm/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["kpis"]["total_leads"], 1)

        # Query B
        self.override_auth(user_b, tenant_b)
        response = self.client.get("/api/v1/crm/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["kpis"]["total_leads"], 1)

    # 10. test_dashboard_call_metrics
    def test_dashboard_call_metrics(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        self.override_auth(user, tenant)

        with SessionLocal() as db:
            call1 = Call(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_call_id="call-1",
                normalized_status="answered",
                started_at=datetime.now(UTC),
                duration_seconds=120,
                billed_minutes=Decimal("2.0")
            )
            call2 = Call(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_call_id="call-2",
                normalized_status="unanswered",
                started_at=datetime.now(UTC),
                duration_seconds=None,
                billed_minutes=Decimal("0.0")
            )
            db.add(call1)
            db.add(call2)
            db.commit()

        response = self.client.get("/api/v1/crm/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        calls = data["calls"]
        self.assertEqual(calls["total_calls"], 2)
        self.assertEqual(calls["answered_calls"], 1)
        self.assertEqual(calls["unanswered_calls"], 1)
        self.assertEqual(calls["average_duration_seconds"], 120.0)
        self.assertEqual(calls["total_billed_minutes"], 2.0)

    # 11. test_dashboard_denominator_zero_returns_zero
    def test_dashboard_denominator_zero_returns_zero(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        self.override_auth(user, tenant)

        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stages = pipeline.ensure_default_pipeline(tenant.id)
            stage_map = {s.key: s for s in stages}

            # 1 lead in stage new (so contacted_cum = 0, connected_cum = 0, etc.)
            self.seed_lead(db, tenant.id, stage_map["new"].id)

        response = self.client.get("/api/v1/crm/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        conv = data["conversion"]
        self.assertEqual(conv["contact_rate"], 0.0)
        self.assertEqual(conv["connection_rate"], 0.0)
        self.assertEqual(conv["qualification_rate"], 0.0)
        self.assertEqual(conv["schedule_rate"], 0.0)
        self.assertEqual(conv["win_rate"], 0.0)
