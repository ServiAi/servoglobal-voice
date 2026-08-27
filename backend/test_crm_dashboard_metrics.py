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
from app.models.crm import CrmContact, CrmPipelineStage, CrmLead, CrmActivity, CrmTask, CrmVoiceCall
from app.models.integrations import TenantIntegrationEvent, TenantSipRoute, TenantVoiceProviderConfig
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
            db.query(TenantIntegrationEvent).delete()
            db.query(CrmVoiceCall).delete()
            db.query(TenantSipRoute).delete()
            db.query(TenantVoiceProviderConfig).delete()
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

    def test_dashboard_voice_capacity_without_route_returns_zeros(self):
        tenant, _agent, user = self.seed_tenant_agent_user()
        self.override_auth(user, tenant)

        response = self.client.get("/api/v1/crm/dashboard")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["voice_capacity"],
            {
                "configured": False,
                "route_status": None,
                "provision_status": None,
                "active_calls": 0,
                "max_concurrent_calls": 0,
                "available_slots": 0,
                "utilization_percent": 0.0,
                "capacity_rejections": 0,
                "reconciled_calls": 0,
                "forced_releases": 0,
                "recent_events": [],
            },
        )

    def test_dashboard_voice_capacity_is_current_period_scoped_and_tenant_isolated(self):
        tenant_a, _agent_a, user_a = self.seed_tenant_agent_user(
            slug="tenant-a", name="Tenant A", email="capacity-a@test.com"
        )
        tenant_b, _agent_b, _user_b = self.seed_tenant_agent_user(
            slug="tenant-b", name="Tenant B", email="capacity-b@test.com"
        )
        self.override_auth(user_a, tenant_a)
        now = datetime.now(UTC)

        with SessionLocal() as db:
            provider_a = TenantVoiceProviderConfig(
                tenant_id=tenant_a.id, provider="ultravox", status="active"
            )
            provider_b = TenantVoiceProviderConfig(
                tenant_id=tenant_b.id, provider="ultravox", status="active"
            )
            db.add_all([provider_a, provider_b])
            db.flush()
            route_a = TenantSipRoute(
                tenant_id=tenant_a.id,
                provider_config_id=provider_a.id,
                status="active",
                provision_status="active",
                pbx_host="pbx-a.example.com",
                sip_username="capacity-a",
                caller_id="+573001110000",
                max_concurrent_calls=3,
            )
            route_b = TenantSipRoute(
                tenant_id=tenant_b.id,
                provider_config_id=provider_b.id,
                status="active",
                provision_status="active",
                pbx_host="pbx-b.example.com",
                sip_username="capacity-b",
                caller_id="+573001110001",
                max_concurrent_calls=1,
            )
            db.add_all([route_a, route_b])
            db.flush()
            db.add_all(
                [
                    CrmVoiceCall(tenant_id=tenant_a.id, sip_route_id=route_a.id, provider="ultravox", direction="outbound", status="queued"),
                    CrmVoiceCall(tenant_id=tenant_a.id, sip_route_id=route_a.id, provider="ultravox", direction="outbound", status="in_progress"),
                    CrmVoiceCall(tenant_id=tenant_a.id, sip_route_id=route_a.id, provider="ultravox", direction="outbound", status="completed"),
                    CrmVoiceCall(tenant_id=tenant_b.id, sip_route_id=route_b.id, provider="ultravox", direction="outbound", status="queued"),
                ]
            )
            for index in range(12):
                event_type = "voice_capacity_reached" if index < 8 else "voice_callback_reconciled"
                db.add(
                    TenantIntegrationEvent(
                        tenant_id=tenant_a.id,
                        provider="ultravox",
                        event_type=event_type,
                        status="blocked" if index < 8 else "success",
                        metadata_json={"active_calls": 3, "max_concurrent_calls": 3},
                        created_at=now - timedelta(minutes=index),
                    )
                )
            db.add(
                TenantIntegrationEvent(
                    tenant_id=tenant_a.id,
                    provider="ultravox",
                    event_type="voice_callback_forced_release",
                    status="success",
                    metadata_json={"resulting_status": "failed"},
                    created_at=now - timedelta(days=40),
                )
            )
            db.add(
                TenantIntegrationEvent(
                    tenant_id=tenant_b.id,
                    provider="ultravox",
                    event_type="voice_capacity_reached",
                    status="blocked",
                    metadata_json={"active_calls": 1, "max_concurrent_calls": 1},
                    created_at=now,
                )
            )
            db.commit()

        response = self.client.get(
            "/api/v1/crm/dashboard?range=30d&source=ignored&campaign=ignored"
        )
        self.assertEqual(response.status_code, 200, response.text)
        capacity = response.json()["voice_capacity"]
        self.assertTrue(capacity["configured"])
        self.assertEqual(capacity["active_calls"], 2)
        self.assertEqual(capacity["max_concurrent_calls"], 3)
        self.assertEqual(capacity["available_slots"], 1)
        self.assertEqual(capacity["utilization_percent"], 66.7)
        self.assertEqual(capacity["capacity_rejections"], 8)
        self.assertEqual(capacity["reconciled_calls"], 4)
        self.assertEqual(capacity["forced_releases"], 0)
        self.assertEqual(len(capacity["recent_events"]), 10)
        occurred = [item["occurred_at"] for item in capacity["recent_events"]]
        self.assertEqual(occurred, sorted(occurred, reverse=True))

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
