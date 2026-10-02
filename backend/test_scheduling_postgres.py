r"""Real PostgreSQL behaviour of Scheduling: Round Robin allocation under
concurrency, booking lifecycle against real FKs/JSON, cancel races.

SQLite cannot prove these: they depend on row locks and on READ COMMITTED
visibility. Provider calls (Google, Cal.com) are fakes; every database
interaction is real. This is NOT a real Google Calendar / Cal.com E2E.

Run only against a dedicated disposable database:

    $env:VOICE_RUNTIME_TEST_DATABASE_URL = "postgresql+psycopg://serviai:serviai@localhost:5432/serviai_voice_runtime_test"
    .\.venv\Scripts\python.exe -m unittest test_scheduling_postgres -v
"""

import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, BrokenBarrierError, Event
from unittest.mock import patch
from uuid import uuid4

from cryptography.fernet import Fernet

DATABASE_URL = os.environ.get("VOICE_RUNTIME_TEST_DATABASE_URL")
if DATABASE_URL:
    os.environ.setdefault("ULTRAVOX_API_KEY", "test")
    os.environ.setdefault("INTEGRATIONS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    os.environ["DATABASE_URL"] = DATABASE_URL

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.crm import CrmContact, CrmLead, CrmPipelineStage
from app.models.identity import Tenant
from app.modules.scheduling.application.booking_service import BookingService
from app.modules.scheduling.application.ports import SchedulingPorts
from app.modules.scheduling.application.resource_service import SchedulingResourceService
from app.modules.scheduling.domain.contracts import BookingCustomer, CreateBookingCommand
from app.modules.scheduling.infrastructure.models import (
    CrmBooking,
    CrmBookingEvent,
    TenantBookingConfig,
    TenantGoogleCalendar,
    TenantGoogleCalendarConnection,
    TenantSchedulingResource,
    TenantSchedulingResourceCalendar,
)

_local = threading.local()
_ORIG_COMMIT = Session.commit


class FakeCustomerPort:
    def __init__(self, customer: BookingCustomer) -> None:
        self.customer = customer

    def get_booking_customer(self, tenant_id: str, lead_id: str) -> BookingCustomer:
        return self.customer


class RecordingActivityPort:
    def __init__(self) -> None:
        self.activities: list[str] = []

    def record_activity(self, **kwargs) -> None:
        self.activities.append(kwargs["activity_type"])


class RecordingEventPort:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def publish_booking_event(self, *, tenant_id: str, booking_id: str, event_type: str) -> None:
        self.events.append((booking_id, event_type))


@unittest.skipUnless(
    DATABASE_URL,
    "VOICE_RUNTIME_TEST_DATABASE_URL not set; skipping real PostgreSQL scheduling tests",
)
class SchedulingPostgresTests(unittest.TestCase):
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

    # -- seed -----------------------------------------------------------------
    def _tenant(self) -> str:
        with self.SessionLocal() as db:
            tenant = Tenant(name="Scheduling PG", slug=f"sched-{uuid4().hex[:8]}")
            db.add(tenant)
            db.commit()
            return tenant.id

    def _resources(self, tenant_id: str, count: int) -> list[str]:
        ids = []
        with self.SessionLocal() as db:
            for index in range(count):
                resource = TenantSchedulingResource(
                    tenant_id=tenant_id,
                    name=f"Agent {index}",
                    team="sales",
                    priority=1,
                    # Equal rank: only last_assigned_at / count decide.
                    created_at=datetime.now(UTC) + timedelta(milliseconds=index),
                )
                db.add(resource)
                db.flush()
                ids.append(resource.id)
            db.commit()
        return ids

    # -- helpers ----------------------------------------------------------------
    def _gated_commit(self, gate: Barrier):
        orig = _ORIG_COMMIT

        def commit(session, *args, **kwargs):
            if getattr(_local, "gate", False):
                # Hold the first transaction open until the second has had the
                # chance to read the same state (or give up: with row locking the
                # second one is blocked and cannot reach the gate).
                try:
                    gate.wait(timeout=1.5)
                except BrokenBarrierError:
                    pass
            return orig(session, *args, **kwargs)

        return commit

    def _select(self, tenant_id: str, *, gated: bool) -> str | None:
        _local.gate = gated
        try:
            with self.SessionLocal() as db:
                chosen, _ = SchedulingResourceService(db).select_resource_round_robin(
                    tenant_id=tenant_id, team_name="sales"
                )
                return chosen.id if chosen else None
        finally:
            _local.gate = False

    # -- Round Robin ---------------------------------------------------------------
    def test_two_simultaneous_allocations_pick_different_resources(self) -> None:
        tenant_id = self._tenant()
        ids = self._resources(tenant_id, 2)
        gate = Barrier(2)
        with patch.object(Session, "commit", self._gated_commit(gate)):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(self._select, tenant_id, gated=True) for _ in range(2)]
                chosen = [f.result(timeout=60) for f in futures]
        self.assertEqual(sorted(chosen), sorted(ids), "Round Robin handed the same resource to both requests")
        with self.SessionLocal() as db:
            counts = sorted(db.scalars(select(TenantSchedulingResource.total_assigned_count)).all())
        self.assertEqual(counts, [1, 1])

    def test_assignment_counter_never_loses_an_update(self) -> None:
        tenant_id = self._tenant()
        self._resources(tenant_id, 3)
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(self._select, tenant_id, gated=False) for _ in range(6)]
            [f.result(timeout=60) for f in futures]
        with self.SessionLocal() as db:
            counts = sorted(db.scalars(select(TenantSchedulingResource.total_assigned_count)).all())
        self.assertEqual(sum(counts), 6, f"lost updates: {counts}")
        self.assertEqual(counts, [2, 2, 2], f"allocation was not distributed: {counts}")

    def test_no_resource_free_returns_none_and_releases_the_lock(self) -> None:
        tenant_id = self._tenant()  # no resources at all
        self.assertIsNone(self._select(tenant_id, gated=False))

    # -- Google FreeBusy never runs under an allocation lock -----------------------------------
    SLOT = datetime(2030, 1, 7, 15, 0, tzinfo=UTC)  # a Monday; resources have no working-hours limits

    def _resources_with_blocking_calendars(self, tenant_id: str, count: int) -> list[str]:
        ids = self._resources(tenant_id, count)
        with self.SessionLocal() as db:
            connection = TenantGoogleCalendarConnection(tenant_id=tenant_id, status="connected", calendar_id="primary")
            db.add(connection)
            db.flush()
            for index, resource_id in enumerate(ids):
                calendar = TenantGoogleCalendar(
                    tenant_id=tenant_id, connection_id=connection.id, google_calendar_id=f"cal{index}@example.com",
                    is_blocking=True, is_booking_destination=True,
                )
                db.add(calendar)
                db.flush()
                db.add(
                    TenantSchedulingResourceCalendar(
                        tenant_id=tenant_id, resource_id=resource_id, calendar_id=calendar.id,
                        is_blocking=True, is_destination=True,
                    )
                )
            db.commit()
        return ids

    def _allocate(self, tenant_id: str, google) -> str | None:
        with self.SessionLocal() as db:
            chosen, _ = SchedulingResourceService(db, google_service=google).select_resource_round_robin(
                tenant_id=tenant_id, team_name="sales", slot_start=self.SLOT
            )
            return chosen.id if chosen else None

    def test_freebusy_runs_while_no_allocation_row_lock_is_held(self) -> None:
        from sqlalchemy import text

        tenant_id = self._tenant()
        ids = self._resources_with_blocking_calendars(tenant_id, 2)
        observed: list[str] = []
        engine = self.engine

        class ProbingGoogle:
            def get_freebusy_intervals(self, **kwargs):
                # Another connection tries to lock the very same rows without
                # waiting: it only succeeds if this request holds no row lock.
                with engine.connect() as other:
                    try:
                        other.execute(
                            text("SELECT id FROM tenant_scheduling_resources WHERE tenant_id = :t FOR UPDATE NOWAIT"),
                            {"t": tenant_id},
                        ).all()
                        observed.append("free")
                    except Exception:
                        observed.append("LOCKED")
                return []

        chosen = self._allocate(tenant_id, ProbingGoogle())
        self.assertIn(chosen, ids)
        self.assertEqual(observed, ["free", "free"], "FreeBusy ran while resource rows were locked")

    def test_slow_freebusy_does_not_block_another_allocation(self) -> None:
        tenant_id = self._tenant()
        ids = self._resources_with_blocking_calendars(tenant_id, 2)
        in_freebusy, release = Event(), Event()

        class SlowGoogle:
            def __init__(self) -> None:
                self.first = True

            def get_freebusy_intervals(self, **kwargs):
                if self.first:  # only request A is slow
                    self.first = False
                    in_freebusy.set()
                    release.wait(timeout=30)
                return []

        class FastGoogle:
            def get_freebusy_intervals(self, **kwargs):
                return []

        with ThreadPoolExecutor(max_workers=2) as pool:
            slow = pool.submit(self._allocate, tenant_id, SlowGoogle())
            self.assertTrue(in_freebusy.wait(timeout=30), "request A never reached FreeBusy")
            fast = pool.submit(self._allocate, tenant_id, FastGoogle())
            try:
                # B must finish while A is still stuck in the network call.
                fast_choice = fast.result(timeout=15)
            finally:
                release.set()
            slow_choice = slow.result(timeout=30)
        self.assertFalse(slow.running())
        self.assertEqual(sorted([fast_choice, slow_choice]), sorted(ids))
        with self.SessionLocal() as db:
            counts = sorted(db.scalars(select(TenantSchedulingResource.total_assigned_count)).all())
        self.assertEqual(counts, [1, 1])

    def test_both_requests_checked_the_same_candidates_but_the_post_lock_ranking_decides(self) -> None:
        """Both requests see [A, B] as free (stale pre-lock view); the second one
        must still pick the resource the first did not."""
        tenant_id = self._tenant()
        ids = self._resources_with_blocking_calendars(tenant_id, 2)
        gate = Barrier(2)

        class MeetingPointGoogle:
            def get_freebusy_intervals(self, **kwargs):
                try:
                    gate.wait(timeout=5)
                except BrokenBarrierError:
                    pass
                return []

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self._allocate, tenant_id, MeetingPointGoogle()) for _ in range(2)]
            chosen = [f.result(timeout=60) for f in futures]
        self.assertEqual(sorted(chosen), sorted(ids))

    # -- Booking lifecycle (real FKs / JSON) -----------------------------------------
    def _lead(self, tenant_id: str) -> BookingCustomer:
        with self.SessionLocal() as db:
            stage = CrmPipelineStage(tenant_id=tenant_id, key="new", name="Nuevo", position=1, is_default=True)
            contact = CrmContact(tenant_id=tenant_id, name="Pedro", email="p@example.com", phone="+573001112233")
            db.add_all([stage, contact])
            db.flush()
            lead = CrmLead(tenant_id=tenant_id, contact_id=contact.id, current_stage_id=stage.id, status="open")
            db.add(lead)
            db.commit()
            return BookingCustomer(
                lead_id=lead.id, contact_id=contact.id, tenant_id=tenant_id,
                name="Pedro", email="p@example.com", phone="+573001112233",
            )

    def _calcom_config(self, tenant_id: str) -> None:
        with self.SessionLocal() as db:
            db.add(
                TenantBookingConfig(
                    tenant_id=tenant_id, provider="calcom", status="active",
                    calendar_mode="cal_managed", cal_api_key_encrypted="enc", default_event_type_id=1,
                    default_timezone="America/Bogota", default_length_minutes=30,
                )
            )
            db.commit()

    def _service(self, db, customer, activity=None, events=None, client=None) -> BookingService:
        ports = SchedulingPorts(
            customer=FakeCustomerPort(customer),
            activity=activity or RecordingActivityPort(),
            events=events or RecordingEventPort(),
        )
        service = BookingService(db, ports=ports, calcom_client=client)
        # decrypting the fake key would need the real secret manager
        service.config_service.to_client_config = lambda config: __import__(
            "app.modules.scheduling.infrastructure.calcom.client", fromlist=["CalComClientConfig"]
        ).CalComClientConfig(
            api_key="k", api_version="2024-08-13", event_type_id=1, timezone="America/Bogota",
            language="es", organization_slug=None, username=None, team_slug=None, event_type_slug=None,
        )
        return service

    def test_booking_lifecycle_create_cancel_on_real_postgres(self) -> None:
        tenant_id = self._tenant()
        customer = self._lead(tenant_id)
        self._calcom_config(tenant_id)

        class FakeCalCom:
            def __init__(self) -> None:
                self.cancels = 0

            def create_booking(self, config, payload):
                return {"data": {"id": 7, "uid": "uid-7", "status": "accepted", "meetingUrl": "https://meet/x"}}

            def cancel_booking(self, config, uid):
                self.cancels += 1
                return {"data": {"id": 7, "uid": uid, "status": "cancelled"}}

        client = FakeCalCom()
        events = RecordingEventPort()
        with self.SessionLocal() as db:
            service = self._service(db, customer, events=events, client=client)
            booking = service.create_lead_booking(
                tenant_id=tenant_id,
                lead_id=customer.lead_id,
                command=CreateBookingCommand(
                    start="2026-12-01T15:00:00Z", attendee_name="Pedro", attendee_email="p@example.com"
                ),
            )
            booking_id = booking.id
            self.assertEqual(booking.status, "accepted")
            service.cancel_lead_booking(tenant_id=tenant_id, booking_id=booking_id)
        with self.SessionLocal() as db:
            row = db.get(CrmBooking, booking_id)
            kinds = sorted(db.scalars(select(CrmBookingEvent.event_type).where(CrmBookingEvent.booking_id == booking_id)))
        self.assertEqual(row.status, "cancelled")
        self.assertEqual(kinds, ["booking_cancelled", "booking_created", "booking_requested"])
        self.assertEqual([e for _, e in events.events], ["booking.created", "booking.cancelled"])

    def test_concurrent_double_cancel_ends_cancelled_without_errors(self) -> None:
        tenant_id = self._tenant()
        customer = self._lead(tenant_id)
        self._calcom_config(tenant_id)
        with self.SessionLocal() as db:
            booking = CrmBooking(
                tenant_id=tenant_id, lead_id=customer.lead_id, contact_id=customer.contact_id,
                provider="calcom", provider_booking_uid="uid-9", status="accepted",
                start_at=datetime(2026, 12, 2, 15, tzinfo=UTC), attendee_name="Pedro", attendee_email="p@example.com",
            )
            db.add(booking)
            db.commit()
            booking_id = booking.id

        class FakeCalCom:
            def cancel_booking(self, config, uid):
                return {"data": {"id": 9, "uid": uid, "status": "cancelled"}}

        barrier = Barrier(2)

        def cancel():
            barrier.wait(timeout=30)
            with self.SessionLocal() as db:
                return self._service(db, customer, client=FakeCalCom()).cancel_lead_booking(
                    tenant_id=tenant_id, booking_id=booking_id
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [f.result(timeout=60) for f in [pool.submit(cancel) for _ in range(2)]]
        self.assertTrue(all(r["status"] == "success" for r in results))
        with self.SessionLocal() as db:
            self.assertEqual(db.get(CrmBooking, booking_id).status, "cancelled")
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmBooking)), 1)


if __name__ == "__main__":
    unittest.main()
