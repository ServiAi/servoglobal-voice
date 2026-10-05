r"""Real PostgreSQL concurrency tests for Integrations / Messaging.

Only invariants SQLite cannot prove:

* a late ``delivered`` webhook never downgrades ``read`` (row lock on the message),
* a retried inbound webhook creates one message and one CRM activity (advisory lock + the
  partial unique index on ``(tenant_id, provider_message_id)``, which also stops direct writers),
* concurrent writers of the same ``(tenant, provider)`` catalog row converge on one row.

Run only against a dedicated disposable database:

    $env:INTEGRATIONS_TEST_DATABASE_URL = "postgresql+psycopg://serviai:serviai@localhost:5432/serviai_integrations_test"
    .\.venv\Scripts\python.exe -m unittest test_integrations_postgres -v
"""

from __future__ import annotations

import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

INTEGRATIONS_TEST_DATABASE_URL = os.environ.get("INTEGRATIONS_TEST_DATABASE_URL")
if INTEGRATIONS_TEST_DATABASE_URL:
    os.environ.setdefault("ULTRAVOX_API_KEY", "test")
    os.environ["DATABASE_URL"] = INTEGRATIONS_TEST_DATABASE_URL

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.modules.identity.infrastructure.models import Tenant
from app.modules.crm.infrastructure.models import CrmActivity, CrmContact, CrmLead, CrmPipelineStage
from app.modules.integrations.application.integration_service import IntegrationService
from app.modules.integrations.application.whatsapp import message_service as message_service_module
from app.modules.integrations.application.whatsapp.message_service import WhatsAppMessageService
from app.modules.integrations.domain.whatsapp import WhatsAppInboundMessage, WhatsAppStatusUpdate
from app.modules.integrations.infrastructure.models import (
    CrmWhatsAppMessage,
    TenantIntegration,
    TenantWhatsAppConfig,
)

PHONE_NUMBER_ID = "pg-phone-number"


class _Notifications:
    """NotificationsPort double: Notifications' own behaviour is not under test here."""

    def __init__(self) -> None:
        self.reported: list[tuple[str, str]] = []

    def delivery_exists(self, *, tenant_id: str, delivery_id: str) -> bool:
        return True

    def report_delivery_status(self, *, tenant_id, provider_message_id, status, occurred_at, error_message) -> None:
        self.reported.append((provider_message_id, status))


