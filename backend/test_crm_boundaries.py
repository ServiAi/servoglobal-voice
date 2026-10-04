"""CRM at its seams: DTOs (never ORM rows) across ``crm.public``, tenant isolation,
the ledger running inside the caller's transaction, ports faked (identity,
scheduling, history, analytics, provider payload parsing). Fakes + SQLite; no network."""

from __future__ import annotations

import dataclasses
import subprocess
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.modules.crm.application.call_ingestion_service import CrmIngestionService
from app.modules.crm.application.lead_service import CrmLeadService
from app.modules.crm.application.ports import CrmPorts
from app.modules.crm.application.task_service import CrmTaskService
from app.modules.crm.domain.calls import BookingDetection, CallClassification, CallRef, ContextLookup
from app.modules.crm.infrastructure.models import (
    CrmActivity,
    CrmContact,
    CrmLead,
    CrmVoiceCall,
    CrmVoiceCallEvent,
)
from app.modules.crm.public import (
    ContactProfile,
    CrmFacade,
    CrmVoiceCalls,
    LeadProfile,
    OutboundCallLedger,
    VoiceCallView,
)

BACKEND = Path(__file__).parent


class FakeAssignees:
    def __init__(self, members: set[tuple[str, str]]) -> None:
        self.members = members
        self.calls: list[tuple[str, str]] = []

    def is_active_member(self, tenant_id: str, user_id: str) -> bool:
        self.calls.append((tenant_id, user_id))
        return (tenant_id, user_id) in self.members


class FakeScheduling:
    def __init__(self) -> None:
        self.detached: list[dict] = []

    def detach_customers(self, *, tenant_id, lead_ids, contact_ids) -> None:
        self.detached.append({"tenant_id": tenant_id, "lead_ids": list(lead_ids), "contact_ids": list(contact_ids)})


class FakeHistory:
    def __init__(self) -> None:
        self.cleared: list[dict] = []
        self.forms: list[dict] = []

    def clear_references(self, *, tenant_id, lead_ids, contact_ids) -> None:
        self.cleared.append({"tenant_id": tenant_id, "lead_ids": list(lead_ids), "contact_ids": list(contact_ids)})

    def delete_form_artifacts(self, *, tenant_id, lead_ids) -> None:
        self.forms.append({"tenant_id": tenant_id, "lead_ids": list(lead_ids)})


class FakeAnalytics:
    def find_call_id(self, tenant_id, external_provider, external_call_id):
        return None


class FakePayloads:
    """A provider-neutral payload port: CRM only ever sees these normalised answers."""

    def __init__(self, *, event: str, context: dict | None = None, booking: bool = False, stage: str | None = None):
        self.event, self.context, self.booking, self.stage = event, context or {}, booking, stage
        self.seen_payloads: list[dict] = []

    def event_type(self, payload):
        self.seen_payloads.append(dict(payload))
        return self.event

    def context_lookup(self, payload):
        return ContextLookup()

    def extract_context(self, payload, call, call_context):
        return {**{"field_sources": {}}, **self.context}

    def summary_fields(self, payload, call):
        return ("resumen", "corto")

    def end_reason(self, payload, call):
        return "hangup"

    def billed_duration(self, payload):
        return None

    def detect_booking(self, payload):
        return BookingDetection(created=self.booking, event_id="evt-1" if self.booking else None)

    def classify_after_call(self, call_status, summary, short_summary, payload):
        return CallClassification(stage_key=self.stage)


def _ports(**overrides) -> CrmPorts:
    values = dict(
        assignees=FakeAssignees(set()),
        scheduling=FakeScheduling(),
        history=FakeHistory(),
        analytics=FakeAnalytics(),
        payloads=FakePayloads(event="call.updated"),
    )
    values.update(overrides)
    return CrmPorts(**values)


