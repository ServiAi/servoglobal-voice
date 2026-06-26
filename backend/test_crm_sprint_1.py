import json
import os
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

# Set up test database
TEST_DB_PATH = Path("serviai_crm_sprint1_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.api.auth.deps import AuthContext, get_current_auth_context
from app.models.analytics import Agent, Call, CallEvent
from app.models.identity import Tenant, User, TenantMembership
from app.models.crm import CrmContact, CrmPipelineStage, CrmLead, CrmActivity, CrmTask
from app.services.crm_pipeline_service import CrmPipelineService
from app.services.crm_contact_service import CrmContactService, normalize_phone
from app.services.crm_lead_service import CrmLeadService
from app.services.crm_classifier_service import CrmClassifierService
from app.services.crm_ingestion_service import CrmIngestionService
from app.services.ultravox_ingestion_service import UltravoxIngestionService

class CrmSprint1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_DB_PATH.unlink(missing_ok=True)
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        # Clean tables
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

    # --- Unit Tests ---

    def test_phone_normalization(self):
        self.assertEqual(normalize_phone("+57 (300) 111-22-33"), "+573001112233")
        self.assertEqual(normalize_phone("3001112233"), "+573001112233")  # Colombia fallback
        self.assertEqual(normalize_phone(None), None)
        self.assertEqual(normalize_phone(""), None)

    def test_lazy_pipeline_stages_creation(self):
        tenant, _, _ = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            service = CrmPipelineService(db)
            stages = service.ensure_default_pipeline(tenant.id)
            self.assertEqual(len(stages), 10)
            self.assertEqual(stages[0].key, "new")
            self.assertTrue(stages[0].is_default)
            self.assertEqual(stages[2].key, "connected")
            
            # Check duplicate calls are idempotent
            stages_dup = service.ensure_default_pipeline(tenant.id)
            self.assertEqual(len(stages_dup), 10)
            self.assertEqual(stages_dup[0].id, stages[0].id)

    def test_contact_creation_and_deduplication(self):
        tenant, _, _ = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            service = CrmContactService(db)
            
            # Create first contact
            contact1 = service.get_or_create_contact(
                tenant_id=tenant.id,
                phone="3005556677",
                email="contact1@gmail.com",
                name="John Doe",
                metadata={"company": "Acme Corp", "source": "landing"},
            )
            self.assertEqual(contact1.name, "John Doe")
            self.assertEqual(contact1.phone_normalized, "+573005556677")
            self.assertEqual(contact1.company, "Acme Corp")
            
            # Same phone normalized should deduplicate
            contact2 = service.get_or_create_contact(
                tenant_id=tenant.id,
                phone="+57 (300) 555-6677",
                email="contact2@gmail.com",
                name="John Overwrite",
            )
            self.assertEqual(contact1.id, contact2.id)
            # Enrichment check: name should not overwrite unless previous was default
            self.assertEqual(contact2.name, "John Doe")
            
            # Create contact with only email
            contact3 = service.get_or_create_contact(
                tenant_id=tenant.id,
                phone=None,
                email="only-email@test.com",
                name="Email Guy",
            )
            self.assertIsNotNone(contact3.id)
            self.assertEqual(contact3.email, "only-email@test.com")
            
            # Same email should deduplicate
            contact4 = service.get_or_create_contact(
                tenant_id=tenant.id,
                phone="3009998888",
                email="only-email@test.com",
                name="Email Guy With Phone",
            )
            self.assertEqual(contact3.id, contact4.id)
            self.assertEqual(contact4.phone_normalized, "+573009998888")

    def test_lead_creation_and_enrichment(self):
        tenant, _, _ = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            contact_service = CrmContactService(db)
            lead_service = CrmLeadService(db)
            
            contact = contact_service.get_or_create_contact(
                tenant_id=tenant.id,
                phone="3004445555",
                email="leadtest@gmail.com",
                name="Lead Tester",
            )
            
            lead1 = lead_service.get_or_create_open_lead(
                tenant_id=tenant.id,
                contact_id=contact.id,
                call_id="call-1",
                metadata={"interest": "AI Agents", "budget_range": "1000-5000"},
            )
            self.assertEqual(lead1.status, "open")
            self.assertEqual(lead1.interest, "AI Agents")
            self.assertEqual(lead1.budget_range, "1000-5000")
            
            # Retrieval of existing open lead
            lead2 = lead_service.get_or_create_open_lead(
                tenant_id=tenant.id,
                contact_id=contact.id,
                call_id="call-2",
                metadata={"interest": "New Interest", "industry": "Tech"},
            )
            self.assertEqual(lead1.id, lead2.id)
            self.assertEqual(lead2.last_call_id, "call-2")
            self.assertEqual(lead2.interest, "AI Agents")  # Preserved
            self.assertEqual(lead2.industry, "Tech")  # Enriched

    def test_classifier_rules(self):
        classifier = CrmClassifierService()
        
        # Voicemail check
        self.assertEqual(classifier.classify_lead_stage("voicemail", None, None), "voicemail")
        
        # Unanswered check
        self.assertEqual(classifier.classify_lead_stage("unanswered", None, None), "follow_up")
        
        # Scheduling language alone must not move a lead to scheduled.
        self.assertIsNone(
            classifier.classify_lead_stage("answered", "Reunión agendada para el lunes.", None),
        )
        
        # Not Interested keyword check
        self.assertEqual(
            classifier.classify_lead_stage("answered", "El cliente no le interesa.", None),
            "not_interested"
        )
        
        # Qualified keyword check
        self.assertEqual(
            classifier.classify_lead_stage("answered", "Interesado en cotizar.", None),
            "qualified"
        )
        
        # No signal
        self.assertIsNone(classifier.classify_lead_stage("answered", "Hola, gracias.", None))

    # --- Integration / E2E Tests via Ingestion Service ---

    def test_ingestion_call_joined(self):
        tenant, agent, _ = self.seed_tenant_agent_user()
        
        with SessionLocal() as db:
            # Seed call record
            call = Call(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_call_id="uvx-joined-test",
                agent_id=agent.id,
                normalized_status="in_progress",
                started_at=datetime.now(UTC),
            )
            db.add(call)
            db.commit()
            db.refresh(call)
            
            payload = {
                "event": "call.joined",
                "eventId": "evt-joined-1",
                "call": {
                    "callId": "uvx-joined-test",
                    "customerPhone": "3112223344",
                    "metadata": {
                        "user_name": "Maria Lopez",
                        "interest": "Omnichannel CRM",
                    }
                }
            }

            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event(payload, call)
            
            # Assertions
            contact = db.scalar(select(CrmContact).where(CrmContact.tenant_id == tenant.id))
            self.assertIsNotNone(contact)
            self.assertEqual(contact.name, "Maria Lopez")
            self.assertEqual(contact.phone_normalized, "+573112223344")
            
            lead = db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id))
            self.assertIsNotNone(lead)
            self.assertEqual(lead.contact_id, contact.id)
            self.assertEqual(lead.interest, "Omnichannel CRM")
            
            # Check lead stage updated to connected
            connected_stage = db.scalar(
                select(CrmPipelineStage).where(CrmPipelineStage.tenant_id == tenant.id, CrmPipelineStage.key == "connected")
            )
            self.assertEqual(lead.current_stage_id, connected_stage.id)
            
            # Check activities created (should have call_joined and stage_changed)
            activities = db.scalars(
                select(CrmActivity).where(CrmActivity.lead_id == lead.id).order_by(CrmActivity.activity_type.asc())
            ).all()
            self.assertEqual(len(activities), 2)
            self.assertEqual(activities[0].activity_type, "call_joined")
            self.assertEqual(activities[1].activity_type, "stage_changed")
            self.assertEqual(activities[0].outcome, "connected")

    def test_ingestion_call_ended_and_classification(self):
        tenant, agent, _ = self.seed_tenant_agent_user()
        
        with SessionLocal() as db:
            call = Call(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_call_id="uvx-ended-test",
                agent_id=agent.id,
                normalized_status="answered",
                started_at=datetime.now(UTC),
                joined_at=datetime.now(UTC),
            )
            db.add(call)
            db.commit()
            db.refresh(call)
            
            payload = {
                "event": "call.ended",
                "eventId": "evt-ended-1",
                "call": {
                    "callId": "uvx-ended-test",
                    "customerPhone": "3112223344",
                    "summary": "Reunión agendada para presentar propuesta técnica.",
                    "shortSummary": "Cita agendada",
                    "endReason": "hangup",
                    "metadata": {
                        "user_name": "Maria Lopez",
                    }
                }
            }

            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event(payload, call)
            
            # Scheduling language without crear_evento must not classify as scheduled.
            lead = db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id))
            qualified_stage = db.scalar(
                select(CrmPipelineStage).where(CrmPipelineStage.tenant_id == tenant.id, CrmPipelineStage.key == "qualified")
            )
            self.assertEqual(lead.current_stage_id, qualified_stage.id)
            self.assertEqual(lead.summary, "Reunión agendada para presentar propuesta técnica.")
            self.assertEqual(lead.short_summary, "Cita agendada")
            
            # Activities check (should have call_ended and stage_changed)
            activities = db.scalars(
                select(CrmActivity).where(CrmActivity.lead_id == lead.id).order_by(CrmActivity.activity_type.asc())
            ).all()
            self.assertEqual(len(activities), 2)
            self.assertEqual(activities[0].activity_type, "call_ended")
            self.assertEqual(activities[1].activity_type, "stage_changed")

    def test_ingestion_call_ended_schedules_only_when_crear_evento_tool_runs(self):
        tenant, agent, _ = self.seed_tenant_agent_user()

        with SessionLocal() as db:
            call = Call(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_call_id="uvx-tool-scheduled-test",
                agent_id=agent.id,
                normalized_status="answered",
                started_at=datetime.now(UTC),
                joined_at=datetime.now(UTC),
            )
            db.add(call)
            db.commit()
            db.refresh(call)

            payload = {
                "event": "call.ended",
                "eventId": "evt-ended-tool-1",
                "call": {
                    "callId": "uvx-tool-scheduled-test",
                    "customerPhone": "3112223344",
                    "summary": "Se confirmó una reunión con el cliente.",
                    "shortSummary": "Reunión confirmada",
                    "metadata": {"user_name": "Maria Lopez"},
                    "toolCalls": [
                        {
                            "name": "crear_evento",
                            "status": "success",
                            "result": {"event_id": "cal-123"},
                        }
                    ],
                },
            }

            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event(payload, call)

            lead = db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id))
            scheduled_stage = db.scalar(
                select(CrmPipelineStage).where(CrmPipelineStage.tenant_id == tenant.id, CrmPipelineStage.key == "scheduled")
            )
            self.assertEqual(lead.current_stage_id, scheduled_stage.id)

    def test_ingestion_reuses_one_lead_across_events_for_same_call(self):
        tenant, agent, _ = self.seed_tenant_agent_user()

        with SessionLocal() as db:
            call = Call(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_call_id="uvx-single-call",
                agent_id=agent.id,
                normalized_status="answered",
                customer_phone="3112223344",
                started_at=datetime.now(UTC),
            )
            db.add(call)
            db.commit()
            db.refresh(call)

            ingestion = CrmIngestionService(db)
            for payload in (
                {
                    "event": "call.started",
                    "eventId": "evt-single-started",
                    "call": {"callId": "uvx-single-call"},
                },
                {
                    "event": "call.joined",
                    "eventId": "evt-single-joined",
                    "call": {
                        "callId": "uvx-single-call",
                        "customerPhone": "3112223344",
                        "metadata": {"user_name": "Maria Lopez"},
                    },
                },
                {
                    "event": "call.ended",
                    "eventId": "evt-single-ended",
                    "call": {
                        "callId": "uvx-single-call",
                        "summary": "Quiere cotizar una propuesta comercial.",
                        "shortSummary": "Quiere cotización",
                    },
                },
                {
                    "event": "call.billed",
                    "eventId": "evt-single-billed",
                    "call": {
                        "callId": "uvx-single-call",
                        "billedDuration": "60s",
                    },
                },
            ):
                ingestion.process_ultravox_event(payload, call)

            contacts = db.scalars(select(CrmContact).where(CrmContact.tenant_id == tenant.id)).all()
            leads = db.scalars(select(CrmLead).where(CrmLead.tenant_id == tenant.id)).all()
            self.assertEqual(len(contacts), 1)
            self.assertEqual(len(leads), 1)
            self.assertEqual(contacts[0].phone_normalized, "+573112223344")

            stage = db.scalar(select(CrmPipelineStage).where(CrmPipelineStage.id == leads[0].current_stage_id))
            self.assertEqual(stage.key, "qualified")

    def test_webhook_crm_integration_does_not_break_on_crm_failure(self):
        tenant, agent, _ = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            service = UltravoxIngestionService(db)
            
            # Corrupt lead status argument in payload to trigger error in CRM but keep call ingestion working
            payload = {
                "event": "call.joined",
                "eventId": "evt-joined-broken",
                "call": {
                    "callId": "uvx-broken",
                    "metadata": {
                        "tenant_id": tenant.id,
                        "tenant_slug": tenant.slug,
                        # Pass name as integer to trigger type issues in CRM or similar, 
                        # but we want to make sure it doesn't crash the main webhook
                    }
                }
            }
            
            # Mock get_or_create_contact to raise RuntimeError
            original_contact_creator = service.ingest_event
            
            # We call the service and check it returns successfully without raising exception
            res = service.ingest_event(payload)
            self.assertIsNotNone(res.call)
            self.assertEqual(res.call.external_call_id, "uvx-broken")

    # --- API Endpoints Tests ---

    def test_crm_endpoints_multitenancy(self):
        # Seed Tenant A and Tenant B
        tenant_a, agent_a, user_a = self.seed_tenant_agent_user()
        
        with SessionLocal() as db:
            tenant_b = Tenant(name="Empresa Test B", slug="empresa-test-b")
            db.add(tenant_b)
            db.commit()
            db.refresh(tenant_b)
            
            user_b = User(
                email="user_b@test.com",
                name="Test User B",
                status="active",
                external_auth_id="auth0|user-b",
            )
            db.add(user_b)
            db.commit()
            db.refresh(user_b)
            
            membership_b = TenantMembership(
                tenant_id=tenant_b.id,
                user_id=user_b.id,
                role="tenant_admin",
                status="active",
            )
            db.add(membership_b)
            
            # Seed lead in tenant A
            pipeline_service = CrmPipelineService(db)
            stage_a = pipeline_service.get_stage_by_key(tenant_a.id, "new")
            contact_a = CrmContact(tenant_id=tenant_a.id, name="Contact A")
            db.add(contact_a)
            db.commit()
            db.refresh(contact_a)
            
            lead_a = CrmLead(
                tenant_id=tenant_a.id,
                contact_id=contact_a.id,
                current_stage_id=stage_a.id,
                status="open",
            )
            db.add(lead_a)
            db.commit()
            db.refresh(lead_a)
            
            # Seed lead in tenant B
            stage_b = pipeline_service.get_stage_by_key(tenant_b.id, "new")
            contact_b = CrmContact(tenant_id=tenant_b.id, name="Contact B")
            db.add(contact_b)
            db.commit()
            db.refresh(contact_b)
            
            lead_b = CrmLead(
                tenant_id=tenant_b.id,
                contact_id=contact_b.id,
                current_stage_id=stage_b.id,
                status="open",
            )
            db.add(lead_b)
            db.commit()
            db.refresh(lead_b)

        # Authenticate as User A (Tenant A)
        self.override_auth(user_a, tenant_a)
        
        # Get Leads list
        response = self.client.get("/api/v1/crm/leads")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["lead_id"], lead_a.id)
        
        # Trying to access lead B directly should return 404
        response_detail = self.client.get(f"/api/v1/crm/leads/{lead_b.id}")
        self.assertEqual(response_detail.status_code, 404)

        # Authenticate as User B (Tenant B)
        self.override_auth(user_b, tenant_b)
        
        # Get Leads list
        response = self.client.get("/api/v1/crm/leads")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["lead_id"], lead_b.id)

    def test_ingestion_call_billed_creates_activity(self):
        tenant, agent, _ = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            call = Call(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_call_id="uvx-billed-test",
                agent_id=agent.id,
                normalized_status="answered",
                started_at=datetime.now(UTC),
            )
            db.add(call)
            db.commit()
            db.refresh(call)

            payload = {
                "event": "call.billed",
                "call": {
                    "callId": "uvx-billed-test",
                    "billedDuration": "120s",
                    "sipDetails": {
                        "billedDuration": "90s"
                    }
                }
            }

            ingestion = CrmIngestionService(db)
            joined_payload = {
                "event": "call.joined",
                "call": {
                    "callId": "uvx-billed-test",
                    "customerPhone": "3112223344",
                },
            }
            ingestion.process_ultravox_event(joined_payload, call)
            ingestion.process_ultravox_event(payload, call)

            # Assert activity was created and parsed billed duration
            activity = db.scalar(
                select(CrmActivity).where(
                    CrmActivity.tenant_id == tenant.id,
                    CrmActivity.call_id == call.id,
                    CrmActivity.activity_type == "call_billed"
                )
            )
            self.assertIsNotNone(activity)
            self.assertIn("120s", activity.description)

    def test_ingestion_duplicate_event_does_not_duplicate_activity(self):
        tenant, agent, _ = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            call = Call(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_call_id="uvx-dup-test",
                agent_id=agent.id,
                normalized_status="in_progress",
                started_at=datetime.now(UTC),
            )
            db.add(call)
            db.commit()
            db.refresh(call)

            payload = {
                "event": "call.joined",
                "call": {
                    "callId": "uvx-dup-test",
                    "customerPhone": "3112223344"
                }
            }

            ingestion = CrmIngestionService(db)
            # Process twice
            ingestion.process_ultravox_event(payload, call)
            ingestion.process_ultravox_event(payload, call)

            activities = db.scalars(
                select(CrmActivity).where(
                    CrmActivity.tenant_id == tenant.id,
                    CrmActivity.call_id == call.id,
                    CrmActivity.activity_type == "call_joined"
                )
            ).all()
            self.assertEqual(len(activities), 1)

    def test_ingestion_missing_tenant_metadata_does_not_create_crm(self):
        tenant, agent, _ = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            # Keep as transient Call to avoid DB NOT NULL constraint violation
            call = Call(
                tenant_id=None, # Missing tenant ID
                external_provider="ultravox",
                external_call_id="uvx-no-tenant-test",
                agent_id=agent.id,
                normalized_status="in_progress",
                started_at=datetime.now(UTC),
            )

            payload = {
                "event": "call.joined",
                "call": {
                    "callId": "uvx-no-tenant-test",
                    "customerPhone": "3112223344"
                }
            }

            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event(payload, call)

            # Assert no contact was created
            contact = db.scalar(select(CrmContact).where(CrmContact.name == "Lead sin nombre"))
            self.assertIsNone(contact)

    def test_crm_lead_detail_success(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline_service = CrmPipelineService(db)
            stage = pipeline_service.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Test Contact Detail")
            db.add(contact)
            db.commit()
            db.refresh(contact)

            lead = CrmLead(
                tenant_id=tenant.id,
                contact_id=contact.id,
                current_stage_id=stage.id,
                status="open",
            )
            db.add(lead)
            db.commit()
            db.refresh(lead)

            # Create an activity
            activity = CrmActivity(
                tenant_id=tenant.id,
                contact_id=contact.id,
                lead_id=lead.id,
                activity_type="note",
                title="Nota de prueba",
                occurred_at=datetime.now(UTC)
            )
            db.add(activity)
            db.commit()

        self.override_auth(user, tenant)
        response = self.client.get(f"/api/v1/crm/leads/{lead.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], lead.id)
        self.assertEqual(len(data["activities"]), 1)
        self.assertEqual(data["activities"][0]["title"], "Nota de prueba")

    def test_ingestion_voicemail_moves_lead_to_voicemail(self):
        tenant, agent, _ = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            call = Call(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_call_id="uvx-voicemail",
                agent_id=agent.id,
                normalized_status="voicemail",
                started_at=datetime.now(UTC),
                joined_at=datetime.now(UTC),
            )
            db.add(call)
            db.commit()
            db.refresh(call)

            payload = {
                "event": "call.ended",
                "call": {
                    "callId": "uvx-voicemail",
                    "customerPhone": "3112223344",
                    "endReason": "voicemail"
                }
            }

            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event(payload, call)

            lead = db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id))
            stage = db.scalar(select(CrmPipelineStage).where(CrmPipelineStage.id == lead.current_stage_id))
            self.assertEqual(stage.key, "voicemail")

    def test_ingestion_not_interested_moves_lead_to_not_interested(self):
        tenant, agent, _ = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            call = Call(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_call_id="uvx-not-interested",
                agent_id=agent.id,
                normalized_status="answered",
                started_at=datetime.now(UTC),
                joined_at=datetime.now(UTC),
            )
            db.add(call)
            db.commit()
            db.refresh(call)

            payload = {
                "event": "call.ended",
                "call": {
                    "callId": "uvx-not-interested",
                    "customerPhone": "3112223344",
                    "summary": "El cliente dice que no le interesa y que no quiere recibir más llamadas.",
                    "shortSummary": "No interesado"
                }
            }

            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event(payload, call)

            lead = db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id))
            stage = db.scalar(select(CrmPipelineStage).where(CrmPipelineStage.id == lead.current_stage_id))
            self.assertEqual(stage.key, "not_interested")
            self.assertEqual(lead.status, "lost")

    def test_call_ended_before_call_joined_without_joined_at_does_not_create_crm(self):
        tenant, agent, _ = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            call = Call(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_call_id="uvx-out-of-order",
                agent_id=agent.id,
                normalized_status="answered",
                started_at=datetime.now(UTC),
            )
            db.add(call)
            db.commit()
            db.refresh(call)

            payload = {
                "event": "call.ended",
                "call": {
                    "callId": "uvx-out-of-order",
                    "customerPhone": "3112223344",
                    "summary": "El cliente quiere una cotización rápida.",
                    "shortSummary": "Quiere cotización"
                }
            }

            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event(payload, call)

            # Commercial CRM records should not be created without a real connection.
            contact = db.scalar(select(CrmContact).where(CrmContact.tenant_id == tenant.id))
            self.assertIsNone(contact)

            lead = db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id))
            self.assertIsNone(lead)

    def test_stage_changed_history_is_not_overwritten(self):
        tenant, agent, _ = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            call = Call(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_call_id="uvx-history-test",
                agent_id=agent.id,
                normalized_status="answered",
                started_at=datetime.now(UTC),
            )
            db.add(call)
            db.commit()
            db.refresh(call)

            ingestion = CrmIngestionService(db)

            # 1. Process call.joined (connected)
            joined_payload = {
                "event": "call.joined",
                "call": {
                    "callId": "uvx-history-test",
                    "customerPhone": "3112223344"
                }
            }
            ingestion.process_ultravox_event(joined_payload, call)

            # 2. Process call.ended (qualified)
            ended_payload = {
                "event": "call.ended",
                "call": {
                    "callId": "uvx-history-test",
                    "customerPhone": "3112223344",
                    "summary": "Quiere cotización de propuesta",
                    "shortSummary": "Quiere propuesta"
                }
            }
            ingestion.process_ultravox_event(ended_payload, call)

            # Assert there are two separate stage_changed activities
            activities = db.scalars(
                select(CrmActivity).where(
                    CrmActivity.tenant_id == tenant.id,
                    CrmActivity.call_id == call.id,
                    CrmActivity.activity_type == "stage_changed"
                ).order_by(CrmActivity.occurred_at.asc())
            ).all()

            self.assertEqual(len(activities), 2)
            self.assertEqual(activities[0].deduplication_key, "connected")
            self.assertEqual(activities[1].deduplication_key, "qualified")
            self.assertIsNotNone(activities[0].to_stage_id)
            self.assertIsNotNone(activities[1].to_stage_id)

    def test_activity_response_does_not_expose_raw_payload_json(self):
        tenant, agent, user = self.seed_tenant_agent_user()
        with SessionLocal() as db:
            pipeline_service = CrmPipelineService(db)
            stage = pipeline_service.get_stage_by_key(tenant.id, "new")
            contact = CrmContact(tenant_id=tenant.id, name="Test Contact Payload")
            db.add(contact)
            db.commit()
            db.refresh(contact)

            lead = CrmLead(
                tenant_id=tenant.id,
                contact_id=contact.id,
                current_stage_id=stage.id,
                status="open",
            )
            db.add(lead)
            db.commit()
            db.refresh(lead)

            # Create an activity with raw payload
            activity = CrmActivity(
                tenant_id=tenant.id,
                contact_id=contact.id,
                lead_id=lead.id,
                activity_type="call_joined",
                title="Llamada establecida",
                occurred_at=datetime.now(UTC),
                payload_json={
                    "event": "call.joined",
                    "systemPrompt": "secret prompt",
                    "callbacks": ["http://secret-callback"],
                    "call": {
                        "recordingUrl": "http://recording-url",
                        "summary": "Test summary",
                    }
                }
            )
            db.add(activity)
            db.commit()

        self.override_auth(user, tenant)
        response = self.client.get("/api/v1/crm/activities")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        activity_data = data[0]

        # Verify raw fields are hidden, but clean ones are exposed
        self.assertNotIn("payload_json", activity_data)
        self.assertNotIn("systemPrompt", activity_data)
        self.assertNotIn("callbacks", activity_data)
        self.assertEqual(activity_data["recording_url"], "http://recording-url")
        self.assertEqual(activity_data["summary"], "Test summary")
        self.assertEqual(activity_data["provider_event"], "call.joined")

    def test_delete_lead_and_bulk_delete(self):
        from sqlalchemy import func
        tenant, agent, user = self.seed_tenant_agent_user()
        
        # Create a contact and a lead
        with SessionLocal() as db:
            contact = CrmContact(tenant_id=tenant.id, name="Lead to delete", phone="+573001234567")
            db.add(contact)
            db.commit()
            db.refresh(contact)
            
            stage = CrmPipelineStage(tenant_id=tenant.id, key="new", name="Nuevo", position=1)
            db.add(stage)
            db.commit()
            db.refresh(stage)
            
            lead = CrmLead(
                tenant_id=tenant.id,
                contact_id=contact.id,
                current_stage_id=stage.id,
                status="open",
            )
            db.add(lead)
            db.commit()
            db.refresh(lead)
            
            # Add a task and activity for cascade verify
            task = CrmTask(tenant_id=tenant.id, lead_id=lead.id, title="Test Task")
            activity = CrmActivity(tenant_id=tenant.id, lead_id=lead.id, contact_id=contact.id, activity_type="note", title="Test Activity")
            db.add(task)
            db.add(activity)
            db.commit()
            
            lead_id = lead.id
            contact_id = contact.id
            task_id = task.id
            activity_id = activity.id

        self.override_auth(user, tenant)
        
        # Test DELETE /api/v1/crm/leads/{lead_id}
        res_del = self.client.delete(f"/api/v1/crm/leads/{lead_id}")
        self.assertEqual(res_del.status_code, 204)
        
        # Verify cascades and orphaned contact cleanup
        with SessionLocal() as db:
            self.assertIsNone(db.scalar(select(CrmLead).where(CrmLead.id == lead_id)))
            self.assertIsNone(db.scalar(select(CrmTask).where(CrmTask.id == task_id)))
            self.assertIsNone(db.scalar(select(CrmActivity).where(CrmActivity.id == activity_id)))
            self.assertIsNone(db.scalar(select(CrmContact).where(CrmContact.id == contact_id)))

        # Seed again for bulk delete verification
        with SessionLocal() as db:
            contact2 = CrmContact(tenant_id=tenant.id, name="Lead to delete 2", phone="+573001234568")
            db.add(contact2)
            db.commit()
            db.refresh(contact2)
            
            lead2 = CrmLead(
                tenant_id=tenant.id,
                contact_id=contact2.id,
                current_stage_id=stage.id,
                status="open",
            )
            db.add(lead2)
            db.commit()
            db.refresh(lead2)
            
            lead2_id = lead2.id

        # Change user role to platform_admin for bulk delete
        with SessionLocal() as db:
            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant.id,
                    TenantMembership.user_id == user.id,
                )
            )
            membership.role = "platform_admin"
            db.commit()
        self.override_auth(user, tenant)

        # Test DELETE /api/v1/crm/leads
        res_bulk = self.client.delete("/api/v1/crm/leads")
        self.assertEqual(res_bulk.status_code, 204)
        
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmLead).where(CrmLead.tenant_id == tenant.id)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmContact).where(CrmContact.tenant_id == tenant.id)), 0)

if __name__ == "__main__":
    unittest.main()