@unittest.skipUnless(
    INTEGRATIONS_TEST_DATABASE_URL,
    "INTEGRATIONS_TEST_DATABASE_URL not set; skipping real PostgreSQL concurrency tests",
)
class IntegrationsPostgresConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(INTEGRATIONS_TEST_DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=10)
        if cls.engine.dialect.name != "postgresql":
            raise unittest.SkipTest("INTEGRATIONS_TEST_DATABASE_URL must point to a PostgreSQL database")
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=cls.engine)

    @classmethod
    def tearDownClass(cls) -> None:
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    # -- fixtures ---------------------------------------------------------------------------------

    def _tenant(self, db) -> str:
        tenant = Tenant(name="Empresa PG", slug=f"pg-{uuid4().hex[:10]}")
        db.add(tenant)
        db.commit()
        return tenant.id

    def _whatsapp_config(self, db, tenant_id: str) -> str:
        phone_number_id = f"{PHONE_NUMBER_ID}-{uuid4().hex[:8]}"
        db.add(
            TenantWhatsAppConfig(
                tenant_id=tenant_id,
                provider="whatsapp_cloud",
                status="active",
                phone_number_id=phone_number_id,
                display_phone_number="+573009998877",
                default_language="es",
            )
        )
        db.commit()
        return phone_number_id

    def _open_lead(self, db, tenant_id: str, phone: str) -> tuple[str, str]:
        stage = CrmPipelineStage(tenant_id=tenant_id, key="new", name="Nuevo", position=1, is_default=True)
        contact = CrmContact(tenant_id=tenant_id, name="Pedro Gomez", email=f"{uuid4().hex[:6]}@example.com", phone=phone)
        db.add_all([stage, contact])
        db.commit()
        lead = CrmLead(tenant_id=tenant_id, contact_id=contact.id, current_stage_id=stage.id, status="open")
        db.add(lead)
        db.commit()
        return lead.id, contact.id

    def _outbound_message(self, db, tenant_id: str, provider_message_id: str) -> str:
        message = CrmWhatsAppMessage(
            tenant_id=tenant_id,
            provider_message_id=provider_message_id,
            direction="outbound",
            to_phone="573001112233",
            status="sent",
            metadata_json={},
            sent_at=datetime.now(timezone.utc),
        )
        db.add(message)
        db.commit()
        return message.id

    def _process(self, events, barrier: Barrier | None = None) -> dict[str, int]:
        session = self.SessionLocal()
        try:
            service = WhatsAppMessageService(session, client=object(), notifications=_Notifications())
            if barrier is not None:
                barrier.wait(timeout=10)
            return service.handle_events(events)
        finally:
            session.close()

    # -- WhatsApp status race ---------------------------------------------------------------------

    def test_concurrent_delivered_and_read_never_leave_the_message_downgraded(self) -> None:
        with self.SessionLocal() as db:
            tenant_id = self._tenant(db)
            phone_number_id = self._whatsapp_config(db, tenant_id)
            wamids = [f"wamid.race-{index}-{uuid4().hex[:6]}" for index in range(12)]
            for wamid in wamids:
                self._outbound_message(db, tenant_id, wamid)

        real_can_advance = message_service_module.can_advance_status

        def slow_can_advance(current, new):
            # Widens the read-modify-write window: without a row lock the loser overwrites the winner.
            time.sleep(0.05)
            return real_can_advance(current, new)

        def status(wamid, name):
            return [WhatsAppStatusUpdate(phone_number_id=phone_number_id, provider_message_id=wamid, status=name)]

        with patch.object(message_service_module, "can_advance_status", slow_can_advance):
            for index, wamid in enumerate(wamids):
                barrier = Barrier(2)
                pair = [("read", status(wamid, "read")), ("delivered", status(wamid, "delivered"))]
                if index % 2:
                    pair.reverse()
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(self._process, events, barrier) for _, events in pair]
                    for future in futures:
                        future.result(timeout=30)

        with self.SessionLocal() as db:
            statuses = {
                message.provider_message_id: message.status
                for message in db.scalars(
                    select(CrmWhatsAppMessage).where(CrmWhatsAppMessage.provider_message_id.in_(wamids))
                )
            }
        self.assertEqual(set(statuses.values()), {"read"}, statuses)

    def test_late_failed_after_read_never_overwrites_it_and_releases_the_row_lock(self) -> None:
        with self.SessionLocal() as db:
            tenant_id = self._tenant(db)
            phone_number_id = self._whatsapp_config(db, tenant_id)
            wamid = f"wamid.late-failed-{uuid4().hex[:6]}"
            message_id = self._outbound_message(db, tenant_id, wamid)

        def status(name):
            return [WhatsAppStatusUpdate(phone_number_id=phone_number_id, provider_message_id=wamid, status=name)]

        self._process(status("read"))
        self._process(status("failed"))
        with self.SessionLocal() as db:
            self.assertEqual(db.get(CrmWhatsAppMessage, message_id).status, "read")

        # The ignored webhook must not keep the row locked: another writer gets it without waiting.
        session = self.SessionLocal()
        try:
            service = WhatsAppMessageService(session, client=object(), notifications=_Notifications())
            service.handle_events(status("failed"))
            other = self.SessionLocal()
            try:
                other.execute(text("SET lock_timeout = '500ms'"))
                other.execute(select(CrmWhatsAppMessage).where(CrmWhatsAppMessage.id == message_id).with_for_update())
            finally:
                other.rollback()
                other.close()
        finally:
            session.close()

    # -- inbound idempotency ----------------------------------------------------------------------

    def test_concurrent_duplicate_inbound_webhook_stores_one_message_and_one_activity(self) -> None:
        with self.SessionLocal() as db:
            tenant_id = self._tenant(db)
            phone_number_id = self._whatsapp_config(db, tenant_id)
            lead_id, _ = self._open_lead(db, tenant_id, "+573001112233")
        wamid = f"wamid.in-{uuid4().hex[:8]}"
        events = [
            WhatsAppInboundMessage(
                phone_number_id=phone_number_id, from_phone="573001112233", provider_message_id=wamid, body="Hola"
            )
        ]

        real_preview = message_service_module.safe_preview

        def slow_preview(value):
            # Runs between the duplicate lookup and the INSERT: widens the window a missing lock would leave open.
            time.sleep(0.1)
            return real_preview(value)

        barrier = Barrier(4)
        with patch.object(message_service_module, "safe_preview", slow_preview):
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = [
                    future.result(timeout=30)
                    for future in [pool.submit(self._process, events, barrier) for _ in range(4)]
                ]

        self.assertEqual(sum(result["inbound"] for result in results), 1, results)
        with self.SessionLocal() as db:
            messages = db.scalar(
                select(func.count()).select_from(CrmWhatsAppMessage).where(CrmWhatsAppMessage.provider_message_id == wamid)
            )
            activities = db.scalar(
                select(func.count()).select_from(CrmActivity).where(
                    CrmActivity.lead_id == lead_id, CrmActivity.activity_type == "whatsapp_inbound_received"
                )
            )
        self.assertEqual((messages, activities), (1, 1))

    # -- database-level identity of provider messages ----------------------------------------------

    def _insert_message(self, tenant_id: str, provider_message_id: str | None, direction: str = "outbound") -> None:
        """A writer that bypasses WhatsAppMessageService and its advisory lock."""
        with self.SessionLocal() as db:
            db.add(
                CrmWhatsAppMessage(
                    tenant_id=tenant_id,
                    provider_message_id=provider_message_id,
                    direction=direction,
                    status="sent",
                    metadata_json={},
                )
            )
            db.commit()

    def test_database_rejects_a_duplicate_provider_message_id_from_a_direct_writer(self) -> None:
        with self.SessionLocal() as db:
            tenant_id = self._tenant(db)
        wamid = f"wamid.direct-{uuid4().hex[:6]}"
        self._insert_message(tenant_id, wamid)
        with self.assertRaises(IntegrityError):
            self._insert_message(tenant_id, wamid, direction="inbound")
        with self.SessionLocal() as db:
            count = db.scalar(
                select(func.count()).select_from(CrmWhatsAppMessage).where(CrmWhatsAppMessage.provider_message_id == wamid)
            )
        self.assertEqual(count, 1)

    def test_the_same_provider_message_id_is_allowed_in_different_tenants(self) -> None:
        with self.SessionLocal() as db:
            tenant_a, tenant_b = self._tenant(db), self._tenant(db)
        wamid = f"wamid.shared-{uuid4().hex[:6]}"
        self._insert_message(tenant_a, wamid)
        self._insert_message(tenant_b, wamid)
        with self.SessionLocal() as db:
            count = db.scalar(
                select(func.count()).select_from(CrmWhatsAppMessage).where(CrmWhatsAppMessage.provider_message_id == wamid)
            )
        self.assertEqual(count, 2)

    def test_messages_without_a_provider_message_id_may_repeat(self) -> None:
        with self.SessionLocal() as db:
            tenant_id = self._tenant(db)
        for _ in range(3):
            self._insert_message(tenant_id, None)
        with self.SessionLocal() as db:
            count = db.scalar(
                select(func.count()).select_from(CrmWhatsAppMessage).where(
                    CrmWhatsAppMessage.tenant_id == tenant_id, CrmWhatsAppMessage.provider_message_id.is_(None)
                )
            )
        self.assertEqual(count, 3)

    def test_inbound_unique_violation_after_the_lock_is_a_duplicate_not_a_500(self) -> None:
        """If the unique index fires despite the advisory lock (simulated by hiding the existing row from the
        lookup), the retry is ignored only because the inbound message really is stored."""
        with self.SessionLocal() as db:
            tenant_id = self._tenant(db)
            phone_number_id = self._whatsapp_config(db, tenant_id)
            lead_id, _ = self._open_lead(db, tenant_id, "+573001112233")
        wamid = f"wamid.race-ix-{uuid4().hex[:6]}"
        events = [
            WhatsAppInboundMessage(
                phone_number_id=phone_number_id, from_phone="573001112233", provider_message_id=wamid, body="Hola"
            )
        ]
        self.assertEqual(self._process(events)["inbound"], 1)

        real_exists = WhatsAppMessageService._inbound_exists
        calls = {"count": 0}

        def blind_first_lookup(service, tenant, provider_message_id):
            # The pre-insert duplicate check misses (as if the advisory lock had been bypassed), so the
            # INSERT really collides with the unique index; the post-collision check then sees the row.
            calls["count"] += 1
            return False if calls["count"] == 1 else real_exists(service, tenant, provider_message_id)

        with patch.object(WhatsAppMessageService, "_inbound_exists", blind_first_lookup):
            result = self._process(events)

        self.assertEqual(result["inbound"], 0)
        with self.SessionLocal() as db:
            activities = db.scalar(
                select(func.count()).select_from(CrmActivity).where(
                    CrmActivity.lead_id == lead_id, CrmActivity.activity_type == "whatsapp_inbound_received"
                )
            )
        self.assertEqual(activities, 1)

    def test_outbound_provider_id_collision_is_manual_review_and_overwrites_nothing(self) -> None:
        with self.SessionLocal() as db:
            tenant_id = self._tenant(db)
        wamid = f"wamid.taken-{uuid4().hex[:6]}"
        self._insert_message(tenant_id, wamid)
        with self.SessionLocal() as db:
            queued = CrmWhatsAppMessage(
                tenant_id=tenant_id, direction="outbound", status="queued", metadata_json={}
            )
            db.add(queued)
            db.commit()
            queued_id = queued.id

        session = self.SessionLocal()
        try:
            service = WhatsAppMessageService(session, client=object(), notifications=_Notifications())
            message = session.get(CrmWhatsAppMessage, queued_id)
            acknowledged = service._acknowledge(message, wamid, datetime.now(timezone.utc))
            result = service._provider_id_conflict(tenant_id, message)
        finally:
            session.close()

        self.assertFalse(acknowledged)
        self.assertEqual(result.status, "manual_review")
        self.assertEqual(result.error_message, "whatsapp_provider_message_id_conflict")
        with self.SessionLocal() as db:
            row = db.get(CrmWhatsAppMessage, queued_id)
            owners = db.scalar(
                select(func.count()).select_from(CrmWhatsAppMessage).where(CrmWhatsAppMessage.provider_message_id == wamid)
            )
        self.assertEqual((row.status, row.provider_message_id, owners), ("queued", None, 1))

    # -- catalog race -----------------------------------------------------------------------------

    def test_concurrent_catalog_writers_converge_on_one_row_per_tenant_and_provider(self) -> None:
        with self.SessionLocal() as db:
            tenant_id = self._tenant(db)

        def set_enabled(value: bool) -> bool:
            session = self.SessionLocal()
            try:
                barrier.wait(timeout=10)
                return IntegrationService(session).set_enabled(tenant_id, "whatsapp", value).enabled
            finally:
                session.close()

        for round_number in range(5):
            tenant_round = tenant_id
            if round_number:
                with self.SessionLocal() as db:
                    tenant_round = self._tenant(db)
            tenant_id = tenant_round
            barrier = Barrier(4)
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(set_enabled, bool(index % 2)) for index in range(4)]
                outcomes = [future.result(timeout=30) for future in futures]
            with self.SessionLocal() as db:
                rows = db.scalars(
                    select(TenantIntegration).where(
                        TenantIntegration.tenant_id == tenant_id, TenantIntegration.provider == "whatsapp"
                    )
                ).all()
            self.assertEqual(len(rows), 1, f"round {round_number}")
            self.assertIn(rows[0].enabled, {True, False})
            self.assertEqual(len(outcomes), 4)

    def test_concurrent_resend_upserts_converge_on_one_row(self) -> None:
        with self.SessionLocal() as db:
            tenant_id = self._tenant(db)
        barrier = Barrier(3)

        def upsert(index: int) -> str:
            session = self.SessionLocal()
            try:
                barrier.wait(timeout=10)
                return IntegrationService(session).upsert_resend(
                    tenant_id=tenant_id, display_name=f"Resend {index}", config={"sender_email": "a@b.co"}, api_key=None
                ).id
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=3) as pool:
            ids = {future.result(timeout=30) for future in [pool.submit(upsert, i) for i in range(3)]}
        self.assertEqual(len(ids), 1)
        with self.SessionLocal() as db:
            count = db.scalar(
                select(func.count()).select_from(TenantIntegration).where(
                    TenantIntegration.tenant_id == tenant_id, TenantIntegration.provider == "resend"
                )
            )
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