class CrmPublicDtoTests(Integration2ATestCase):
    def test_profiles_are_frozen_dtos_not_orm_rows(self) -> None:
        lead_id, contact_id = self.seed_lead()
        with SessionLocal() as db:
            facade = CrmFacade(db)
            lead = facade.get_lead_profile(self.tenant.id, lead_id)
            contact = facade.get_contact_profile(self.tenant.id, contact_id)
            calls = CrmVoiceCalls(db)
            call = calls.create(tenant_id=self.tenant.id, lead_id=lead_id, contact_id=contact_id, provider="x")
        self.assertIsInstance(lead, LeadProfile)
        self.assertIsInstance(contact, ContactProfile)
        self.assertIsInstance(call, VoiceCallView)
        self.assertEqual(lead.contact.email, "lead@example.com")
        for dto in (lead, contact, call):
            self.assertTrue(dataclasses.is_dataclass(dto))
            with self.assertRaises(dataclasses.FrozenInstanceError):
                dto.id = "tampered"  # type: ignore[misc]

    def test_profiles_are_tenant_scoped_but_get_lead_by_id_keeps_its_snapshot_semantics(self) -> None:
        lead_id, contact_id = self.seed_lead()
        other_tenant, _ = self._seed_tenant_user(slug="tenant-b", email="b@example.com")
        with SessionLocal() as db:
            facade = CrmFacade(db)
            self.assertIsNone(facade.get_lead_profile(other_tenant.id, lead_id))
            self.assertIsNone(facade.get_contact_profile(other_tenant.id, contact_id))
            self.assertIsNone(facade.get_open_lead_for_contact(other_tenant.id, contact_id))
            self.assertIsNone(facade.find_contact_by_phone_digits(other_tenant.id, "573001112233"))
            # By-id snapshots are deliberately NOT tenant-scoped: Voice compares tenant_id itself.
            snapshot = facade.get_lead(lead_id)
            self.assertEqual(snapshot.tenant_id, self.tenant.id)
            self.assertEqual(facade.get_contact(contact_id).tenant_id, self.tenant.id)

    def test_find_contact_by_phone_digits_matches_regardless_of_formatting(self) -> None:
        _, contact_id = self.seed_lead()
        with SessionLocal() as db:
            found = CrmFacade(db).find_contact_by_phone_digits(self.tenant.id, "57 300-111 2233")
        self.assertEqual(found.id, contact_id)

    def test_record_activity_appends_to_the_timeline_and_stage_activity_waits_for_the_caller(self) -> None:
        lead_id, contact_id = self.seed_lead()
        with SessionLocal() as db:
            facade = CrmFacade(db)
            facade.record_activity(
                tenant_id=self.tenant.id, lead_id=lead_id, contact_id=contact_id,
                activity_type="note", title="Nota", deduplication_key="k1", payload={"a": 1},
            )
            facade.stage_activity(
                tenant_id=self.tenant.id, lead_id=lead_id, contact_id=contact_id,
                activity_type="staged", title="Staged", deduplication_key="k2",
            )
            db.rollback()  # the staged entry was never committed by the caller
        with SessionLocal() as db:
            types = sorted(db.scalars(select(CrmActivity.activity_type).where(CrmActivity.lead_id == lead_id)))
            self.assertEqual(types, ["note"])
            self.assertTrue(CrmFacade(db).has_activity(self.tenant.id, lead_id, "k1"))
            self.assertFalse(CrmFacade(db).has_activity(self.tenant.id, lead_id, "k2"))
            views = CrmFacade(db).list_lead_activities(self.tenant.id, lead_id)
            self.assertEqual([v.activity_type for v in views], ["note"])
            self.assertEqual(views[0].payload, {"a": 1})


class CrmPortsTests(Integration2ATestCase):
    def test_task_assignee_is_validated_through_the_identity_port(self) -> None:
        lead_id, contact_id = self.seed_lead()
        assignees = FakeAssignees({(self.tenant.id, "member-user")})
        with SessionLocal() as db:
            service = CrmTaskService(db, assignees)
            with self.assertRaisesRegex(ValueError, "active member"):
                service.create_task(
                    tenant_id=self.tenant.id, title="Llamar", lead_id=lead_id, assigned_to_user_id="stranger"
                )
        self.assertIn((self.tenant.id, "stranger"), assignees.calls)
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmActivity)), 0)

    def test_lead_deletion_reaches_other_modules_only_through_ports(self) -> None:
        lead_id, contact_id = self.seed_lead()
        with SessionLocal() as db:
            call = CrmVoiceCalls(db).create(
                tenant_id=self.tenant.id, lead_id=lead_id, contact_id=contact_id, provider="x"
            )
            db.commit()
        scheduling, history = FakeScheduling(), FakeHistory()
        with SessionLocal() as db:
            deleted = CrmLeadService(db, scheduling=scheduling, history=history).delete_all_leads(self.tenant.id)
        self.assertEqual(deleted, 1)
        self.assertEqual(scheduling.detached[0]["lead_ids"], [lead_id])
        self.assertEqual(history.cleared[0]["contact_ids"], [contact_id])
        self.assertEqual(history.forms[0]["lead_ids"], [lead_id])
        with SessionLocal() as db:  # CRM clears its OWN voice calls directly
            row = db.get(CrmVoiceCall, call.id)
            self.assertIsNotNone(row)
            self.assertIsNone(row.lead_id)
            self.assertIsNone(row.contact_id)

    def test_ingestion_never_reads_the_provider_payload_itself(self) -> None:
        payloads = FakePayloads(
            event="call.joined", context={"phone": "+573001230000", "name": "Ana", "interest": "demo"}
        )
        raw = {"opaque": {"provider": ["shape", "crm", "must", "not", "parse"]}}
        call = CallRef(id=None, tenant_id=self.tenant.id, external_provider="p", external_call_id="ext-1")
        with SessionLocal() as db:
            CrmIngestionService(db, _ports(payloads=payloads)).process_call_event(raw, call)
        self.assertEqual(payloads.seen_payloads[0], raw)
        with SessionLocal() as db:
            lead = db.scalar(select(CrmLead).where(CrmLead.tenant_id == self.tenant.id))
            self.assertIsNotNone(lead)
            self.assertEqual(lead.interest, "demo")
            self.assertEqual(db.scalar(select(CrmContact.phone_normalized)), "+573001230000")

    def test_ingestion_errors_are_swallowed_not_raised(self) -> None:
        class Boom(FakePayloads):
            def event_type(self, payload):
                raise RuntimeError("provider payload exploded")

        with SessionLocal() as db:
            CrmIngestionService(db, _ports(payloads=Boom(event="x"))).process_call_event(
                {}, CallRef(id="c", tenant_id=self.tenant.id)
            )


