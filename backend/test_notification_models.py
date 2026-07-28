import os
import unittest
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

TEST_DB_PATH = Path("serviai_notification_models_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.identity import Tenant
from app.models.notifications import (
    DomainEvent,
    NotificationDelivery,
    TenantCapability,
    TenantNotificationRecipient,
    TenantNotificationRule,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class NotificationModelsTests(unittest.TestCase):
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

    def _create_tenant(self, slug: str) -> str:
        with SessionLocal() as db:
            tenant = Tenant(name=f"Empresa {slug}", slug=slug)
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            return tenant.id

    def _seed_event_and_rule(self, tenant_id: str, suffix: str) -> tuple[str, str]:
        with SessionLocal() as db:
            event_row = DomainEvent(
                tenant_id=tenant_id,
                event_type="booking.confirmed",
                source="calcom",
                idempotency_key=f"evt-{suffix}",
            )
            rule = TenantNotificationRule(
                tenant_id=tenant_id,
                name=f"Regla {suffix}",
                capability_key="booking_notifications",
                event_type="booking.confirmed",
                channel="whatsapp",
                action_type="send_template",
                recipient_strategy="event_customer",
            )
            db.add_all([event_row, rule])
            db.commit()
            db.refresh(event_row)
            db.refresh(rule)
            return event_row.id, rule.id

    # 6.1 Registro de metadata ------------------------------------------------
    def test_metadata_registers_notification_tables(self):
        expected = {
            "tenant_capabilities",
            "tenant_notification_recipients",
            "tenant_notification_rules",
            "domain_events",
            "notification_deliveries",
        }
        self.assertTrue(expected.issubset(Base.metadata.tables.keys()))

    # 6.2 Defaults de TenantCapability -----------------------------------------
    def test_tenant_capability_defaults(self):
        tenant_id = self._create_tenant("empresa-cap-defaults")
        with SessionLocal() as db:
            capability = TenantCapability(tenant_id=tenant_id, capability_key="booking_notifications")
            db.add(capability)
            db.commit()
            db.refresh(capability)

            self.assertFalse(capability.enabled)
            self.assertEqual(capability.config_json, {})
            self.assertIsNotNone(capability.created_at)
            self.assertIsNotNone(capability.updated_at)

    # 6.3 Aislamiento de capacidades --------------------------------------------
    def test_capability_isolation_across_tenants(self):
        tenant_a = self._create_tenant("empresa-cap-a")
        tenant_b = self._create_tenant("empresa-cap-b")

        with SessionLocal() as db:
            db.add(TenantCapability(tenant_id=tenant_a, capability_key="booking_notifications"))
            db.add(TenantCapability(tenant_id=tenant_b, capability_key="booking_notifications"))
            db.commit()

        with SessionLocal() as db:
            db.add(TenantCapability(tenant_id=tenant_a, capability_key="booking_notifications"))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

    # 6.4 Destinatarios ---------------------------------------------------------
    def test_recipients_group_and_uniqueness(self):
        tenant_a = self._create_tenant("empresa-recipients-a")
        tenant_b = self._create_tenant("empresa-recipients-b")

        with SessionLocal() as db:
            db.add(
                TenantNotificationRecipient(
                    tenant_id=tenant_a,
                    group_key="ops",
                    name="Owner",
                    channel="whatsapp",
                    destination="+570000000001",
                )
            )
            db.add(
                TenantNotificationRecipient(
                    tenant_id=tenant_a,
                    group_key="ops",
                    name="Backup",
                    channel="whatsapp",
                    destination="+570000000002",
                )
            )
            db.commit()

        with SessionLocal() as db:
            db.add(
                TenantNotificationRecipient(
                    tenant_id=tenant_a,
                    group_key="ops",
                    name="Duplicado",
                    channel="whatsapp",
                    destination="+570000000001",
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

        with SessionLocal() as db:
            db.add(
                TenantNotificationRecipient(
                    tenant_id=tenant_b,
                    group_key="ops",
                    name="Owner B",
                    channel="whatsapp",
                    destination="+570000000001",
                )
            )
            db.commit()

    # 6.5 Reglas ------------------------------------------------------------
    def test_rule_persistence_defaults_and_uniqueness(self):
        tenant_a = self._create_tenant("empresa-rules-a")
        tenant_b = self._create_tenant("empresa-rules-b")

        conditions = [{"field": "status", "op": "eq", "value": "confirmed"}]
        variable_mapping = {"client_name": "contact.name"}

        with SessionLocal() as db:
            rule = TenantNotificationRule(
                tenant_id=tenant_a,
                name="Confirmacion de reserva",
                capability_key="booking_notifications",
                event_type="booking.confirmed",
                channel="whatsapp",
                action_type="send_template",
                recipient_strategy="event_customer",
                conditions_json=conditions,
                variable_mapping_json=variable_mapping,
            )
            db.add(rule)
            db.commit()
            db.refresh(rule)

            self.assertEqual(rule.conditions_json, conditions)
            self.assertEqual(rule.variable_mapping_json, variable_mapping)
            self.assertEqual(rule.schedule_mode, "immediate")
            self.assertEqual(rule.schedule_offset_minutes, 0)
            self.assertEqual(rule.priority, 100)
            self.assertTrue(rule.enabled)

        with SessionLocal() as db:
            db.add(
                TenantNotificationRule(
                    tenant_id=tenant_a,
                    name="Confirmacion de reserva",
                    capability_key="booking_notifications",
                    event_type="booking.confirmed",
                    channel="whatsapp",
                    action_type="send_template",
                    recipient_strategy="event_customer",
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

        with SessionLocal() as db:
            db.add(
                TenantNotificationRule(
                    tenant_id=tenant_b,
                    name="Confirmacion de reserva",
                    capability_key="booking_notifications",
                    event_type="booking.confirmed",
                    channel="whatsapp",
                    action_type="send_template",
                    recipient_strategy="event_customer",
                )
            )
            db.commit()

    # 6.6 Idempotencia de DomainEvent ---------------------------------------
    def test_domain_event_idempotency(self):
        tenant_a = self._create_tenant("empresa-events-a")
        tenant_b = self._create_tenant("empresa-events-b")

        with SessionLocal() as db:
            event_row = DomainEvent(
                tenant_id=tenant_a,
                event_type="booking.confirmed",
                source="calcom",
                idempotency_key="evt-booking-1",
            )
            db.add(event_row)
            db.commit()
            db.refresh(event_row)

            self.assertEqual(event_row.status, "pending")
            self.assertEqual(event_row.attempts, 0)
            self.assertIsNotNone(event_row.available_at)

        with SessionLocal() as db:
            db.add(
                DomainEvent(
                    tenant_id=tenant_a,
                    event_type="booking.confirmed",
                    source="calcom",
                    idempotency_key="evt-booking-1",
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

        with SessionLocal() as db:
            db.add(
                DomainEvent(
                    tenant_id=tenant_b,
                    event_type="booking.confirmed",
                    source="calcom",
                    idempotency_key="evt-booking-1",
                )
            )
            db.commit()

    # 6.7 NotificationDelivery ------------------------------------------------
    def test_notification_delivery_relations_and_idempotency(self):
        tenant_a = self._create_tenant("empresa-deliveries-a")
        tenant_b = self._create_tenant("empresa-deliveries-b")

        event_a_id, rule_a_id = self._seed_event_and_rule(tenant_a, "a")
        event_b_id, rule_b_id = self._seed_event_and_rule(tenant_b, "b")

        with SessionLocal() as db:
            delivery = NotificationDelivery(
                tenant_id=tenant_a,
                domain_event_id=event_a_id,
                notification_rule_id=rule_a_id,
                channel="whatsapp",
                recipient="+570000000001",
                idempotency_key="dlv-1",
            )
            db.add(delivery)
            db.commit()
            db.refresh(delivery)

            self.assertEqual(delivery.status, "pending")
            self.assertEqual(delivery.attempts, 0)
            self.assertIsNotNone(delivery.scheduled_for)
            self.assertEqual(delivery.domain_event_id, event_a_id)
            self.assertEqual(delivery.notification_rule_id, rule_a_id)

        with SessionLocal() as db:
            db.add(
                NotificationDelivery(
                    tenant_id=tenant_a,
                    domain_event_id=event_a_id,
                    notification_rule_id=rule_a_id,
                    channel="whatsapp",
                    recipient="+570000000002",
                    idempotency_key="dlv-1",
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

        with SessionLocal() as db:
            db.add(
                NotificationDelivery(
                    tenant_id=tenant_b,
                    domain_event_id=event_b_id,
                    notification_rule_id=rule_b_id,
                    channel="whatsapp",
                    recipient="+570000000001",
                    idempotency_key="dlv-1",
                )
            )
            db.commit()

    # 6.8 Integridad referencial ------------------------------------------------
    def test_notification_delivery_referential_integrity(self):
        tenant_a = self._create_tenant("empresa-fk-a")
        _, rule_id = self._seed_event_and_rule(tenant_a, "fk-base")

        with SessionLocal() as db:
            db.add(
                NotificationDelivery(
                    tenant_id=tenant_a,
                    domain_event_id="nonexistent-event-id",
                    notification_rule_id=rule_id,
                    channel="whatsapp",
                    recipient="+570000000001",
                    idempotency_key="dlv-fk-1",
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

        with SessionLocal() as db:
            event_row = DomainEvent(
                tenant_id=tenant_a,
                event_type="booking.confirmed",
                source="calcom",
                idempotency_key="evt-fk-1",
            )
            db.add(event_row)
            db.commit()
            db.refresh(event_row)
            event_id = event_row.id

        with SessionLocal() as db:
            db.add(
                NotificationDelivery(
                    tenant_id=tenant_a,
                    domain_event_id=event_id,
                    notification_rule_id="nonexistent-rule-id",
                    channel="whatsapp",
                    recipient="+570000000001",
                    idempotency_key="dlv-fk-2",
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

    # Phase 6 — worker state columns --------------------------------------
    def test_delivery_worker_state_columns_default_to_none(self):
        tenant_id = self._create_tenant("empresa-worker-state")
        event_id, rule_id = self._seed_event_and_rule(tenant_id, "worker-state")

        with SessionLocal() as db:
            delivery = NotificationDelivery(
                tenant_id=tenant_id,
                domain_event_id=event_id,
                notification_rule_id=rule_id,
                channel="whatsapp",
                recipient="+570000000099",
                idempotency_key="dlv-worker-state",
            )
            db.add(delivery)
            db.commit()
            db.refresh(delivery)

            self.assertIsNone(delivery.next_attempt_at)
            self.assertIsNone(delivery.claim_token)
            self.assertIsNone(delivery.claimed_at)
            self.assertIsNone(delivery.claim_expires_at)

    def test_delivery_worker_state_columns_are_persisted(self):
        from datetime import datetime, timezone

        tenant_id = self._create_tenant("empresa-worker-state-2")
        event_id, rule_id = self._seed_event_and_rule(tenant_id, "worker-state-2")
        now = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)

        with SessionLocal() as db:
            delivery = NotificationDelivery(
                tenant_id=tenant_id,
                domain_event_id=event_id,
                notification_rule_id=rule_id,
                channel="whatsapp",
                recipient="+570000000098",
                idempotency_key="dlv-worker-state-2",
                next_attempt_at=now,
                claim_token="tok-abc123",
                claimed_at=now,
                claim_expires_at=now,
            )
            db.add(delivery)
            db.commit()
            delivery_id = delivery.id

        with SessionLocal() as db:
            reloaded = db.get(NotificationDelivery, delivery_id)
            self.assertEqual(reloaded.claim_token, "tok-abc123")
            self.assertIsNotNone(reloaded.next_attempt_at)
            self.assertIsNotNone(reloaded.claimed_at)
            self.assertIsNotNone(reloaded.claim_expires_at)

    def test_crm_whatsapp_message_notification_delivery_fk(self):
        from app.models.crm import CrmWhatsAppMessage

        tenant_id = self._create_tenant("empresa-message-fk")
        event_id, rule_id = self._seed_event_and_rule(tenant_id, "message-fk")

        with SessionLocal() as db:
            delivery = NotificationDelivery(
                tenant_id=tenant_id,
                domain_event_id=event_id,
                notification_rule_id=rule_id,
                channel="whatsapp",
                recipient="+570000000097",
                idempotency_key="dlv-message-fk",
            )
            db.add(delivery)
            db.commit()
            db.refresh(delivery)
            delivery_id = delivery.id

            message = CrmWhatsAppMessage(
                tenant_id=tenant_id,
                provider="whatsapp_cloud",
                direction="outbound",
                to_phone="+570000000097",
                status="queued",
                metadata_json={},
                notification_delivery_id=delivery_id,
            )
            db.add(message)
            db.commit()
            db.refresh(message)
            self.assertEqual(message.notification_delivery_id, delivery_id)

    def test_crm_whatsapp_message_allows_multiple_messages_per_delivery(self):
        from app.models.crm import CrmWhatsAppMessage

        tenant_id = self._create_tenant("empresa-message-fk-multi")
        event_id, rule_id = self._seed_event_and_rule(tenant_id, "message-fk-multi")

        with SessionLocal() as db:
            delivery = NotificationDelivery(
                tenant_id=tenant_id,
                domain_event_id=event_id,
                notification_rule_id=rule_id,
                channel="whatsapp",
                recipient="+570000000096",
                idempotency_key="dlv-message-fk-multi",
            )
            db.add(delivery)
            db.commit()
            db.refresh(delivery)

            db.add_all(
                [
                    CrmWhatsAppMessage(
                        tenant_id=tenant_id,
                        provider="whatsapp_cloud",
                        direction="outbound",
                        to_phone="+570000000096",
                        status="failed",
                        metadata_json={},
                        notification_delivery_id=delivery.id,
                    ),
                    CrmWhatsAppMessage(
                        tenant_id=tenant_id,
                        provider="whatsapp_cloud",
                        direction="outbound",
                        to_phone="+570000000096",
                        status="sent",
                        metadata_json={},
                        notification_delivery_id=delivery.id,
                    ),
                ]
            )
            # No uniqueness constraint: a delivery may produce more than one
            # CRM message across retries/attempts.
            db.commit()

            count = (
                db.query(CrmWhatsAppMessage)
                .filter(CrmWhatsAppMessage.notification_delivery_id == delivery.id)
                .count()
            )
            self.assertEqual(count, 2)

    def test_crm_whatsapp_message_notification_delivery_fk_rejects_unknown_id(self):
        from app.models.crm import CrmWhatsAppMessage

        tenant_id = self._create_tenant("empresa-message-fk-bad")

        with SessionLocal() as db:
            db.add(
                CrmWhatsAppMessage(
                    tenant_id=tenant_id,
                    provider="whatsapp_cloud",
                    direction="outbound",
                    to_phone="+570000000095",
                    status="queued",
                    metadata_json={},
                    notification_delivery_id="nonexistent-delivery-id",
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()


if __name__ == "__main__":
    unittest.main()
