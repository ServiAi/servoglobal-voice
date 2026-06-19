import os
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import select

TEST_DB_PATH = Path("serviai_crm_sprint2_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.api.auth.deps import AuthContext, get_current_auth_context
from app.models.analytics import Agent, Call, CallEvent
from app.models.identity import Tenant, User, TenantMembership
from app.models.crm import CrmContact, CrmPipelineStage, CrmLead, CrmActivity, CrmTask
from app.services.crm_pipeline_service import CrmPipelineService
from app.services.crm_contact_service import CrmContactService
from app.services.crm_lead_service import CrmLeadService
from app.services.crm_activity_service import CrmActivityService
from app.services.crm_task_service import CrmTaskService
from app.services.crm_metrics_service import CrmMetricsService
from app.services.crm_query_service import CrmQueryService


class CrmSprint2Tests(unittest.TestCase):
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

    def seed_tenant_agent_user(self) -> tuple[Tenant, Agent, User]:
        with SessionLocal() as db:
            tenant = Tenant(name="Empresa Test A", slug="empresa-test-a")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

            agent = Agent(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_agent_id="agent-test-1",
                name="Agente Ventas IA",
            )
            db.add(agent)

            user = User(
                email="user@test.com",
                name="Test User A",
                status="active",
                external_auth_id="auth0|user-a",
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

    def seed_lead(self, db, tenant_id, stage_id, contact=None, **kwargs) -> CrmLead:
        if contact is None:
            contact = CrmContact(tenant_id=tenant_id, name="Lead Test")
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

    # === Listado y filtros ===

    def test_crm_leads_filter_by_stage(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stages = pipeline.ensure_default_pipeline(tenant.id)
            stage_map = {s.key: s for s in stages}
            contact = CrmContact(tenant_id=tenant.id, name="Lead A")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant.id, stage_map["new"].id, contact=contact)
            # Another lead in different stage
            contact2 = CrmContact(tenant_id=tenant.id, name="Lead B")
            db.add(contact2)
            db.commit()
            db.refresh(contact2)
            lead2 = self.seed_lead(db, tenant.id, stage_map["qualified"].id, contact=contact2)

        self.override_auth(user, tenant)
        response = self.client.get(f"/api/v1/crm/leads?stage_key=new")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["lead_id"], lead.id)
        self.assertEqual(data["items"][0]["stage_key"], "new")

    def test_crm_leads_search_by_contact_name(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Carlos Pérez")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant.id, stage.id, contact=contact)

        self.override_auth(user, tenant)
        response = self.client.get("/api/v1/crm/leads?search=Carlos")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["contact_name"], "Carlos Pérez")

    def test_crm_leads_search_by_phone(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Phone Lead", phone="+573001112233")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant.id, stage.id, contact=contact)

        self.override_auth(user, tenant)
        response = self.client.get("/api/v1/crm/leads?search=3001112233")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(data["total"], 1)

    def test_crm_leads_pagination(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            for i in range(5):
                contact = CrmContact(tenant_id=tenant.id, name=f"Paginated Lead {i}")
                db.add(contact)
                db.commit()
                db.refresh(contact)
                self.seed_lead(db, tenant.id, stage.id, contact=contact)

        self.override_auth(user, tenant)
        response = self.client.get("/api/v1/crm/leads?page=1&page_size=2")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["total_pages"], 3)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 2)

    def test_crm_leads_sorting_allowed_fields(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            for i in range(3):
                contact = CrmContact(tenant_id=tenant.id, name=f"Sort Lead {i}")
                db.add(contact)
                db.commit()
                db.refresh(contact)
                self.seed_lead(db, tenant.id, stage.id, contact=contact)

        self.override_auth(user, tenant)
        # Sort by created_at asc
        response = self.client.get("/api/v1/crm/leads?sort_by=created_at&sort_order=asc")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["items"]), 3)

    # === Detalle ===

    def test_crm_lead_detail_includes_activities_and_tasks(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Detail Lead")
            db.add(contact)
            db.commit()
            db.refresh(contact)

            lead = self.seed_lead(db, tenant.id, stage.id, contact=contact)

            activity_service = CrmActivityService(db)
            activity_service.create_activity(
                tenant_id=tenant.id, lead_id=lead.id, contact_id=contact.id,
                activity_type="note", title="Test note",
            )

            task_service = CrmTaskService(db)
            task_service.create_task(
                tenant_id=tenant.id, lead_id=lead.id, title="Test task",
            )

        self.override_auth(user, tenant)
        response = self.client.get(f"/api/v1/crm/leads/{lead.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], lead.id)
        self.assertIn("activities", data)
        self.assertIn("tasks", data)
        self.assertGreaterEqual(len(data["activities"]), 1)
        self.assertGreaterEqual(len(data["tasks"]), 1)

    def test_crm_lead_detail_cross_tenant_returns_404(self):
        tenant_a, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            tenant_b = Tenant(name="Empresa B", slug="empresa-b")
            db.add(tenant_b)
            db.commit()
            db.refresh(tenant_b)

            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant_b.id, "new")
            contact = CrmContact(tenant_id=tenant_b.id, name="Cross Tenant")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant_b.id, stage.id, contact=contact)

        self.override_auth(user, tenant_a)
        response = self.client.get(f"/api/v1/crm/leads/{lead.id}")
        self.assertEqual(response.status_code, 404)

    # === Actualización lead ===

    def test_crm_update_lead_allowed_fields(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Update Lead")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant.id, stage.id, contact=contact)

        self.override_auth(user, tenant)
        response = self.client.patch(
            f"/api/v1/crm/leads/{lead.id}",
            json={"interest": "Alto", "use_case": "Ventas", "industry": "Real Estate"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["interest"], "Alto")
        self.assertEqual(data["use_case"], "Ventas")

        # Verify activity was created
        response_detail = self.client.get(f"/api/v1/crm/leads/{lead.id}")
        activities = response_detail.json()["activities"]
        types = [a["activity_type"] for a in activities]
        self.assertIn("lead_updated", types)

    def test_crm_update_lead_rejects_invalid_score(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Score Lead")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant.id, stage.id, contact=contact)

        self.override_auth(user, tenant)
        response = self.client.patch(
            f"/api/v1/crm/leads/{lead.id}",
            json={"lead_score": 150},
        )
        self.assertEqual(response.status_code, 422)

    def test_crm_update_lead_creates_activity(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Activity Lead")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant.id, stage.id, contact=contact)

        self.override_auth(user, tenant)
        response = self.client.patch(
            f"/api/v1/crm/leads/{lead.id}",
            json={"status": "paused"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "paused")

    # === Cambio de etapa ===

    def test_crm_manual_stage_change(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            _ = pipeline.ensure_default_pipeline(tenant.id)
            stage_new = pipeline.get_stage_by_key(tenant.id, "new")
            stage_qualified = pipeline.get_stage_by_key(tenant.id, "qualified")
            contact = CrmContact(tenant_id=tenant.id, name="Stage Change Lead")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant.id, stage_new.id, contact=contact)

        self.override_auth(user, tenant)
        response = self.client.patch(
            f"/api/v1/crm/leads/{lead.id}/stage",
            json={"stage_key": "qualified", "reason": "Cliente solicitó propuesta"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["stage"]["key"], "qualified")

    def test_crm_manual_stage_change_creates_stage_history(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            _ = pipeline.ensure_default_pipeline(tenant.id)
            stage_new = pipeline.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Stage History Lead")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant.id, stage_new.id, contact=contact)

        self.override_auth(user, tenant)
        response = self.client.patch(
            f"/api/v1/crm/leads/{lead.id}/stage",
            json={"stage_key": "qualified"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should have at least one stage_changed activity
        activities = data["activities"]
        stage_changes = [a for a in activities if a["activity_type"] == "stage_changed"]
        self.assertGreaterEqual(len(stage_changes), 1)

    def test_crm_manual_stage_change_cross_tenant_404(self):
        tenant_a, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            tenant_b = Tenant(name="Empresa B", slug="empresa-b")
            db.add(tenant_b)
            db.commit()
            db.refresh(tenant_b)
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant_b.id, "new")
            contact = CrmContact(tenant_id=tenant_b.id, name="Cross Stage")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant_b.id, stage.id, contact=contact)

        self.override_auth(user, tenant_a)
        response = self.client.patch(
            f"/api/v1/crm/leads/{lead.id}/stage",
            json={"stage_key": "qualified"},
        )
        self.assertEqual(response.status_code, 404)

    # === Pipeline board ===

    def test_crm_pipeline_board_groups_leads_by_stage(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stages = pipeline.ensure_default_pipeline(tenant.id)
            stage_map = {s.key: s for s in stages}

            contact1 = CrmContact(tenant_id=tenant.id, name="Board Lead 1")
            db.add(contact1)
            db.commit()
            db.refresh(contact1)
            self.seed_lead(db, tenant.id, stage_map["new"].id, contact=contact1)

            contact2 = CrmContact(tenant_id=tenant.id, name="Board Lead 2")
            db.add(contact2)
            db.commit()
            db.refresh(contact2)
            self.seed_lead(db, tenant.id, stage_map["qualified"].id, contact=contact2)

        self.override_auth(user, tenant)
        response = self.client.get("/api/v1/crm/pipeline/board")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("stages", data)

        stages = data["stages"]
        stage_keys = {s["key"]: s for s in stages}
        self.assertIn("new", stage_keys)
        self.assertIn("qualified", stage_keys)
        self.assertGreaterEqual(stage_keys["new"]["count"], 1)
        self.assertGreaterEqual(stage_keys["qualified"]["count"], 1)

    def test_crm_pipeline_board_respects_limit_per_stage(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            for i in range(5):
                contact = CrmContact(tenant_id=tenant.id, name=f"Limit Lead {i}")
                db.add(contact)
                db.commit()
                db.refresh(contact)
                self.seed_lead(db, tenant.id, stage.id, contact=contact)

        self.override_auth(user, tenant)
        response = self.client.get("/api/v1/crm/pipeline/board?limit_per_stage=2")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        new_stage = [s for s in data["stages"] if s["key"] == "new"][0]
        self.assertLessEqual(len(new_stage["leads"]), 2)

    # === Actividades ===

    def test_crm_activities_filter_by_type(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Activity Filter")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant.id, stage.id, contact=contact)

            activity_service = CrmActivityService(db)
            activity_service.create_activity(
                tenant_id=tenant.id, lead_id=lead.id, contact_id=contact.id,
                activity_type="note", title="Nota",
            )
            activity_service.create_activity(
                tenant_id=tenant.id, lead_id=lead.id, contact_id=contact.id,
                activity_type="call_started", title="Llamada",
            )

        self.override_auth(user, tenant)
        response = self.client.get("/api/v1/crm/activities?activity_type=note")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(len(data), 1)
        for a in data:
            self.assertEqual(a["activity_type"], "note")

    def test_crm_activities_do_not_expose_payload_json(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Payload Sanitize")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant.id, stage.id, contact=contact)

            activity = CrmActivity(
                tenant_id=tenant.id, lead_id=lead.id, contact_id=contact.id,
                activity_type="note", title="Sanitized",
                payload_json={"event": "test", "call": {"summary": "test"}},
            )
            db.add(activity)
            db.commit()

        self.override_auth(user, tenant)
        response = self.client.get("/api/v1/crm/activities")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        for a in data:
            self.assertNotIn("payload_json", a)
            self.assertNotIn("systemPrompt", a)
            self.assertNotIn("callbacks", a)

    # === Notas ===

    def test_crm_create_note(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Note Lead")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant.id, stage.id, contact=contact)

        self.override_auth(user, tenant)
        response = self.client.post(
            f"/api/v1/crm/leads/{lead.id}/notes",
            json={"note": "Cliente pidió seguimiento el viernes."},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Verify note activity was added
        activities = data["activities"]
        notes = [a for a in activities if a["activity_type"] == "note"]
        self.assertGreaterEqual(len(notes), 1)
        self.assertEqual(notes[0]["title"], "Nota interna")

    def test_crm_create_empty_note_rejected(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Empty Note")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant.id, stage.id, contact=contact)

        self.override_auth(user, tenant)
        response = self.client.post(
            f"/api/v1/crm/leads/{lead.id}/notes",
            json={"note": ""},
        )
        self.assertEqual(response.status_code, 422)

    # === Tareas ===

    def test_crm_create_task(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Task Lead")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant.id, stage.id, contact=contact)

        self.override_auth(user, tenant)
        response = self.client.post(
            "/api/v1/crm/tasks",
            json={
                "lead_id": lead.id,
                "title": "Llamar al cliente",
                "priority": "high",
            },
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Llamar al cliente")
        self.assertEqual(data["priority"], "high")
        self.assertEqual(data["status"], "pending")

    def test_crm_update_task_status_done(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            task_service = CrmTaskService(db)
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Task Done")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            lead = self.seed_lead(db, tenant.id, stage.id, contact=contact)

            task = task_service.create_task(
                tenant_id=tenant.id, lead_id=lead.id, title="Complete me",
            )

        self.override_auth(user, tenant)
        response = self.client.patch(
            f"/api/v1/crm/tasks/{task.id}",
            json={"status": "done"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "done")

    def test_crm_task_cross_tenant_404(self):
        tenant_a, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            tenant_b = Tenant(name="Empresa B", slug="empresa-b")
            db.add(tenant_b)
            db.commit()
            db.refresh(tenant_b)

            task = CrmTask(tenant_id=tenant_b.id, title="Cross task")
            db.add(task)
            db.commit()
            db.refresh(task)

        self.override_auth(user, tenant_a)
        response = self.client.patch(
            f"/api/v1/crm/tasks/{task.id}",
            json={"title": "Hacked"},
        )
        self.assertEqual(response.status_code, 404)

    def test_crm_task_assignee_must_belong_to_tenant(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            # Create user from another tenant
            other_user = User(
                email="other@test.com", name="Other", status="active",
                external_auth_id="auth0|other",
            )
            db.add(other_user)
            db.commit()
            db.refresh(other_user)

        self.override_auth(user, tenant)
        response = self.client.post(
            "/api/v1/crm/tasks",
            json={
                "title": "Invalid assignee",
                "assigned_to_user_id": other_user.id,
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_crm_delete_task(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            task = CrmTask(tenant_id=tenant.id, title="Delete me")
            db.add(task)
            db.commit()
            db.refresh(task)
            task_id = task.id

        self.override_auth(user, tenant)
        response = self.client.delete(f"/api/v1/crm/tasks/{task_id}")
        self.assertEqual(response.status_code, 204)

        # Verify it's gone
        response = self.client.get("/api/v1/crm/tasks")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        ids = [t["id"] for t in data]
        self.assertNotIn(task_id, ids)

    # === Métricas ===

    def test_crm_metrics_counts(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stages = pipeline.ensure_default_pipeline(tenant.id)
            stage_map = {s.key: s for s in stages}

            for i in range(3):
                contact = CrmContact(tenant_id=tenant.id, name=f"Metric Lead {i}")
                db.add(contact)
                db.commit()
                db.refresh(contact)

            # Create leads in various statuses
            contact1 = CrmContact(tenant_id=tenant.id, name="Won Lead")
            db.add(contact1)
            db.commit()
            db.refresh(contact1)
            lead_won = CrmLead(
                tenant_id=tenant.id, contact_id=contact1.id,
                current_stage_id=stage_map["won"].id, status="won",
            )
            db.add(lead_won)

            contact2 = CrmContact(tenant_id=tenant.id, name="Lost Lead")
            db.add(contact2)
            db.commit()
            db.refresh(contact2)
            lead_lost = CrmLead(
                tenant_id=tenant.id, contact_id=contact2.id,
                current_stage_id=stage_map["lost"].id, status="lost",
            )
            db.add(lead_lost)
            db.commit()

        # Create some tasks
        with SessionLocal() as db:
            task = CrmTask(tenant_id=tenant.id, title="Pending task")
            db.add(task)
            db.commit()

        self.override_auth(user, tenant)
        response = self.client.get("/api/v1/crm/metrics")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_leads", data)
        self.assertIn("total_contacts", data)
        self.assertIn("open_leads", data)
        self.assertIn("won_leads", data)
        self.assertIn("lost_leads", data)

    def test_crm_metrics_conversion_rate(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stages = pipeline.ensure_default_pipeline(tenant.id)
            stage_map = {s.key: s for s in stages}

            # 2 won, 2 lost, 1 open = 5 total
            for i in range(2):
                c = CrmContact(tenant_id=tenant.id, name=f"Won {i}")
                db.add(c)
                db.commit()
                db.refresh(c)
                lead = CrmLead(tenant_id=tenant.id, contact_id=c.id,
                               current_stage_id=stage_map["won"].id, status="won")
                db.add(lead)

            for i in range(2):
                c = CrmContact(tenant_id=tenant.id, name=f"Lost {i}")
                db.add(c)
                db.commit()
                db.refresh(c)
                lead = CrmLead(tenant_id=tenant.id, contact_id=c.id,
                               current_stage_id=stage_map["lost"].id, status="lost")
                db.add(lead)

            c = CrmContact(tenant_id=tenant.id, name="Open")
            db.add(c)
            db.commit()
            db.refresh(c)
            lead = CrmLead(tenant_id=tenant.id, contact_id=c.id,
                           current_stage_id=stage_map["new"].id, status="open")
            db.add(lead)
            db.commit()

        self.override_auth(user, tenant)
        response = self.client.get("/api/v1/crm/metrics")
        data = response.json()
        # 2/5 = 40%
        self.assertAlmostEqual(data["conversion_rate"], 40.0, places=1)

    def test_crm_metrics_contact_completion_rate(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            # 2 contacts with phone, 1 with email, 2 with neither
            for i in range(2):
                c = CrmContact(tenant_id=tenant.id, name=f"With Phone {i}", phone="+573001112233")
                db.add(c)
            c = CrmContact(tenant_id=tenant.id, name="With Email", email="test@test.com")
            db.add(c)
            for i in range(2):
                c = CrmContact(tenant_id=tenant.id, name=f"No Contact {i}")
                db.add(c)
            db.commit()

        self.override_auth(user, tenant)
        response = self.client.get("/api/v1/crm/metrics")
        data = response.json()
        # 3/5 = 60%
        self.assertAlmostEqual(data["contact_completion_rate"], 60.0, places=1)

    def test_crm_metrics_filters_by_date(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline = CrmPipelineService(db)
            stage = pipeline.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Old Lead")
            db.add(contact)
            db.commit()
            db.refresh(contact)

            from datetime import datetime as dt
            old_lead = CrmLead(
                tenant_id=tenant.id, contact_id=contact.id,
                current_stage_id=stage.id, status="open",
                created_at=dt(2024, 1, 1, tzinfo=UTC),
            )
            db.add(old_lead)
            db.commit()

        self.override_auth(user, tenant)
        # Filter only recent dates
        response = self.client.get(
            "/api/v1/crm/metrics?date_from=2026-01-01T00:00:00Z&date_to=2026-12-31T00:00:00Z"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["leads_created_this_month"], 0)


if __name__ == "__main__":
    unittest.main()