class VoiceCallLedgerTests(Integration2ATestCase):
    def test_ledger_writes_run_in_the_callers_transaction_and_never_commit(self) -> None:
        with SessionLocal() as db:
            calls = CrmVoiceCalls(db)
            created = calls.create(tenant_id=self.tenant.id, provider="p", status="requested")
            calls.update(created.id, status="queued", provider_call_id="pc-1")
            self.assertEqual(calls.get(created.id).status, "queued")
            db.rollback()  # the caller decides: nothing was committed behind its back
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmVoiceCall)), 0)

    def test_update_rejects_fields_outside_the_whitelist(self) -> None:
        with SessionLocal() as db:
            calls = CrmVoiceCalls(db)
            created = calls.create(tenant_id=self.tenant.id, provider="p")
            for bad in ("tenant_id", "id", "created_at", "source_submission_id"):
                with self.assertRaises(ValueError):
                    calls.update(created.id, **{bad: "x"})

    def test_event_claim_is_idempotent_per_dedup_key(self) -> None:
        with SessionLocal() as db:
            calls = CrmVoiceCalls(db)
            created = calls.create(tenant_id=self.tenant.id, provider="p")
            kwargs = dict(
                tenant_id=self.tenant.id, voice_call_id=created.id, provider="p", event_type="call.joined",
                status="success", dedup_key="p:call-1:call.joined", payload_summary={}, created_at=datetime.now(UTC),
            )
            self.assertTrue(calls.claim_event(**kwargs))
            self.assertFalse(calls.claim_event(**kwargs))
            db.commit()
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmVoiceCallEvent)), 1)

    def test_outbound_ledger_resolves_the_target_through_the_profile_and_is_tenant_checked(self) -> None:
        lead_id, contact_id = self.seed_lead()
        other_tenant, _ = self._seed_tenant_user(slug="tenant-c", email="c@example.com")
        with SessionLocal() as db:
            target = OutboundCallLedger(db, self.tenant.id, lead_id).resolve_target()
            self.assertEqual((target.contact_id, target.lead_id), (contact_id, lead_id))
            with self.assertRaises(ValueError):
                OutboundCallLedger(db, other_tenant.id, lead_id).resolve_target()
            ledger = OutboundCallLedger(db, self.tenant.id, lead_id)
            call_id = ledger.open_call(sip_route_id=None, agent_version_id=None, to_phone="+57300", from_number="+57")
            self.assertEqual(ledger.call_state(call_id).status, "requested")
            with self.assertRaises(ValueError):  # another tenant cannot read this call
                OutboundCallLedger(db, other_tenant.id, lead_id).call_state(call_id)


class CrmPublicIsLightTests(unittest.TestCase):
    def test_importing_crm_public_loads_no_orm_framework_or_other_module(self) -> None:
        code = (
            "import sys, app.modules.crm.public; "
            "heavy = ('app.models', 'app.modules.crm.infrastructure', 'app.modules.crm.application', "
            "'app.modules.crm.api', 'app.modules.crm.wiring', 'fastapi', 'app.services', "
            "'app.modules.analytics', 'app.modules.voice', 'app.modules.telephony', "
            "'app.modules.scheduling', 'app.modules.integrations', 'app.modules.identity'); "
            "print(sorted(n for n in sys.modules if n.startswith(heavy)))"
        )
        out = subprocess.run(
            [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True
        ).stdout.strip()
        self.assertEqual(out, "[]")


if __name__ == "__main__":
    unittest.main()
