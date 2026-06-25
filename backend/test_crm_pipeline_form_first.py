import os
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

TEST_DB_PATH = Path("serviai_crm_pipeline_form_first_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"
os.environ.setdefault("ULTRAVOX_API_KEY", "test")

from app.api.endpoints.voice import _create_form_context_and_lead
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.analytics import Agent, Call
from app.models.crm import CrmCallContext, CrmContact, CrmLead, CrmPipelineStage
from app.models.identity import Tenant
from app.services.crm_call_context_service import CrmCallContextService
from app.services.crm_classifier_service import CrmClassifierService
from app.services.crm_ingestion_service import CrmIngestionService
from app.services.crm_lead_resolver_service import CrmLeadResolverService
from app.services.crm_lead_service import CrmLeadService


class CrmPipelineFormFirstTests(unittest.TestCase):
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
            tenant = Tenant(name="Tenant Pipeline", slug="tenant-pipeline")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            agent = Agent(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_agent_id="agent-pipeline",
                name="Agente Pipeline",
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
            return tenant, agent

    def seed_call(self, tenant, agent, external_call_id="uvx-pipeline", *, joined=False, status="answered", phone="3001112233"):
        with SessionLocal() as db:
            call = Call(
                tenant_id=tenant.id,
                external_provider="ultravox",
                external_call_id=external_call_id,
                agent_id=agent.id,
                normalized_status=status,
                started_at=datetime.now(UTC),
                joined_at=datetime.now(UTC) if joined else None,
                customer_phone=phone,
            )
            db.add(call)
            db.commit()
            db.refresh(call)
            return call.id

    def submit_form(self, db, tenant, **overrides):
        context = {
            "user_name": "Maria Form",
            "user_email": "maria@test.com",
            "user_phone": "3001112233",
            "user_company": "ACME",
            "user_use_case": "Automatizar ventas",
        }
        context.update(overrides)
        return _create_form_context_and_lead(db, tenant, context)

    def get_call(self, db, call_id):
        return db.get(Call, call_id)

    def stage_key(self, db, lead):
        return db.get(CrmPipelineStage, lead.current_stage_id).key

    def lead(self, db, tenant):
        return db.scalar(select(CrmLead).where(CrmLead.tenant_id == tenant.id))

    def leads(self, db, tenant):
        return db.scalars(select(CrmLead).where(CrmLead.tenant_id == tenant.id)).all()

    def payload(self, event, external_call_id="uvx-pipeline", context=None, **call_fields):
        metadata = {}
        if context:
            metadata = {
                "context_id": context.context_id,
                "form_submission_id": context.form_submission_id,
            }
        call = {"callId": external_call_id, "customerPhone": "3001112233", "metadata": metadata}
        call.update(call_fields)
        return {"event": event, "call": call}

    def context_only_payload(self, event, context, external_call_id="uvx-pipeline", **call_fields):
        call = {
            "callId": external_call_id,
            "metadata": {
                "context_id": context.context_id,
                "form_submission_id": context.form_submission_id,
            },
        }
        call.update(call_fields)
        return {"event": event, "call": call}

    def test_form_submission_creates_contact_and_lead_in_new(self):
        tenant, _ = self.seed_tenant_agent()
        with SessionLocal() as db:
            self.submit_form(db, tenant)
            contact = db.scalar(select(CrmContact).where(CrmContact.tenant_id == tenant.id))
            lead = self.lead(db, tenant)
            self.assertEqual(contact.name, "Maria Form")
            self.assertEqual(contact.phone_normalized, "+573001112233")
            self.assertEqual(self.stage_key(db, lead), "new")

    def test_form_submission_does_not_duplicate_existing_open_lead(self):
        tenant, _ = self.seed_tenant_agent()
        with SessionLocal() as db:
            self.submit_form(db, tenant)
            self.submit_form(db, tenant, user_name="Maria Segunda")
            self.assertEqual(len(self.leads(db, tenant)), 1)

    def test_form_submission_creates_new_lead_after_previous_was_qualified(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            first_context = self.submit_form(db, tenant)
            first_lead = self.lead(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.ended", context=first_context, summary="Quiere cotizar una propuesta."),
                self.get_call(db, call_id),
            )
            db.refresh(first_lead)
            self.assertEqual(self.stage_key(db, first_lead), "qualified")

            second_context = self.submit_form(
                db,
                tenant,
                user_name="Maria Segunda",
                user_email="maria.segunda@test.com",
            )
            leads = self.leads(db, tenant)
            self.assertEqual(len(leads), 2)
            second_lead = db.scalar(
                select(CrmLead).where(
                    CrmLead.tenant_id == tenant.id,
                    CrmLead.context_id == second_context.context_id,
                )
            )
            self.assertIsNotNone(second_lead)
            self.assertNotEqual(second_lead.id, first_lead.id)
            self.assertEqual(self.stage_key(db, second_lead), "new")
            self.assertEqual(self.stage_key(db, first_lead), "qualified")

    def test_form_context_is_saved_with_context_id_and_form_submission_id(self):
        tenant, _ = self.seed_tenant_agent()
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            self.assertIsNotNone(call_context.context_id)
            self.assertIsNotNone(call_context.form_submission_id)
            saved = db.scalar(select(CrmCallContext).where(CrmCallContext.tenant_id == tenant.id))
            self.assertEqual(saved.context_id, call_context.context_id)
            self.assertEqual(saved.form_submission_id, call_context.form_submission_id)

    def test_form_context_can_attach_external_call_id(self):
        tenant, _ = self.seed_tenant_agent()
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            attached = CrmCallContextService(db).attach_external_call_id(tenant.id, call_context.id, "uvx-attached")
            self.assertEqual(attached.external_call_id, "uvx-attached")
            self.assertEqual(attached.status, "attached")

    def test_form_submission_persists_context_ids_on_lead(self):
        tenant, _ = self.seed_tenant_agent()
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            lead = self.lead(db, tenant)
            self.assertEqual(lead.context_id, call_context.context_id)
            self.assertEqual(lead.form_submission_id, call_context.form_submission_id)

    def test_resolver_finds_lead_by_context_id_without_phone_or_email(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, phone=None)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            lead = self.lead(db, tenant)
            found = CrmLeadResolverService(db).resolve_existing_lead_for_call(
                tenant.id,
                self.get_call(db, call_id),
                context={"context_id": call_context.context_id},
            )
            self.assertEqual(found.id, lead.id)

    def test_resolver_finds_lead_by_form_submission_id_without_phone_or_email(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, phone=None)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            lead = self.lead(db, tenant)
            found = CrmLeadResolverService(db).resolve_existing_lead_for_call(
                tenant.id,
                self.get_call(db, call_id),
                context={"form_submission_id": call_context.form_submission_id},
            )
            self.assertEqual(found.id, lead.id)

    def test_call_started_moves_existing_lead_to_contacted(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, status="in_progress")
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.started", context=call_context),
                self.get_call(db, call_id),
            )
            self.assertEqual(self.stage_key(db, self.lead(db, tenant)), "contacted")

    def test_call_started_uses_context_id_to_move_lead_to_contacted(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, status="in_progress", phone=None)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.context_only_payload("call.started", call_context),
                self.get_call(db, call_id),
            )
            self.assertEqual(self.stage_key(db, self.lead(db, tenant)), "contacted")

    def test_call_started_without_existing_lead_does_not_create_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, status="in_progress")
        with SessionLocal() as db:
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.started"),
                self.get_call(db, call_id),
            )
            self.assertEqual(len(self.leads(db, tenant)), 0)

    def test_call_joined_moves_existing_lead_to_connected(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.joined", context=call_context),
                self.get_call(db, call_id),
            )
            self.assertEqual(self.stage_key(db, self.lead(db, tenant)), "connected")

    def test_call_joined_uses_context_id_to_move_lead_to_connected(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True, phone=None)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.context_only_payload("call.joined", call_context),
                self.get_call(db, call_id),
            )
            self.assertEqual(self.stage_key(db, self.lead(db, tenant)), "connected")

    def test_call_joined_creates_lead_only_if_context_exists(self):
        tenant, agent = self.seed_tenant_agent()
        call_without_context_id = self.seed_call(tenant, agent, "uvx-empty", joined=True, phone=None)
        call_with_context_id = self.seed_call(tenant, agent, "uvx-with-context", joined=True)
        with SessionLocal() as db:
            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event(
                {"event": "call.joined", "call": {"callId": "uvx-empty"}},
                self.get_call(db, call_without_context_id),
            )
            self.assertEqual(len(self.leads(db, tenant)), 0)
            ingestion.process_ultravox_event(
                self.payload("call.joined", external_call_id="uvx-with-context", user_name="Fallback"),
                self.get_call(db, call_with_context_id),
            )
            self.assertEqual(len(self.leads(db, tenant)), 1)

    def test_call_joined_does_not_duplicate_form_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event(self.payload("call.joined", context=call_context), self.get_call(db, call_id))
            ingestion.process_ultravox_event(self.payload("call.joined", context=call_context), self.get_call(db, call_id))
            self.assertEqual(len(self.leads(db, tenant)), 1)

    def test_call_ended_reuses_existing_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.ended", context=call_context, summary="Quiere cotizar una propuesta."),
                self.get_call(db, call_id),
            )
            self.assertEqual(len(self.leads(db, tenant)), 1)
            self.assertEqual(self.stage_key(db, self.lead(db, tenant)), "qualified")

    def test_call_ended_uses_context_id_to_reuse_existing_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True, phone=None)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.context_only_payload("call.ended", call_context, summary="Quiere cotizar una propuesta."),
                self.get_call(db, call_id),
            )
            self.assertEqual(len(self.leads(db, tenant)), 1)
            self.assertEqual(self.stage_key(db, self.lead(db, tenant)), "qualified")

    def test_call_billed_does_not_create_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent)
        with SessionLocal() as db:
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.billed"),
                self.get_call(db, call_id),
            )
            self.assertEqual(len(self.leads(db, tenant)), 0)

    def test_call_ended_not_interested_moves_to_not_interested(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.ended", context=call_context, summary="El cliente dice no estoy interesado."),
                self.get_call(db, call_id),
            )
            lead = self.lead(db, tenant)
            self.assertEqual(self.stage_key(db, lead), "not_interested")

    def test_call_ended_clear_interest_moves_to_qualified(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.ended", context=call_context, summary="Me interesa, quiero cotizar."),
                self.get_call(db, call_id),
            )
            self.assertEqual(self.stage_key(db, self.lead(db, tenant)), "qualified")

    def test_call_ended_booking_intent_without_event_goes_to_qualified_with_confirm_booking(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.ended", context=call_context, summary="Quiere agendar una cita."),
                self.get_call(db, call_id),
            )
            lead = self.lead(db, tenant)
            self.assertEqual(self.stage_key(db, lead), "qualified")
            self.assertEqual(lead.next_action, "confirm_booking")

    def test_call_ended_no_signal_goes_to_follow_up(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.ended", context=call_context, summary="Cliente pidio revisar luego."),
                self.get_call(db, call_id),
            )
            self.assertEqual(self.stage_key(db, self.lead(db, tenant)), "follow_up")

    def test_voicemail_goes_to_follow_up(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True, status="voicemail")
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.ended", context=call_context, endReason="voicemail"),
                self.get_call(db, call_id),
            )
            self.assertEqual(self.stage_key(db, self.lead(db, tenant)), "follow_up")

    def test_unanswered_goes_to_follow_up(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=False, status="unanswered")
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.started", context=call_context),
                self.get_call(db, call_id),
            )
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.ended", context=call_context, endReason="unanswered"),
                self.get_call(db, call_id),
            )
            self.assertEqual(self.stage_key(db, self.lead(db, tenant)), "follow_up")

    def test_successful_crear_evento_with_event_id_moves_to_scheduled(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            payload = self.payload("call.ended", context=call_context)
            payload["call"]["toolCalls"] = [{"name": "crear_evento", "status": "success", "result": {"event_id": "evt-1"}}]
            CrmIngestionService(db).process_ultravox_event(payload, self.get_call(db, call_id))
            self.assertEqual(self.stage_key(db, self.lead(db, tenant)), "scheduled")

    def test_crear_evento_without_event_id_does_not_move_to_scheduled(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            payload = self.payload("call.ended", context=call_context)
            payload["call"]["toolCalls"] = [{"name": "crear_evento", "status": "success"}]
            CrmIngestionService(db).process_ultravox_event(payload, self.get_call(db, call_id))
            self.assertNotEqual(self.stage_key(db, self.lead(db, tenant)), "scheduled")

    def test_failed_crear_evento_does_not_move_to_scheduled(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            payload = self.payload("call.ended", context=call_context)
            payload["call"]["toolCalls"] = [{"name": "crear_evento", "status": "failed", "result": {"event_id": "evt-1"}}]
            CrmIngestionService(db).process_ultravox_event(payload, self.get_call(db, call_id))
            self.assertNotEqual(self.stage_key(db, self.lead(db, tenant)), "scheduled")

    def test_summary_mentions_agenda_without_tool_does_not_move_to_scheduled(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.ended", context=call_context, summary="Cliente quiere agendar una reunion."),
                self.get_call(db, call_id),
            )
            self.assertNotEqual(self.stage_key(db, self.lead(db, tenant)), "scheduled")

    def test_classifier_never_sets_won(self):
        classifier = CrmClassifierService()
        result = classifier.classify_after_call("answered", "Venta cerrada y pago realizado.", None, None)
        self.assertNotEqual(result.stage_key, "won")

    def test_classifier_does_not_set_lost_for_simple_rejection(self):
        classifier = CrmClassifierService()
        result = classifier.classify_after_call("answered", "No me interesa.", None, None)
        self.assertEqual(result.stage_key, "not_interested")
        self.assertNotEqual(result.stage_key, "lost")

    def test_not_interested_sets_status_lost(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.payload("call.ended", context=call_context, summary="No volver a llamar, no me interesa."),
                self.get_call(db, call_id),
            )
            self.assertEqual(self.lead(db, tenant).status, "lost")

    def test_manual_stage_change_can_move_to_won(self):
        tenant, _ = self.seed_tenant_agent()
        with SessionLocal() as db:
            self.submit_form(db, tenant)
            lead = self.lead(db, tenant)
            changed = CrmLeadService(db).change_stage(tenant.id, lead.id, "won", "Cierre manual")
            self.assertEqual(self.stage_key(db, changed), "won")
            self.assertEqual(changed.status, "won")

    def test_manual_stage_change_can_move_to_lost(self):
        tenant, _ = self.seed_tenant_agent()
        with SessionLocal() as db:
            self.submit_form(db, tenant)
            lead = self.lead(db, tenant)
            changed = CrmLeadService(db).change_stage(tenant.id, lead.id, "lost", "Descartado manual")
            self.assertEqual(self.stage_key(db, changed), "lost")
            self.assertEqual(changed.status, "lost")

    def test_form_started_joined_ended_billed_results_in_one_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            ingestion = CrmIngestionService(db)
            for payload in (
                self.payload("call.started", context=call_context),
                self.payload("call.joined", context=call_context),
                self.payload("call.ended", context=call_context, summary="Quiere cotizar una propuesta."),
                self.payload("call.billed", context=call_context, billedDuration="60s"),
            ):
                ingestion.process_ultravox_event(payload, self.get_call(db, call_id))
            self.assertEqual(len(self.leads(db, tenant)), 1)
            self.assertEqual(self.stage_key(db, self.lead(db, tenant)), "qualified")

    def test_duplicate_webhooks_do_not_duplicate_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            ingestion = CrmIngestionService(db)
            payload = self.payload("call.joined", context=call_context)
            ingestion.process_ultravox_event(payload, self.get_call(db, call_id))
            ingestion.process_ultravox_event(payload, self.get_call(db, call_id))
            self.assertEqual(len(self.leads(db, tenant)), 1)

    def test_duplicate_context_id_does_not_duplicate_lead(self):
        tenant, _ = self.seed_tenant_agent()
        with SessionLocal() as db:
            self.submit_form(db, tenant, context_id="ctx-dup", user_phone="3001112233")
            self.submit_form(db, tenant, context_id="ctx-dup", user_phone="3009998888", user_email="otra@test.com")
            self.assertEqual(len(self.leads(db, tenant)), 1)

    def test_duplicate_form_submission_id_does_not_duplicate_lead(self):
        tenant, _ = self.seed_tenant_agent()
        with SessionLocal() as db:
            self.submit_form(db, tenant, form_submission_id="form-dup", user_phone="3001112233")
            self.submit_form(db, tenant, form_submission_id="form-dup", user_phone="3009998888", user_email="otra@test.com")
            self.assertEqual(len(self.leads(db, tenant)), 1)

    def test_context_id_is_not_overwritten_by_different_payload_context(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True, phone=None)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant, context_id="ctx-original")
            original_lead = self.lead(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.context_only_payload("call.started", call_context),
                self.get_call(db, call_id),
            )
            payload = self.context_only_payload("call.joined", call_context)
            payload["call"]["metadata"]["context_id"] = "ctx-different"
            CrmIngestionService(db).process_ultravox_event(
                payload,
                self.get_call(db, call_id),
            )
            db.refresh(original_lead)
            self.assertEqual(original_lead.context_id, "ctx-original")
            self.assertEqual(len(self.leads(db, tenant)), 1)

    def test_form_submission_id_is_not_overwritten_by_different_payload_submission(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True, phone=None)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant, form_submission_id="form-original")
            original_lead = self.lead(db, tenant)
            CrmIngestionService(db).process_ultravox_event(
                self.context_only_payload("call.started", call_context),
                self.get_call(db, call_id),
            )
            payload = self.context_only_payload("call.joined", call_context)
            payload["call"]["metadata"]["form_submission_id"] = "form-different"
            CrmIngestionService(db).process_ultravox_event(
                payload,
                self.get_call(db, call_id),
            )
            db.refresh(original_lead)
            self.assertEqual(original_lead.form_submission_id, "form-original")
            self.assertEqual(len(self.leads(db, tenant)), 1)

    def test_events_out_of_order_do_not_duplicate_lead(self):
        tenant, agent = self.seed_tenant_agent()
        call_id = self.seed_call(tenant, agent, joined=True)
        with SessionLocal() as db:
            call_context = self.submit_form(db, tenant)
            ingestion = CrmIngestionService(db)
            ingestion.process_ultravox_event(
                self.payload("call.ended", context=call_context, summary="Quiere cotizar."),
                self.get_call(db, call_id),
            )
            ingestion.process_ultravox_event(
                self.payload("call.joined", context=call_context),
                self.get_call(db, call_id),
            )
            self.assertEqual(len(self.leads(db, tenant)), 1)


if __name__ == "__main__":
    unittest.main()
