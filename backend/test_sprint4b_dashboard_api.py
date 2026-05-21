import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import unittest

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
TEST_DB_PATH = Path("serviai_sprint4b_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")

from fastapi.testclient import TestClient

from app.api.auth.deps import get_current_identity
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.analytics import Agent, Call
from app.models.identity import Tenant, TenantMembership, User
from app.services.auth0_service import AuthenticatedIdentity


class Sprint4BDashboardApiTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        app.dependency_overrides.clear()
        self.client = TestClient(app)
        self.tenant_id, self.agent_id = self.seed_dashboard_data()
        self.override_identity()

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def override_identity(self):
        async def _identity_override():
            return AuthenticatedIdentity(
                external_auth_id="auth0|dashboard-user",
                email="dashboard@example.com",
                name="Dashboard User",
                claims={"sub": "auth0|dashboard-user", "email": "dashboard@example.com"},
            )

        app.dependency_overrides[get_current_identity] = _identity_override

    def seed_dashboard_data(self) -> tuple[str, str]:
        with SessionLocal() as db:
            tenant = Tenant(name="Empresa Demo", slug="empresa-demo", timezone="America/Bogota")
            other_tenant = Tenant(name="Otro Tenant", slug="otro-tenant", timezone="America/Bogota")
            user = User(
                external_auth_id="auth0|dashboard-user",
                email="dashboard@example.com",
                name="Dashboard User",
                status="active",
            )
            db.add_all([tenant, other_tenant, user])
            db.commit()
            db.refresh(tenant)
            db.refresh(other_tenant)
            db.refresh(user)

            db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role="tenant_analyst"))
            agent = Agent(tenant_id=tenant.id, name="Agente Ventas", external_provider="ultravox")
            other_agent = Agent(tenant_id=other_tenant.id, name="Agente Otro")
            db.add_all([agent, other_agent])
            db.commit()
            db.refresh(agent)
            db.refresh(other_agent)

            calls = [
                Call(
                    tenant_id=tenant.id,
                    external_provider="ultravox",
                    external_call_id="call-answered-1",
                    agent_id=agent.id,
                    normalized_status="answered",
                    started_at=datetime(2026, 5, 2, 14, 0, tzinfo=UTC),
                    duration_seconds=120,
                    billed_minutes=Decimal("2.00"),
                    summary="Cliente solicito una demo.",
                    short_summary="Demo solicitada",
                ),
                Call(
                    tenant_id=tenant.id,
                    external_provider="ultravox",
                    external_call_id="call-unanswered-1",
                    agent_id=None,
                    normalized_status="unanswered",
                    started_at=datetime(2026, 5, 2, 15, 0, tzinfo=UTC),
                    duration_seconds=None,
                    billed_minutes=Decimal("0.00"),
                    summary=None,
                    short_summary=None,
                ),
                Call(
                    tenant_id=tenant.id,
                    external_provider="ultravox",
                    external_call_id="call-active-1",
                    agent_id=agent.id,
                    normalized_status="in_progress",
                    started_at=datetime(2026, 5, 3, 16, 0, tzinfo=UTC),
                    duration_seconds=30,
                    billed_minutes=Decimal("1.00"),
                ),
                Call(
                    tenant_id=tenant.id,
                    external_provider="ultravox",
                    external_call_id="call-failed-1",
                    agent_id=None,
                    normalized_status="failed",
                    started_at=datetime(2026, 5, 4, 17, 0, tzinfo=UTC),
                    duration_seconds=10,
                    billed_minutes=Decimal("1.00"),
                ),
                Call(
                    tenant_id=tenant.id,
                    external_provider="ultravox",
                    external_call_id="call-voicemail-1",
                    agent_id=agent.id,
                    normalized_status="voicemail",
                    started_at=datetime(2026, 5, 5, 10, 0, tzinfo=UTC),
                    duration_seconds=223,
                    billed_minutes=Decimal("3.80"),
                    summary="La llamada fue atendida por un sistema de contestador automático.",
                    short_summary="Buzón de voz automático.",
                ),
                Call(
                    tenant_id=other_tenant.id,
                    external_provider="ultravox",
                    external_call_id="other-tenant-call",
                    agent_id=other_agent.id,
                    normalized_status="answered",
                    started_at=datetime(2026, 5, 2, 14, 0, tzinfo=UTC),
                    duration_seconds=999,
                    billed_minutes=Decimal("99.00"),
                ),
            ]
            db.add_all(calls)
            db.commit()
            return tenant.id, agent.id

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer test-token"}

    def test_dashboard_endpoints_require_authentication(self):
        app.dependency_overrides.clear()

        response = self.client.get("/api/v1/dashboard/kpis")

        self.assertEqual(response.status_code, 401)

    def test_kpis_are_calculated_from_tenant_calls(self):
        response = self.client.get("/api/v1/dashboard/kpis", headers=self.auth_headers())

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["calls_total"], 5)
        self.assertEqual(payload["calls_answered"], 1)
        self.assertEqual(payload["calls_unanswered"], 1)
        self.assertEqual(payload["active_calls"], 1)
        self.assertEqual(payload["answer_rate"], 25.0)
        self.assertEqual(payload["avg_duration_seconds"], 120.0)
        self.assertEqual(payload["total_duration_seconds"], 383)
        self.assertEqual(payload["billed_minutes"], 7.8)

    def test_voicemail_appears_in_status_distribution(self):
        response = self.client.get(
            "/api/v1/dashboard/status-distribution",
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        statuses = {item["key"]: item for item in response.json()["items"]}
        self.assertIn("voicemail", statuses)
        self.assertEqual(statuses["voicemail"]["calls"], 1)
        self.assertEqual(statuses["voicemail"]["label"], "Voicemail")
        self.assertEqual(statuses["voicemail"]["percentage"], 20.0)
        self.assertEqual(statuses["answered"]["calls"], 1)
        self.assertEqual(statuses["unanswered"]["calls"], 1)
        self.assertEqual(statuses["failed"]["calls"], 1)
        self.assertEqual(statuses["in_progress"]["calls"], 1)

    def test_trends_status_agent_heatmap_and_recent_calls_share_filters(self):
        params = {"from": "2026-05-02", "to": "2026-05-03", "agent_id": self.agent_id}

        trends = self.client.get("/api/v1/dashboard/trends", params=params, headers=self.auth_headers())
        status_distribution = self.client.get(
            "/api/v1/dashboard/status-distribution",
            params=params,
            headers=self.auth_headers(),
        )
        agent_distribution = self.client.get(
            "/api/v1/dashboard/agent-distribution",
            params={"from": "2026-05-02", "to": "2026-05-03"},
            headers=self.auth_headers(),
        )
        heatmap = self.client.get("/api/v1/dashboard/heatmap", params=params, headers=self.auth_headers())
        recent_calls = self.client.get(
            "/api/v1/dashboard/recent-calls",
            params={**params, "page": 1, "page_size": 10},
            headers=self.auth_headers(),
        )

        self.assertEqual(trends.status_code, 200)
        self.assertEqual(status_distribution.status_code, 200)
        self.assertEqual(agent_distribution.status_code, 200)
        self.assertEqual(heatmap.status_code, 200)
        self.assertEqual(recent_calls.status_code, 200)

        trend_series = trends.json()["series"]
        self.assertEqual(sum(item["calls_total"] for item in trend_series), 2)
        self.assertEqual(sum(item["calls_answered"] for item in trend_series), 1)

        statuses = {item["key"]: item["calls"] for item in status_distribution.json()["items"]}
        self.assertEqual(statuses, {"answered": 1, "in_progress": 1})

        agents = {item["agent_name"]: item["calls"] for item in agent_distribution.json()["items"]}
        self.assertEqual(agents["Agente Ventas"], 2)
        self.assertEqual(agents["Unassigned"], 1)

        matrix = heatmap.json()["matrix"]
        self.assertEqual(sum(item["calls"] for item in matrix), 2)
        self.assertTrue(all(0 <= item["hour"] <= 23 for item in matrix))

        recent_payload = recent_calls.json()
        self.assertEqual(recent_payload["total"], 2)
        self.assertEqual([item["status"] for item in recent_payload["items"]], ["in_progress", "answered"])

    def test_kpis_exclude_voicemail_from_answered_and_answer_rate(self):
        response = self.client.get("/api/v1/dashboard/kpis", headers=self.auth_headers())

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["calls_total"], 5)
        self.assertEqual(payload["calls_answered"], 1)
        self.assertEqual(payload["calls_unanswered"], 1)
        self.assertEqual(payload["answer_rate"], 25.0)
        eligible = 4  # total - in_progress = 5 - 1
        self.assertEqual(payload["answer_rate"], round((1 / eligible) * 100, 2))

    def test_status_filter_and_tenant_isolation_are_enforced(self):
        response = self.client.get(
            "/api/v1/dashboard/recent-calls",
            params={"status": "answered", "page": 1, "page_size": 20},
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["status"], "answered")
        self.assertEqual(payload["items"][0]["duration_seconds"], 120)

    def test_foreign_agent_filter_returns_no_tenant_data(self):
        with SessionLocal() as db:
            foreign_agent_id = db.query(Agent).filter(Agent.name == "Agente Otro").one().id

        response = self.client.get(
            "/api/v1/dashboard/kpis",
            params={"agent_id": foreign_agent_id},
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["calls_total"], 0)


if __name__ == "__main__":
    unittest.main()
