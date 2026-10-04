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
import time
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
from app.modules.scheduling.domain.booking import SLOT_BLOCKING_STATUSES
from app.modules.scheduling.domain.contracts import BookingCustomer, CreateBookingCommand
from app.modules.scheduling.domain.errors import (
    BookingOperationInProgressError,
    IdempotencyConflictError,
    SlotConflictError,
)
from app.modules.scheduling.infrastructure.google.calendar import GoogleCalendarService
from app.modules.scheduling.infrastructure.models import (
    BookingOperation,
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


    # =====================================================================
    # Booking consistency: idempotency, slot guard, idempotent cancel/reschedule
    # (Google provider replaced by a counting fake; every DB call is real)
    # =====================================================================
    START = datetime(2030, 3, 4, 15, 0, tzinfo=UTC)  # default length 30 min -> [15:00, 15:30)

    def _google_tenant(self) -> tuple[str, BookingCustomer, str]:
        tenant_id = self._tenant()
        customer = self._lead(tenant_id)
        with self.SessionLocal() as db:
            db.add(TenantGoogleCalendarConnection(tenant_id=tenant_id, status="connected", calendar_id="primary"))
            resource = TenantSchedulingResource(tenant_id=tenant_id, name="Agent R1", team="sales")
            db.add(resource)
            db.commit()
            return tenant_id, customer, resource.id

    @staticmethod
    def _fake_google():
        class FakeGoogle:
            def __init__(self) -> None:
                self.create_calls = self.delete_calls = self.patch_calls = 0
                self.create_error: Exception | None = None
                self.lock = threading.Lock()

        fake = FakeGoogle()

        def create_event(_svc, connection, payload, calendar_id=None):
            with fake.lock:
                fake.create_calls += 1
                n = fake.create_calls
            if fake.create_error:
                raise fake.create_error
            time.sleep(0.2)  # keep the race window open
            return {"id": f"ev-{n}", "htmlLink": "https://example.test/ev"}

        def delete_event(_svc, connection, event_id, calendar_id=None):
            with fake.lock:
                fake.delete_calls += 1
            time.sleep(0.2)

        def patch_event(_svc, connection, event_id, payload, calendar_id=None):
            with fake.lock:
                fake.patch_calls += 1
            time.sleep(0.2)

        patches = [
            patch.object(GoogleCalendarService, "create_event", create_event),
            patch.object(GoogleCalendarService, "delete_event", delete_event),
            patch.object(GoogleCalendarService, "patch_event", patch_event),
        ]
        return fake, patches

    def _create(self, tenant_id, customer, resource_id, *, start=None, key=None, events=None, name="Pedro"):
        command = CreateBookingCommand(
            start=(start or self.START).isoformat().replace("+00:00", "Z"),
            attendee_name=name,
            attendee_email="p@example.com",
            scheduling_resource_id=resource_id,
        )
        with self.SessionLocal() as db:
            booking = self._service(db, customer, events=events).create_lead_booking(
                tenant_id=tenant_id, lead_id=customer.lead_id, command=command, idempotency_key=key
            )
            return booking.id

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

    def _active(self, tenant_id: str) -> int:
        with self.SessionLocal() as db:
            return db.scalar(
                select(func.count()).select_from(CrmBooking).where(
                    CrmBooking.tenant_id == tenant_id, CrmBooking.status.in_(SLOT_BLOCKING_STATUSES)
                )
            )

    def _with_google(self, fake_patches):
        from contextlib import ExitStack

        stack = ExitStack()
        for p in fake_patches:
            stack.enter_context(p)
        return stack

    # 1
    def test_same_create_key_concurrently_yields_one_booking_and_one_provider_call(self) -> None:
        tenant_id, customer, resource_id = self._google_tenant()
        fake, patches = self._fake_google()
        events = RecordingEventPort()
        with self._with_google(patches):
            results = self._in_threads(
                *[lambda: self._create(tenant_id, customer, resource_id, key="abc123", events=events)] * 2
            )
        self.assertFalse([r for r in results if isinstance(r, Exception)], results)
        self.assertEqual(results[0], results[1], "both callers must get the same booking")
        self.assertEqual(fake.create_calls, 1)
        with self.SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmBooking)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(BookingOperation)), 1)
        self.assertEqual([e for _, e in events.events], ["booking.created"])

    # 2
    def test_same_key_with_a_different_payload_is_an_idempotency_conflict(self) -> None:
        tenant_id, customer, resource_id = self._google_tenant()
        fake, patches = self._fake_google()
        with self._with_google(patches):
            self._create(tenant_id, customer, resource_id, key="k-1")
            with self.assertRaises(IdempotencyConflictError):
                self._create(tenant_id, customer, resource_id, key="k-1", start=self.START + timedelta(hours=2))
        self.assertEqual(fake.create_calls, 1)

    def test_sequential_retry_replays_without_calling_the_provider(self) -> None:
        tenant_id, customer, resource_id = self._google_tenant()
        fake, patches = self._fake_google()
        events = RecordingEventPort()
        with self._with_google(patches):
            first = self._create(tenant_id, customer, resource_id, key="k-2", events=events)
            second = self._create(tenant_id, customer, resource_id, key="k-2", events=events)
        self.assertEqual(first, second)
        self.assertEqual(fake.create_calls, 1)
        self.assertEqual(len(events.events), 1)

    # 3
    def test_different_keys_same_slot_one_wins_and_one_gets_a_slot_conflict(self) -> None:
        tenant_id, customer, resource_id = self._google_tenant()
        fake, patches = self._fake_google()
        with self._with_google(patches):
            results = self._in_threads(
                lambda: self._create(tenant_id, customer, resource_id, key="a"),
                lambda: self._create(tenant_id, customer, resource_id, key="b"),
            )
        errors = [r for r in results if isinstance(r, Exception)]
        self.assertEqual(len(errors), 1, results)
        self.assertIsInstance(errors[0], SlotConflictError)
        self.assertEqual(fake.create_calls, 1)
        self.assertEqual(self._active(tenant_id), 1)

    # 4 / 5
    def test_overlapping_interval_is_rejected_and_adjacent_is_allowed(self) -> None:
        tenant_id, customer, resource_id = self._google_tenant()
        fake, patches = self._fake_google()
        with self._with_google(patches):
            self._create(tenant_id, customer, resource_id, key="a")  # [15:00, 15:30)
            with self.assertRaises(SlotConflictError):
                self._create(tenant_id, customer, resource_id, key="b", start=self.START + timedelta(minutes=15))
            self._create(tenant_id, customer, resource_id, key="c", start=self.START + timedelta(minutes=30))
        self.assertEqual(self._active(tenant_id), 2)
        self.assertEqual(fake.create_calls, 2)

    # 6
    def test_failed_booking_releases_the_slot(self) -> None:
        tenant_id, customer, resource_id = self._google_tenant()
        fake, patches = self._fake_google()
        with self._with_google(patches):
            fake.create_error = ValueError("Google Calendar event creation failed: boom")
            with self.assertRaises(ValueError):
                self._create(tenant_id, customer, resource_id, key="a")
            self.assertEqual(self._active(tenant_id), 0)
            fake.create_error = None
            self._create(tenant_id, customer, resource_id, key="b")
        self.assertEqual(self._active(tenant_id), 1)

    def test_known_failure_allows_retry_with_the_same_key(self) -> None:
        tenant_id, customer, resource_id = self._google_tenant()
        fake, patches = self._fake_google()
        with self._with_google(patches):
            fake.create_error = ValueError("Google Calendar event creation failed: 400")
            with self.assertRaises(ValueError):
                self._create(tenant_id, customer, resource_id, key="retry")
            fake.create_error = None
            booking_id = self._create(tenant_id, customer, resource_id, key="retry")
        with self.SessionLocal() as db:
            self.assertEqual(db.get(CrmBooking, booking_id).status, "accepted")

    # 7
    def test_double_cancel_calls_the_provider_once(self) -> None:
        tenant_id, customer, resource_id = self._google_tenant()
        fake, patches = self._fake_google()
        events = RecordingEventPort()
        with self._with_google(patches):
            booking_id = self._create(tenant_id, customer, resource_id, key="a", events=events)

            def cancel():
                with self.SessionLocal() as db:
                    return self._service(db, customer, events=events).cancel_lead_booking(
                        tenant_id=tenant_id, booking_id=booking_id
                    )

            results = self._in_threads(cancel, cancel)
        self.assertTrue(all(isinstance(r, dict) and r["status"] == "success" for r in results), results)
        self.assertEqual(fake.delete_calls, 1)
        self.assertEqual([e for _, e in events.events].count("booking.cancelled"), 1)
        with self.SessionLocal() as db:
            self.assertEqual(db.get(CrmBooking, booking_id).status, "cancelled")
            cancelled = db.scalar(
                select(func.count()).select_from(CrmBookingEvent).where(CrmBookingEvent.event_type == "booking_cancelled")
            )
        self.assertEqual(cancelled, 1)
        # a later repeat is still a no-op
        with self.SessionLocal() as db:
            self._service(db, customer).cancel_lead_booking(tenant_id=tenant_id, booking_id=booking_id)
        self.assertEqual(fake.delete_calls, 1)

    # 8
    def test_double_reschedule_to_the_same_target_calls_the_provider_once(self) -> None:
        tenant_id, customer, resource_id = self._google_tenant()
        fake, patches = self._fake_google()
        events = RecordingEventPort()
        target = self.START + timedelta(hours=1)
        with self._with_google(patches):
            booking_id = self._create(tenant_id, customer, resource_id, key="a", events=events)

            def reschedule():
                with self.SessionLocal() as db:
                    return self._service(db, customer, events=events).reschedule_lead_booking(
                        tenant_id=tenant_id, booking_id=booking_id, new_start_time=target.isoformat().replace("+00:00", "Z")
                    )

            results = self._in_threads(reschedule, reschedule)
            reschedule()  # and once more, sequentially
        self.assertTrue(all(isinstance(r, dict) and r["status"] == "success" for r in results), results)
        self.assertEqual(fake.patch_calls, 1)
        self.assertEqual([e for _, e in events.events].count("booking.rescheduled"), 1)
        with self.SessionLocal() as db:
            row = db.get(CrmBooking, booking_id)
            self.assertEqual(row.start_at, target)
            self.assertEqual(row.end_at, target + timedelta(minutes=30))

    # 9
    def test_reschedule_into_an_occupied_slot_is_rejected(self) -> None:
        tenant_id, customer, resource_id = self._google_tenant()
        fake, patches = self._fake_google()
        with self._with_google(patches):
            a = self._create(tenant_id, customer, resource_id, key="a")
            self._create(tenant_id, customer, resource_id, key="b", start=self.START + timedelta(hours=1))
            with self.SessionLocal() as db:
                with self.assertRaises(SlotConflictError):
                    self._service(db, customer).reschedule_lead_booking(
                        tenant_id=tenant_id,
                        booking_id=a,
                        new_start_time=(self.START + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                    )
        self.assertEqual(fake.patch_calls, 0)
        with self.SessionLocal() as db:
            self.assertEqual(db.get(CrmBooking, a).start_at, self.START)

    # 10
    def test_same_key_and_slot_in_two_tenants_do_not_collide(self) -> None:
        fake, patches = self._fake_google()
        t1, c1, r1 = self._google_tenant()
        t2, c2, r2 = self._google_tenant()
        with self._with_google(patches):
            b1 = self._create(t1, c1, r1, key="same-key")
            b2 = self._create(t2, c2, r2, key="same-key")
        self.assertNotEqual(b1, b2)
        self.assertEqual(fake.create_calls, 2)

    # timeout: outcome unknown
    def test_provider_timeout_leaves_an_unknown_outcome_that_is_not_retried(self) -> None:
        tenant_id, customer, resource_id = self._google_tenant()
        fake, patches = self._fake_google()
        with self._with_google(patches):
            fake.create_error = TimeoutError("read timed out")
            with self.assertRaises(ValueError):  # the adapter wraps it; the cause chain says "timeout"
                self._create(tenant_id, customer, resource_id, key="slow")
            fake.create_error = None
            # same key: NOT executed again, reported as in progress / uncertain
            with self.assertRaises(BookingOperationInProgressError):
                self._create(tenant_id, customer, resource_id, key="slow")
            # the uncertain booking keeps the slot blocked for others
            with self.assertRaises(SlotConflictError):
                self._create(tenant_id, customer, resource_id, key="other")
        self.assertEqual(fake.create_calls, 1)
        with self.SessionLocal() as db:
            op = db.scalar(select(BookingOperation))
            self.assertEqual(op.status, "provider_unknown")
            self.assertEqual(db.get(CrmBooking, op.booking_id).status, "pending")

    def test_invalid_idempotency_key_is_rejected(self) -> None:
        tenant_id, customer, resource_id = self._google_tenant()
        fake, patches = self._fake_google()
        with self._with_google(patches):
            with self.assertRaises(ValueError):
                self._create(tenant_id, customer, resource_id, key="bad key with spaces")
        self.assertEqual(fake.create_calls, 0)

    def test_repeated_same_key_races_are_stable(self) -> None:
        """Soak: 20 rounds of the create race (no deadlocks, always one booking)."""
        fake, patches = self._fake_google()
        with self._with_google(patches):
            for round_no in range(20):
                tenant_id, customer, resource_id = self._google_tenant()
                results = self._in_threads(
                    *[lambda: self._create(tenant_id, customer, resource_id, key=f"r{round_no}")] * 3
                )
                self.assertFalse([r for r in results if isinstance(r, Exception)], results)
                self.assertEqual(len(set(results)), 1)
        self.assertEqual(fake.create_calls, 20)


if __name__ == "__main__":
    unittest.main()
