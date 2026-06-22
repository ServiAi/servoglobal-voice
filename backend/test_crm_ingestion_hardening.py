import os
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

TEST_DB_PATH = Path("serviai_crm_ingestion_hardening_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"
os.environ.setdefault("ULTRAVOX_API_KEY", "test")

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.analytics import Agent, Call
from app.models.crm import CrmCallContext, CrmContact, CrmLead, CrmPipelineStage
from app.models.identity import Tenant
from app.services.crm_call_context_service import CrmCallContextService
from app.services.crm_contact_service import CrmContactService
from app.services.crm_ingestion_service import CrmIngestionService
from app.services.crm_lead_resolver_service import CrmLeadResolverService


class CrmIngestionHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_DB_PATH.unlink(missing_ok=True)
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def seed_tenant_agent(self):
        with SessionLocal() as db:
            tenant = Tenant(name="Tenant Hardening", slug="tenant-hardening")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

            agent = Agent(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_agent_id="agent-hardening",
                name="Agente Hardening",
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
            return tenant, agent

    def seed_call(self, tenant, agent, external_call_id="uvx-hardening", joined=False, status="answered"):
        with SessionLocal() as db:
            call = Call(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_call_id=external_call_id,
                agent_id=agent.id,
                normalized_status=status,
                started_at=datetime.now(UTC),
                joined_at=datetime.now(UTC) if joined else None,
                customer_phone="3112223344",
            )
            db.add(call)
            db.commit()
            db.refresh(call)
            return call.id

    def get_call(self, db, call_id):
        return db.get(Call, call_id)

    def lead_stage_key(self, db, lead):
        stage = db.get(CrmPipelineStage, lead.current_stage_id)
        return stage.key

    def test_call_started_does_not_create_contact_or_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, status="in_progress")
        with SessionLocal() as db:
            CrmIngestionService(db).process_ultravox_event(
                {"event": "call.started", "call": {"callId": "uvx-hardening", "customerPhone": "3112223344"}},
                self.get_call(db, call_id),
            )
            self.assertEqual(db.scalar(select(CrmContact).where(CrmContact.tenant_id == tenant.id)), None)
            self.assertEqual(db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id)), None)

    def test_call_joined_creates_single_contact_and_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            CrmIngestionService(db).process_ultravox_event(
                {
                    "event": "call.joined",
                    "call": {
                        "callId": "uvx-hardening",
                        "customerPhone": "3112223344",
                        "metadata": {"user_name": "Maria", "user_email": "maria@test.com"},
                    },
                },
                self.get_call(db, call_id),
            )
            contacts = db.scalars(select(CrmContact).where(CrmContact.tenant_id == tenant.id)).all()
            leads = db.scalars(select(CrmLead).where(CrmLead.tenant_id == tenant.id)).all()
            self.assertEqual(len(contacts), 1)
            self.assertEqual(len(leads), 1)
            self.assertEqual(contacts[0].name, "Maria")
            self.assertEqual(self.lead_stage_key(db, leads[0]), "connected")

    def test_duplicate_call_joined_does_not_duplicate_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        payload = {
            "event": "call.joined",
            "call": {"callId": "uvx-hardening", "customerPhone": "3112223344"},
        }
        with SessionLocal() as db:
            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event(payload, self.get_call(db, call_id))
            ingestion.process_ultravox_event(payload, self.get_call(db, call_id))
            self.assertEqual(len(db.scalars(select(CrmLead).where(CrmLead.tenant_id == tenant.id)).all()), 1)

    def test_started_joined_ended_billed_creates_one_lead_only(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            ingestion = CrmIngestionService(db)
            for payload in (
                {"event": "call.started", "call": {"callId": "uvx-hardening"}},
                {"event": "call.joined", "call": {"callId": "uvx-hardening", "customerPhone": "3112223344"}},
                {
                    "event": "call.ended",
                    "call": {
                        "callId": "uvx-hardening",
                        "summary": "Quiere cotizar una propuesta.",
                        "shortSummary": "Quiere cotizacion",
                    },
                },
                {"event": "call.billed", "call": {"callId": "uvx-hardening", "billedDuration": "60s"}},
            ):
                ingestion.process_ultravox_event(payload, self.get_call(db, call_id))
            self.assertEqual(len(db.scalars(select(CrmContact).where(CrmContact.tenant_id == tenant.id)).all()), 1)
            leads = db.scalars(select(CrmLead).where(CrmLead.tenant_id == tenant.id)).all()
            self.assertEqual(len(leads), 1)
            self.assertEqual(self.lead_stage_key(db, leads[0]), "qualified")

    def test_call_billed_without_existing_lead_does_not_create_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent)
        with SessionLocal() as db:
            CrmIngestionService(db).process_ultravox_event(
                {"event": "call.billed", "call": {"callId": "uvx-hardening", "billedDuration": "60s"}},
                self.get_call(db, call_id),
            )
            self.assertEqual(db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id)), None)

    def test_call_ended_without_joined_does_not_create_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=False)
        with SessionLocal() as db:
            CrmIngestionService(db).process_ultravox_event(
                {"event": "call.ended", "call": {"callId": "uvx-hardening", "summary": "Quiere cotizar."}},
                self.get_call(db, call_id),
            )
            self.assertEqual(db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id)), None)

    def test_call_ended_with_joined_at_creates_lead_if_missing(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            CrmIngestionService(db).process_ultravox_event(
                {"event": "call.ended", "call": {"callId": "uvx-hardening", "summary": "Quiere cotizar."}},
                self.get_call(db, call_id),
            )
            lead = db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id))
            self.assertIsNotNone(lead)

    def test_duplicate_call_ended_does_not_duplicate_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        payload = {"event": "call.ended", "call": {"callId": "uvx-hardening", "summary": "Quiere cotizar."}}
        with SessionLocal() as db:
            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event(payload, self.get_call(db, call_id))
            ingestion.process_ultravox_event(payload, self.get_call(db, call_id))
            self.assertEqual(len(db.scalars(select(CrmLead).where(CrmLead.tenant_id == tenant.id)).all()), 1)

    def test_lead_uses_form_context_name_email_phone_company(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            CrmCallContextService(db).create_context(
                tenant.id,
                external_call_id="uvx-hardening",
                context={
                    "user_name": "Ana",
                    "user_email": "ana@test.com",
                    "user_phone": "3001112233",
                    "user_company": "ACME",
                    "user_use_case": "Ventas",
                },
            )
            CrmIngestionService(db).process_ultravox_event(
                {"event": "call.joined", "call": {"callId": "uvx-hardening"}},
                self.get_call(db, call_id),
            )
            contact = db.scalar(select(CrmContact).where(CrmContact.tenant_id == tenant.id))
            lead = db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id))
            self.assertEqual(contact.name, "Ana")
            self.assertEqual(contact.email, "ana@test.com")
            self.assertEqual(contact.phone_normalized, "+573001112233")
            self.assertEqual(contact.company, "ACME")
            self.assertEqual(lead.use_case, "Ventas")

    def test_internal_context_wins_over_webhook_metadata(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            CrmCallContextService(db).create_context(
                tenant.id,
                external_call_id="uvx-hardening",
                context={"user_name": "Interno", "user_email": "interno@test.com"},
            )
            CrmIngestionService(db).process_ultravox_event(
                {
                    "event": "call.joined",
                    "call": {
                        "callId": "uvx-hardening",
                        "metadata": {"user_name": "Webhook", "user_email": "webhook@test.com"},
                    },
                },
                self.get_call(db, call_id),
            )
            contact = db.scalar(select(CrmContact).where(CrmContact.tenant_id == tenant.id))
            self.assertEqual(contact.name, "Interno")
            self.assertEqual(contact.email, "interno@test.com")

    def test_metadata_used_when_internal_context_missing(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            CrmIngestionService(db).process_ultravox_event(
                {"event": "call.joined", "call": {"callId": "uvx-hardening", "metadata": {"user_name": "Meta"}}},
                self.get_call(db, call_id),
            )
            contact = db.scalar(select(CrmContact).where(CrmContact.tenant_id == tenant.id))
            self.assertEqual(contact.name, "Meta")

    def test_initial_state_used_when_metadata_missing(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            CrmIngestionService(db).process_ultravox_event(
                {"event": "call.joined", "call": {"callId": "uvx-hardening", "initialState": {"user_name": "Inicial"}}},
                self.get_call(db, call_id),
            )
            contact = db.scalar(select(CrmContact).where(CrmContact.tenant_id == tenant.id))
            self.assertEqual(contact.name, "Inicial")

    def test_request_context_used_when_initial_state_missing(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            CrmIngestionService(db).process_ultravox_event(
                {"event": "call.joined", "call": {"callId": "uvx-hardening", "requestContext": {"user_name": "Request"}}},
                self.get_call(db, call_id),
            )
            contact = db.scalar(select(CrmContact).where(CrmContact.tenant_id == tenant.id))
            self.assertEqual(contact.name, "Request")

    def test_sip_from_used_only_as_phone_fallback(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call = self.get_call(db, call_id)
            call.customer_phone = None
            db.commit()
            CrmIngestionService(db).process_ultravox_event(
                {"event": "call.joined", "call": {"callId": "uvx-hardening", "sipDetails": {"from": "3001112233"}}},
                call,
            )
            contact = db.scalar(select(CrmContact).where(CrmContact.tenant_id == tenant.id))
            self.assertEqual(contact.phone_normalized, "+573001112233")

    def test_missing_email_remains_null(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            CrmIngestionService(db).process_ultravox_event(
                {"event": "call.joined", "call": {"callId": "uvx-hardening"}},
                self.get_call(db, call_id),
            )
            contact = db.scalar(select(CrmContact).where(CrmContact.tenant_id == tenant.id))
            self.assertIsNone(contact.email)

    def test_missing_name_uses_lead_sin_nombre(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            CrmIngestionService(db).process_ultravox_event(
                {"event": "call.joined", "call": {"callId": "uvx-hardening"}},
                self.get_call(db, call_id),
            )
            contact = db.scalar(select(CrmContact).where(CrmContact.tenant_id == tenant.id))
            self.assertEqual(contact.name, "Lead sin nombre")

    def test_existing_contact_is_enriched_from_context(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            CrmContactService(db).get_or_create_contact(tenant.id, "3112223344", None, None)
            CrmIngestionService(db).process_ultravox_event(
                {
                    "event": "call.joined",
                    "call": {
                        "callId": "uvx-hardening",
                        "customerPhone": "3112223344",
                        "metadata": {"user_name": "Enriquecido", "user_email": "enriquecido@test.com", "company": "ACME"},
                    },
                },
                self.get_call(db, call_id),
            )
            contact = db.scalar(select(CrmContact).where(CrmContact.tenant_id == tenant.id))
            self.assertEqual(contact.name, "Enriquecido")
            self.assertEqual(contact.email, "enriquecido@test.com")
            self.assertEqual(contact.company, "ACME")

    def test_existing_lead_is_enriched_without_overwriting_existing_fields(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            contact = CrmContactService(db).get_or_create_contact(tenant.id, "3112223344", None, "Lead")
            lead = CrmLeadResolverService(db).resolve_or_create_lead_for_connected_call(
                tenant.id,
                self.get_call(db, call_id),
                contact,
                {"interest": "Original"},
            )
            CrmIngestionService(db).process_ultravox_event(
                {
                    "event": "call.joined",
                    "call": {
                        "callId": "uvx-hardening",
                        "customerPhone": "3112223344",
                        "metadata": {"interest": "Nuevo", "industry": "Tech"},
                    },
                },
                self.get_call(db, call_id),
            )
            db.refresh(lead)
            self.assertEqual(lead.interest, "Original")
            self.assertEqual(lead.industry, "Tech")

    def test_successful_crear_evento_with_event_id_moves_to_scheduled(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event(
                {"event": "call.joined", "call": {"callId": "uvx-hardening"}},
                self.get_call(db, call_id),
            )
            ingestion.process_ultravox_event(
                {
                    "event": "call.ended",
                    "call": {
                        "callId": "uvx-hardening",
                        "toolCalls": [{"name": "crear_evento", "status": "success", "result": {"event_id": "evt-1"}}],
                    },
                },
                self.get_call(db, call_id),
            )
            lead = db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id))
            self.assertEqual(self.lead_stage_key(db, lead), "scheduled")

    def test_crear_evento_without_event_id_does_not_move_to_scheduled(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event({"event": "call.joined", "call": {"callId": "uvx-hardening"}}, self.get_call(db, call_id))
            ingestion.process_ultravox_event(
                {"event": "call.ended", "call": {"callId": "uvx-hardening", "toolCalls": [{"name": "crear_evento", "status": "success"}]}},
                self.get_call(db, call_id),
            )
            lead = db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id))
            self.assertNotEqual(self.lead_stage_key(db, lead), "scheduled")

    def test_failed_crear_evento_does_not_move_to_scheduled(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event({"event": "call.joined", "call": {"callId": "uvx-hardening"}}, self.get_call(db, call_id))
            ingestion.process_ultravox_event(
                {
                    "event": "call.ended",
                    "call": {"callId": "uvx-hardening", "toolCalls": [{"name": "crear_evento", "status": "failed", "result": {"event_id": "evt-1"}}]},
                },
                self.get_call(db, call_id),
            )
            lead = db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id))
            self.assertNotEqual(self.lead_stage_key(db, lead), "scheduled")

    def test_summary_mentions_schedule_without_tool_does_not_move_to_scheduled(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event({"event": "call.joined", "call": {"callId": "uvx-hardening"}}, self.get_call(db, call_id))
            ingestion.process_ultravox_event(
                {"event": "call.ended", "call": {"callId": "uvx-hardening", "summary": "Quiere agendar una cita."}},
                self.get_call(db, call_id),
            )
            lead = db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id))
            self.assertNotEqual(self.lead_stage_key(db, lead), "scheduled")

    def test_booking_intent_without_event_sets_next_action_confirm_booking(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event({"event": "call.joined", "call": {"callId": "uvx-hardening"}}, self.get_call(db, call_id))
            ingestion.process_ultravox_event(
                {"event": "call.ended", "call": {"callId": "uvx-hardening", "summary": "Cliente quiere una reunion."}},
                self.get_call(db, call_id),
            )
            lead = db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id))
            self.assertEqual(lead.next_action, "confirm_booking")

    def test_unique_lead_per_call_constraint_or_service_guard(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call = self.get_call(db, call_id)
            contact = CrmContactService(db).get_or_create_contact(tenant.id, "3112223344", None, "Lead")
            resolver = CrmLeadResolverService(db)
            resolver.resolve_or_create_lead_for_connected_call(tenant.id, call, contact)
            stage = db.scalar(select(CrmPipelineStage).where(CrmPipelineStage.tenant_id == tenant.id, CrmPipelineStage.key == "connected"))
            db.add(
                CrmLead(
                    tenant_id=tenant.id,
                    contact_id=contact.id,
                    current_stage_id=stage.id,
                    status="open",
                    created_from_call_id=call.id,
                    last_call_id=call.id,
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_events_out_of_order_do_not_duplicate_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event(
                {"event": "call.ended", "call": {"callId": "uvx-hardening", "summary": "Quiere cotizar."}},
                self.get_call(db, call_id),
            )
            ingestion.process_ultravox_event(
                {"event": "call.joined", "call": {"callId": "uvx-hardening", "customerPhone": "3112223344"}},
                self.get_call(db, call_id),
            )
            self.assertEqual(len(db.scalars(select(CrmLead).where(CrmLead.tenant_id == tenant.id)).all()), 1)


if __name__ == "__main__":
    unittest.main()
