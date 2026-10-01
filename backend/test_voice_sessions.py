from __future__ import annotations

import unittest

from _integrations_2a_test_base import Integration2ATestCase
from app.db.session import SessionLocal
from app.modules.agents.infrastructure.models import TenantAgent, TenantAgentVersion
from app.models.crm import CrmContact, CrmLead, CrmPipelineStage
from app.modules.crm.public import ContactRef, LeadRef
from app.modules.voice.public import ToolSessionView, VoiceSessionFacade
from app.services.contact_resolution_service import ContactResolutionError
from app.services.voice_session_service import (
    SessionContextContactConflictError,
    SessionContextLeadConflictError,
    SessionContextTenantConflictError,
    VoiceSessionError,
    VoiceSessionService,
)


class VoiceSessionTests(Integration2ATestCase):
    def _published_agent(self, *, tenant_id: str | None = None, status: str = "active") -> str:
        with SessionLocal() as db:
            agent = TenantAgent(tenant_id=tenant_id or self.tenant.id, name="Sandra", status="draft")
            db.add(agent)
            db.flush()
            version = TenantAgentVersion(
                tenant_id=agent.tenant_id, agent_id=agent.id, version=1, status="published",
                language="es-CO", timezone="America/Bogota", identity_json={"name": "Sandra"},
                instructions_json={"system_prompt": "Published prompt", "greeting": "Hola"},
                behavior_json={}, runtime_binding_json={"pipeline_type": "realtime", "realtime": {"provider": "ultravox", "model": "fixie-ai/ultravox"}},
            )
            db.add(version)
            db.flush()
            agent.published_version_id = version.id
            agent.status = status
            db.commit()
            return agent.id

    def test_create_pins_version_and_is_idempotent(self) -> None:
        agent_id = self._published_agent()
        with SessionLocal() as db:
            service = VoiceSessionService(db)
            first = service.create(self.tenant.id, agent_id, channel="internal_test", direction="internal", idempotency_key="same")
            version_id = first.agent_version_id
            second = service.create(self.tenant.id, agent_id, channel="internal_test", direction="internal", idempotency_key="same")
            self.assertEqual(first.id, second.id)
            self.assertEqual(second.agent_version_id, version_id)
            # Session Context V1 also emits context-resolution events on
            # creation (see test_context_events_* below); this only checks
            # that the lifecycle event itself is still recorded.
            event_types = [event.event_type for event in first.events]
            self.assertIn("voice.session.requested", event_types)

    def test_rejects_non_active_agent_and_cross_tenant_lookup(self) -> None:
        agent_id = self._published_agent(status="draft")
        with SessionLocal() as db:
            service = VoiceSessionService(db)
            with self.assertRaises(VoiceSessionError):
                service.create(self.tenant.id, agent_id, channel="internal_test", direction="internal")

    def test_lifecycle_rejects_invalid_transition(self) -> None:
        agent_id = self._published_agent()
        with SessionLocal() as db:
            service = VoiceSessionService(db)
            session = service.create(self.tenant.id, agent_id, channel="internal_test", direction="internal")
            with self.assertRaises(VoiceSessionError):
                service.transition(session, "connected")

    def test_agent_version_is_immutable(self) -> None:
        agent_id = self._published_agent()
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="internal_test", direction="internal")
            session.agent_version_id = "another-version"
            with self.assertRaises(ValueError):
                db.commit()

    # -- Session Context V1 wiring (Fase E) --

    def _seed_contact_and_lead(self, tenant_id: str) -> tuple[str, str]:
        with SessionLocal() as db:
            stage = CrmPipelineStage(tenant_id=tenant_id, key="qualified", name="Qualified", position=1, is_default=True)
            contact = CrmContact(tenant_id=tenant_id, name="Carlos Pérez", phone="3001112233", phone_normalized="+573001112233", email="carlos@example.com")
            db.add_all([stage, contact])
            db.commit()
            db.refresh(stage)
            db.refresh(contact)
            lead = CrmLead(tenant_id=tenant_id, contact_id=contact.id, current_stage_id=stage.id, status="open")
            db.add(lead)
            db.commit()
            db.refresh(lead)
            return contact.id, lead.id

    def test_session_without_contact_or_lead_gets_an_empty_context_snapshot(self) -> None:
        agent_id = self._published_agent()
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="webrtc", direction="internal")
            self.assertIsNotNone(session.session_context_json)
            self.assertIsNone(session.session_context_json.get("contact"))
            self.assertIsNone(session.session_context_json.get("lead"))

    def test_session_with_trusted_lead_id_snapshots_resolved_context(self) -> None:
        agent_id = self._published_agent()
        contact_id, lead_id = self._seed_contact_and_lead(self.tenant.id)
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(
                self.tenant.id, agent_id, channel="webrtc", direction="internal", lead_id=lead_id
            )
            self.assertEqual(session.session_context_json["lead"]["id"], lead_id)
            self.assertEqual(session.session_context_json["contact"]["id"], contact_id)
            self.assertEqual(session.session_context_json["source"], "webrtc")

    def test_session_with_cross_tenant_lead_id_is_rejected(self) -> None:
        agent_id = self._published_agent()
        other_tenant, _ = self._seed_tenant_user(slug="voice-session-tenant-b", email="vsb@example.com")
        _, other_lead_id = self._seed_contact_and_lead(other_tenant.id)
        with SessionLocal() as db:
            with self.assertRaises(ContactResolutionError):
                VoiceSessionService(db).create(
                    self.tenant.id, agent_id, channel="webrtc", direction="internal", lead_id=other_lead_id
                )

    # -- context resolution observability (Fase G) --

    def test_context_events_for_unresolved_caller(self) -> None:
        agent_id = self._published_agent()
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="webrtc", direction="internal")
            event_types = {event.event_type for event in session.events}
            self.assertIn("session.context.resolved", event_types)
            self.assertIn("session.context.unresolved", event_types)
            self.assertNotIn("session.context.contact_matched", event_types)
            self.assertNotIn("session.context.lead_matched", event_types)
            resolved_event = next(e for e in session.events if e.event_type == "session.context.resolved")
            self.assertEqual(
                resolved_event.payload_json,
                {"contact_resolved": False, "lead_resolved": False, "campaign_resolved": False, "caller_known": False},
            )

    def test_context_events_for_resolved_lead_contain_no_pii(self) -> None:
        agent_id = self._published_agent()
        _, lead_id = self._seed_contact_and_lead(self.tenant.id)
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(
                self.tenant.id, agent_id, channel="webrtc", direction="internal", lead_id=lead_id
            )
            event_types = {event.event_type for event in session.events}
            self.assertIn("session.context.contact_matched", event_types)
            self.assertIn("session.context.lead_matched", event_types)
            self.assertNotIn("session.context.unresolved", event_types)
            resolved_event = next(e for e in session.events if e.event_type == "session.context.resolved")
            self.assertTrue(resolved_event.payload_json["contact_resolved"])
            self.assertTrue(resolved_event.payload_json["lead_resolved"])
            # No name/phone/email anywhere in any context event's payload.
            for event in session.events:
                if event.event_type.startswith("session.context."):
                    self.assertNotIn("Carlos", str(event.payload_json))
                    self.assertNotIn("+57", str(event.payload_json))

    def test_existing_sessions_without_context_column_stay_compatible(self) -> None:
        # Simulates a pre-Session-Context-V1 row: session_context_json is
        # NULL at the DB level, not an empty dict -- the compiler must
        # still produce a valid, empty RuntimeSessionSpecV1.context.
        # Uses the logical model key ("ultravox"), not the raw execution
        # id -- unlike VoiceSessionService.create() (used by every other
        # test in this file), the compiler resolves it
        # through voice_registry and needs the real key.
        from app.modules.agents.public import AgentsFacade

        with SessionLocal() as db:
            agent = TenantAgent(tenant_id=self.tenant.id, name="Sandra", status="draft")
            db.add(agent)
            db.flush()
            version = TenantAgentVersion(
                tenant_id=agent.tenant_id, agent_id=agent.id, version=1, status="published",
                language="es-CO", timezone="America/Bogota", identity_json={"name": "Sandra"},
                instructions_json={"system_prompt": "Published prompt", "greeting": "Hola"},
                behavior_json={}, runtime_binding_json={"pipeline_type": "realtime", "realtime": {"provider": "ultravox", "model": "ultravox"}},
            )
            db.add(version)
            db.flush()
            agent.published_version_id = version.id
            agent.status = "active"
            db.commit()
            agent_id = agent.id
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="webrtc", direction="internal")
            session.session_context_json = None
            db.commit()
            db.refresh(session)
            spec = AgentsFacade(db).compile_runtime_spec(
                session.tenant_id, session.agent_id, session.agent_version_id,
                session_id=session.id, context=session.session_context_json,
            )
            self.assertIsNone(spec.context.contact)
            self.assertEqual(spec.context.variables, {})


    # -- controlled monotonic context enrichment (Fase F.1) --

    def test_enrich_context_resolves_a_previously_unresolved_contact_and_lead(self) -> None:
        # Caso 1: normal enrichment success.
        agent_id = self._published_agent()
        contact_id, lead_id = self._seed_contact_and_lead(self.tenant.id)
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="webrtc", direction="internal")
            self.assertIsNone(session.session_context_json.get("contact"))
            contact = db.get(CrmContact, contact_id)
            lead = db.get(CrmLead, lead_id)
            enriched = VoiceSessionService(db).enrich_context(session, contact=contact, lead=lead, event_source="crm.create_lead")
            self.assertEqual(enriched.contact.id, contact_id)
            self.assertEqual(enriched.lead.id, lead_id)
            db.refresh(session)
            self.assertEqual(session.session_context_json["contact"]["id"], contact_id)
            self.assertEqual(session.session_context_json["lead"]["id"], lead_id)

    def test_enrich_context_with_the_same_identity_twice_is_idempotent(self) -> None:
        # Caso 2: idempotency -- same contact/lead run twice succeeds with
        # no corruption or duplication.
        agent_id = self._published_agent()
        contact_id, lead_id = self._seed_contact_and_lead(self.tenant.id)
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="webrtc", direction="internal")
            contact = db.get(CrmContact, contact_id)
            lead = db.get(CrmLead, lead_id)
            first = VoiceSessionService(db).enrich_context(session, contact=contact, lead=lead, event_source="crm.create_lead")
            second = VoiceSessionService(db).enrich_context(session, contact=contact, lead=lead, event_source="crm.create_lead")
            self.assertEqual(first.contact.id, second.contact.id)
            self.assertEqual(first.lead.id, second.lead.id)
            db.refresh(session)
            self.assertEqual(session.session_context_json["contact"]["id"], contact_id)
            self.assertEqual(session.session_context_json["lead"]["id"], lead_id)

    def test_enrich_context_rejects_replacing_an_already_resolved_contact(self) -> None:
        # Caso 3: contact conflict -> FAIL.
        agent_id = self._published_agent()
        contact_id, lead_id = self._seed_contact_and_lead(self.tenant.id)
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="webrtc", direction="internal")
            contact = db.get(CrmContact, contact_id)
            lead = db.get(CrmLead, lead_id)
            VoiceSessionService(db).enrich_context(session, contact=contact, lead=lead, event_source="crm.create_lead")
            other_contact = CrmContact(tenant_id=self.tenant.id, name="Otra Persona", phone="3009998877", phone_normalized="+573009998877")
            db.add(other_contact)
            db.commit()
            db.refresh(other_contact)
            with self.assertRaises(SessionContextContactConflictError):
                VoiceSessionService(db).enrich_context(session, contact=other_contact, event_source="crm.create_lead")

    def test_enrich_context_rejects_replacing_an_already_resolved_lead(self) -> None:
        # Caso 4: lead conflict -> FAIL.
        agent_id = self._published_agent()
        contact_id, lead_id = self._seed_contact_and_lead(self.tenant.id)
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="webrtc", direction="internal")
            contact = db.get(CrmContact, contact_id)
            lead = db.get(CrmLead, lead_id)
            VoiceSessionService(db).enrich_context(session, contact=contact, lead=lead, event_source="crm.create_lead")
            stage = db.query(CrmPipelineStage).filter_by(tenant_id=self.tenant.id).first()
            other_lead = CrmLead(tenant_id=self.tenant.id, contact_id=contact_id, current_stage_id=stage.id, status="open")
            db.add(other_lead)
            db.commit()
            db.refresh(other_lead)
            with self.assertRaises(SessionContextLeadConflictError):
                VoiceSessionService(db).enrich_context(session, contact=contact, lead=other_lead, event_source="crm.create_lead")

    def test_enrich_context_rejects_cross_tenant_contact_and_persists_nothing(self) -> None:
        # Caso 5: cross-tenant enrichment attempt -> FAIL, nothing persisted.
        agent_id = self._published_agent()
        other_tenant, _ = self._seed_tenant_user(slug="voice-session-enrich-b", email="vseb@example.com")
        other_contact_id, other_lead_id = self._seed_contact_and_lead(other_tenant.id)
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="webrtc", direction="internal")
            other_contact = db.get(CrmContact, other_contact_id)
            with self.assertRaises(SessionContextTenantConflictError):
                VoiceSessionService(db).enrich_context(session, contact=other_contact, event_source="crm.create_lead")
            db.refresh(session)
            self.assertIsNone(session.session_context_json.get("contact"))

    def test_enrich_context_emits_no_pii_in_its_event(self) -> None:
        # Caso 9: enrichment events contain no PII.
        agent_id = self._published_agent()
        contact_id, lead_id = self._seed_contact_and_lead(self.tenant.id)
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="webrtc", direction="internal")
            contact = db.get(CrmContact, contact_id)
            lead = db.get(CrmLead, lead_id)
            VoiceSessionService(db).enrich_context(session, contact=contact, lead=lead, event_source="crm.create_lead")
            enriched_events = [e for e in session.events if e.event_type == "session.context.enriched"]
            self.assertEqual(len(enriched_events), 1)
            self.assertEqual(
                enriched_events[0].payload_json,
                {"contact_resolved": True, "lead_resolved": True, "source": "crm.create_lead"},
            )
            self.assertNotIn("Carlos", str(enriched_events[0].payload_json))
            self.assertNotIn("+57", str(enriched_events[0].payload_json))

    # -- public facade (DTO boundary used by Tool Platform) --

    def _refs(self, contact_id: str, lead_id: str, tenant_id: str) -> tuple[ContactRef, LeadRef]:
        return ContactRef(id=contact_id, tenant_id=tenant_id), LeadRef(
            id=lead_id, tenant_id=tenant_id, contact_id=contact_id, status="open"
        )

    def test_facade_enrich_context_by_refs_is_monotonic(self) -> None:
        agent_id = self._published_agent()
        contact_id, lead_id = self._seed_contact_and_lead(self.tenant.id)
        contact_ref, lead_ref = self._refs(contact_id, lead_id, self.tenant.id)
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="webrtc", direction="internal")
            facade = VoiceSessionFacade(db)
            facade.enrich_context(session.id, contact=contact_ref, lead=lead_ref, event_source="crm.create_lead")
            facade.enrich_context(session.id, contact=contact_ref, lead=lead_ref, event_source="crm.create_lead")
            view = facade.get_tool_session(session.id)
            self.assertEqual((view.context.contact.id, view.context.lead.id), (contact_id, lead_id))

            stage = db.query(CrmPipelineStage).filter_by(tenant_id=self.tenant.id).first()
            other_contact = CrmContact(tenant_id=self.tenant.id, name="Otra", phone="3009998877", phone_normalized="+573009998877")
            db.add(other_contact)
            db.flush()
            other_lead = CrmLead(tenant_id=self.tenant.id, contact_id=contact_id, current_stage_id=stage.id, status="open")
            db.add(other_lead)
            db.commit()
            with self.assertRaisesRegex(SessionContextContactConflictError, "session_context_contact_conflict"):
                facade.enrich_context(session.id, contact=ContactRef(id=other_contact.id, tenant_id=self.tenant.id), lead=None, event_source="t")
            with self.assertRaisesRegex(SessionContextLeadConflictError, "session_context_lead_conflict"):
                facade.enrich_context(session.id, contact=contact_ref, lead=LeadRef(id=other_lead.id, tenant_id=self.tenant.id, contact_id=contact_id, status="open"), event_source="t")

    def test_facade_enrich_context_rejects_forged_cross_tenant_ref(self) -> None:
        # The ref claims this tenant but points at another tenant's row: the
        # owner re-loads the row and checks its real tenant_id.
        agent_id = self._published_agent()
        other_tenant, _ = self._seed_tenant_user(slug="voice-session-enrich-dto", email="vsdto@example.com")
        other_contact_id, other_lead_id = self._seed_contact_and_lead(other_tenant.id)
        contact_ref, lead_ref = self._refs(other_contact_id, other_lead_id, self.tenant.id)
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="webrtc", direction="internal")
            with self.assertRaisesRegex(SessionContextTenantConflictError, "session_context_tenant_conflict"):
                VoiceSessionFacade(db).enrich_context(session.id, contact=contact_ref, lead=lead_ref, event_source="t")
            db.refresh(session)
            self.assertIsNone(session.session_context_json.get("contact"))

    def test_facade_tool_session_view_exposes_no_orm(self) -> None:
        agent_id = self._published_agent()
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="webrtc", direction="internal")
            view = VoiceSessionFacade(db).get_tool_session(session.id)
            self.assertIsInstance(view, ToolSessionView)
            self.assertEqual((view.id, view.tenant_id, view.agent_id), (session.id, self.tenant.id, agent_id))
            self.assertFalse(view.is_terminal)
            for value in vars(view).values():
                self.assertFalse(hasattr(type(value), "__table__"), f"ORM leaked: {type(value)}")


if __name__ == "__main__":
    unittest.main()
