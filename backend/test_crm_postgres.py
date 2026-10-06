r"""Real PostgreSQL behaviour of CRM: get-or-create under concurrency, open-lead
uniqueness, timeline and call-event deduplication, tenant isolation.

SQLite cannot prove these: they depend on unique/partial indexes, ``ON CONFLICT``
and row locks. No provider is involved: every database interaction is real.

Run only against a dedicated disposable database:

    $env:VOICE_RUNTIME_TEST_DATABASE_URL = "postgresql+psycopg://serviai:serviai@localhost:5432/serviai_voice_runtime_test"
    .\.venv\Scripts\python.exe -m unittest test_crm_postgres -v
"""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

from cryptography.fernet import Fernet

DATABASE_URL = os.environ.get("VOICE_RUNTIME_TEST_DATABASE_URL")
if DATABASE_URL:
    os.environ.setdefault("ULTRAVOX_API_KEY", "test")
    os.environ.setdefault("INTEGRATIONS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    os.environ["DATABASE_URL"] = DATABASE_URL

from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (register every ORM table before create_all)
from app.db.base import Base
from app.models.analytics import Call
from app.modules.identity.infrastructure.models import Tenant
from app.modules.crm.application.activity_service import CrmActivityService
from app.modules.crm.application.call_ingestion_service import CrmIngestionService
from app.modules.crm.application.contact_service import CrmContactService
from app.modules.crm.application.lead_resolver_service import CrmLeadResolverService
from app.modules.crm.application.lead_service import CrmLeadService
from app.modules.crm.application.stage_transition_service import CrmStageTransitionService
from app.modules.crm.domain.calls import CallRef
from app.modules.crm.infrastructure.models import (
    CrmActivity,
    CrmContact,
    CrmLead,
    CrmVoiceCallEvent,
)
from app.modules.crm.public import CreateVoiceCallCommand, CrmVoiceCalls, UpdateVoiceCallCommand


@unittest.skipUnless(
    DATABASE_URL,
    "VOICE_RUNTIME_TEST_DATABASE_URL not set; skipping real PostgreSQL CRM tests",
)
class CrmPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        if cls.engine.dialect.name != "postgresql":
            raise unittest.SkipTest("VOICE_RUNTIME_TEST_DATABASE_URL must point to PostgreSQL")
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls) -> None:
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    # -- seed / helpers ---------------------------------------------------------
    def _tenant(self) -> str:
        with self.SessionLocal() as db:
            tenant = Tenant(name="CRM PG", slug=f"crm-{uuid4().hex[:8]}")
            db.add(tenant)
            db.commit()
            return tenant.id

    def _in_threads(self, *calls):
        barrier = Barrier(len(calls))

        def run(call):
            barrier.wait(timeout=30)
            try:
                return call()
            except Exception as exc:  # noqa: BLE001 - the outcome is what the test asserts on
                return exc

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            return [f.result(timeout=90) for f in [pool.submit(run, c) for c in calls]]

    def _count(self, model, **where) -> int:
        with self.SessionLocal() as db:
            stmt = select(func.count()).select_from(model)
            for key, value in where.items():
                stmt = stmt.where(getattr(model, key) == value)
            return db.scalar(stmt)

    def _contact_id(self, tenant_id: str, phone: str = "+573001112233", email: str | None = "a@example.com") -> str:
        with self.SessionLocal() as db:
            return CrmContactService(db).get_or_create_contact(tenant_id, phone, email, "Ana").id

    # -- contacts -------------------------------------------------------------------
    def test_concurrent_get_or_create_contact_by_phone_yields_one_contact(self) -> None:
        tenant_id = self._tenant()

        def create():
            with self.SessionLocal() as db:
                return CrmContactService(db).get_or_create_contact(tenant_id, "300 111 2233", None, "Ana").id

        results = self._in_threads(create, create, create)
        self.assertFalse([r for r in results if isinstance(r, Exception)], results)
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(self._count(CrmContact, tenant_id=tenant_id), 1)

    def test_concurrent_get_or_create_contact_by_email_yields_one_contact(self) -> None:
        tenant_id = self._tenant()

        def create():
            with self.SessionLocal() as db:
                return CrmContactService(db).get_or_create_contact(tenant_id, None, "same@example.com", "Ana").id

        results = self._in_threads(create, create, create)
        self.assertFalse([r for r in results if isinstance(r, Exception)], results)
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(self._count(CrmContact, tenant_id=tenant_id), 1)

    def test_same_phone_and_email_in_two_tenants_do_not_collide(self) -> None:
        t1, t2 = self._tenant(), self._tenant()
        a = self._contact_id(t1)
        b = self._contact_id(t2)
        self.assertNotEqual(a, b)
        self.assertEqual(self._count(CrmContact), 2)

    # -- leads ----------------------------------------------------------------------
    def test_concurrent_get_or_create_open_lead_yields_one_open_lead(self) -> None:
        tenant_id = self._tenant()
        contact_id = self._contact_id(tenant_id)

        def open_lead():
            with self.SessionLocal() as db:
                return CrmLeadService(db).get_or_create_open_lead(tenant_id, contact_id).id

        results = self._in_threads(open_lead, open_lead, open_lead)
        self.assertFalse([r for r in results if isinstance(r, Exception)], results)
        self.assertEqual(len(set(results)), 1, "the contact must keep a single open lead")
        self.assertEqual(self._count(CrmLead, tenant_id=tenant_id, status="open"), 1)

    # -- single open lead across ALL entry points (same contact lock) ---------------------
    def _connected(self, tenant_id: str, contact_id: str, call_id: str) -> str:
        with self.SessionLocal() as db:
            contact = db.get(CrmContact, contact_id)
            ref = CallRef(id=call_id, tenant_id=tenant_id, external_provider="ultravox", external_call_id=f"ext-{call_id}")
            return CrmLeadResolverService(db).resolve_or_create_lead_for_connected_call(
                tenant_id, ref, contact, {"interest": "x"}
            ).id

    def _new_context(self, tenant_id: str, contact_id: str, context_id: str) -> str:
        with self.SessionLocal() as db:
            contact = db.get(CrmContact, contact_id)
            return CrmLeadResolverService(db).resolve_or_create_lead_for_new_context(
                tenant_id, contact, {"context_id": context_id}
            ).id

    def _open_count(self, tenant_id: str, contact_id: str) -> int:
        return self._count(CrmLead, tenant_id=tenant_id, contact_id=contact_id, status="open")

    def test_two_connected_calls_of_the_same_contact_yield_one_open_lead(self) -> None:
        tenant_id = self._tenant()
        contact_id = self._contact_id(tenant_id)
        call_a, call_b = self._call_row(tenant_id), self._call_row(tenant_id)
        results = self._in_threads(
            lambda: self._connected(tenant_id, contact_id, call_a), lambda: self._connected(tenant_id, contact_id, call_b)
        )
        self.assertFalse([r for r in results if isinstance(r, Exception)], results)
        self.assertEqual(self._open_count(tenant_id, contact_id), 1)
        self.assertEqual(len(set(results)), 1)

    def test_two_distinct_contexts_of_the_same_contact_yield_one_open_lead(self) -> None:
        tenant_id = self._tenant()
        contact_id = self._contact_id(tenant_id)
        results = self._in_threads(
            lambda: self._new_context(tenant_id, contact_id, "context-A"),
            lambda: self._new_context(tenant_id, contact_id, "context-B"),
        )
        self.assertFalse([r for r in results if isinstance(r, Exception)], results)
        self.assertEqual(self._open_count(tenant_id, contact_id), 1)

    def test_the_same_context_id_concurrently_returns_the_same_lead_without_integrity_errors(self) -> None:
        tenant_id = self._tenant()
        contact_id = self._contact_id(tenant_id)
        results = self._in_threads(*[lambda: self._new_context(tenant_id, contact_id, "same-context")] * 3)
        self.assertFalse([r for r in results if isinstance(r, Exception)], results)
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(self._count(CrmLead, tenant_id=tenant_id, context_id="same-context"), 1)

    def test_different_entry_points_share_the_same_invariant(self) -> None:
        tenant_id = self._tenant()
        contact_id = self._contact_id(tenant_id)
        call_id = self._call_row(tenant_id)

        def service_path():
            with self.SessionLocal() as db:
                return CrmLeadService(db).get_or_create_open_lead(tenant_id, contact_id).id

        results = self._in_threads(
            service_path, lambda: self._connected(tenant_id, contact_id, call_id),
            lambda: self._new_context(tenant_id, contact_id, "ctx-mixed"),
        )
        self.assertFalse([r for r in results if isinstance(r, Exception)], results)
        self.assertEqual(self._open_count(tenant_id, contact_id), 1)
        self.assertEqual(len(set(results)), 1)

    def _progressed_lead(self, tenant_id: str, contact_id: str, stage_key: str) -> str:
        with self.SessionLocal() as db:
            lead = CrmLeadService(db).get_or_create_open_lead(tenant_id, contact_id)
            lead_id = lead.id
            CrmStageTransitionService(db).move(tenant_id, lead, stage_key, description="test", manual=True)
        return lead_id

    def test_connected_call_and_service_reuse_the_open_lead_whatever_its_stage(self) -> None:
        for stage_key in ("connected", "qualified", "follow_up"):
            with self.subTest(stage=stage_key):
                tenant_id = self._tenant()
                contact_id = self._contact_id(tenant_id)
                existing_id = self._progressed_lead(tenant_id, contact_id, stage_key)
                call_id = self._call_row(tenant_id)
                with self.SessionLocal() as db:
                    # resolver path with no call/context correlation, then the plain service path
                    contact = db.get(CrmContact, contact_id)
                    ref = CallRef(id=call_id, tenant_id=tenant_id, external_provider="x", external_call_id="no-match")
                    via_resolver = CrmLeadResolverService(db).lead_service.claim_or_create_open_lead(
                        tenant_id, contact.id, stage_key="connected", call_id=call_id,
                        find_existing=lambda: None,
                    )
                    via_service = CrmLeadService(db).claim_or_create_open_lead(tenant_id, contact_id)
                self.assertEqual((via_resolver[0].id, via_resolver[1]), (existing_id, False))
                self.assertEqual((via_service[0].id, via_service[1]), (existing_id, False))
                self.assertEqual(self._open_count(tenant_id, contact_id), 1)

    def test_form_first_keeps_its_rule_a_new_context_opens_a_new_lead_once_the_previous_progressed(self) -> None:
        tenant_id = self._tenant()
        contact_id = self._contact_id(tenant_id)
        first = self._progressed_lead(tenant_id, contact_id, "qualified")
        second = self._new_context(tenant_id, contact_id, "next-form")
        self.assertNotEqual(first, second)
        # ...and concurrent submissions of that new form still converge on one lead
        results = self._in_threads(
            lambda: self._new_context(tenant_id, contact_id, "another-form"),
            lambda: self._new_context(tenant_id, contact_id, "yet-another-form"),
        )
        self.assertFalse([r for r in results if isinstance(r, Exception)], results)
        self.assertEqual(len(set(results)), 1)

    def test_claiming_an_open_lead_for_an_unknown_contact_fails_cleanly(self) -> None:
        tenant_id, other_tenant = self._tenant(), self._tenant()
        contact_id = self._contact_id(other_tenant)
        with self.SessionLocal() as db:
            with self.assertRaisesRegex(ValueError, "Contact not found"):
                CrmLeadService(db).claim_or_create_open_lead(tenant_id, contact_id)
        self.assertEqual(self._count(CrmLead), 0)

    def test_open_lead_invariant_is_scoped_per_contact(self) -> None:
        tenant_id = self._tenant()
        c1 = self._contact_id(tenant_id, "+573001110001", "one@example.com")
        c2 = self._contact_id(tenant_id, "+573001110002", "two@example.com")
        results = self._in_threads(
            lambda: self._new_context(tenant_id, c1, "ctx-1"), lambda: self._new_context(tenant_id, c2, "ctx-2")
        )
        self.assertFalse([r for r in results if isinstance(r, Exception)], results)
        self.assertEqual((self._open_count(tenant_id, c1), self._open_count(tenant_id, c2)), (1, 1))

    # -- timeline -------------------------------------------------------------------
    def _call_row(self, tenant_id: str) -> str:
        with self.SessionLocal() as db:
            call = Call(
                tenant_id=tenant_id, external_provider="ultravox", external_call_id=f"uvx-{uuid4().hex[:8]}",
                normalized_status="in_progress", started_at=datetime.now(UTC),
            )
            db.add(call)
            db.commit()
            return call.id

    def test_activity_unique_key_is_enforced_by_the_database(self) -> None:
        tenant_id = self._tenant()
        contact_id = self._contact_id(tenant_id)
        call_id = self._call_row(tenant_id)

        def add():
            with self.SessionLocal() as db:
                CrmActivityService(db).create_activity(
                    tenant_id=tenant_id, lead_id=None, contact_id=contact_id, activity_type="call_joined",
                    title="x", call_id=call_id, deduplication_key="k",
                )

        add()
        with self.assertRaises(IntegrityError):
            add()
        self.assertEqual(self._count(CrmActivity, tenant_id=tenant_id), 1)

    def test_concurrent_ingestion_of_the_same_event_creates_one_activity(self) -> None:
        tenant_id = self._tenant()
        call_id = self._call_row(tenant_id)
        with self.SessionLocal() as db:
            external = db.get(Call, call_id).external_call_id
        payload = {
            "event": "call.joined",
            "call": {"callId": external, "customerPhone": "+573004445566", "metadata": {"name": "Ana", "interest": "x"}},
        }
        ref = CallRef(id=call_id, tenant_id=tenant_id, external_provider="ultravox", external_call_id=external,
                      customer_phone="+573004445566")

        def ingest():
            with self.SessionLocal() as db:
                CrmIngestionService(db).process_call_event(payload, ref)

        results = self._in_threads(ingest, ingest)
        self.assertFalse([r for r in results if isinstance(r, Exception)], results)
        self.assertEqual(self._count(CrmActivity, tenant_id=tenant_id, call_id=call_id, activity_type="call_joined"), 1)
        self.assertEqual(self._count(CrmLead, tenant_id=tenant_id), 1)
        self.assertEqual(self._count(CrmContact, tenant_id=tenant_id), 1)

    def test_concurrent_identical_stage_transitions_record_one_history_entry(self) -> None:
        tenant_id = self._tenant()
        contact_id = self._contact_id(tenant_id)
        with self.SessionLocal() as db:
            lead_id = CrmLeadService(db).get_or_create_open_lead(tenant_id, contact_id).id
        call_id = self._call_row(tenant_id)

        def move():
            with self.SessionLocal() as db:
                lead = db.get(CrmLead, lead_id)
                return CrmStageTransitionService(db).move_to_contacted(tenant_id, lead, call_id=call_id)

        results = self._in_threads(move, move)
        self.assertFalse([r for r in results if isinstance(r, Exception)], results)
        self.assertEqual(
            self._count(CrmActivity, tenant_id=tenant_id, lead_id=lead_id, activity_type="stage_changed"), 1
        )

    # -- voice call events ------------------------------------------------------------
    def test_concurrent_call_event_claims_insert_exactly_one_row(self) -> None:
        tenant_id = self._tenant()
        with self.SessionLocal() as db:
            call = CrmVoiceCalls(db).create(CreateVoiceCallCommand(tenant_id=tenant_id, provider="ultravox"))
            db.commit()

        def claim():
            with self.SessionLocal() as db:
                won = CrmVoiceCalls(db).claim_event(
                    tenant_id=tenant_id, voice_call_id=call.id, provider="ultravox", event_type="call.joined",
                    status="success", dedup_key="ultravox:call-1:call.joined", payload_summary={},
                    created_at=datetime.now(UTC),
                )
                db.commit()
                return won

        results = self._in_threads(claim, claim, claim)
        self.assertFalse([r for r in results if isinstance(r, Exception)], results)
        self.assertEqual(sorted(results), [False, False, True])
        self.assertEqual(self._count(CrmVoiceCallEvent, tenant_id=tenant_id), 1)

    # -- tenant isolation -------------------------------------------------------------
    def test_dedup_keys_and_phones_are_scoped_per_tenant(self) -> None:
        t1, t2 = self._tenant(), self._tenant()
        for tenant_id in (t1, t2):
            contact_id = self._contact_id(tenant_id)
            call_id = self._call_row(tenant_id)
            with self.SessionLocal() as db:
                CrmActivityService(db).create_activity(
                    tenant_id=tenant_id, lead_id=None, contact_id=contact_id, activity_type="call_joined",
                    title="x", call_id=call_id, deduplication_key="same-key",
                )
        self.assertEqual(self._count(CrmActivity), 2)


if __name__ == "__main__":
    unittest.main()
