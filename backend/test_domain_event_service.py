import copy
import os
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import event

TEST_DB_PATH = Path("serviai_domain_event_service_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.domain.events import (
    DomainEventPayloadValidationError,
    DomainEventType,
    UnsupportedDomainEventTypeError,
    validate_domain_event_payload,
)
from app.models.identity import Tenant
from app.models.notifications import DomainEvent, NotificationDelivery
from app.services.domain_event_service import (
    DomainEventIdempotencyConflictError,
    DomainEventService,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _valid_booking_payload() -> dict:
    return {
        "booking": {
            "id": "bk-123",
            "status": "confirmed",
            "title": "Visita al apartamento",
            "start_at": "2026-08-01T15:00:00+00:00",
            "end_at": "2026-08-01T15:30:00+00:00",
            "timezone": "America/Bogota",
            "meeting_url": "https://meet.example.com/abc",
        },
        "customer": {"name": "Cliente Demo", "phone": "+573000000000"},
        "lead": {"id": "lead-1", "status": "qualified"},
        "call": {"id": "call-1", "provider_call_id": "prov-1"},
        "custom": {"property_id": "prop-1"},
    }


def _valid_call_payload() -> dict:
    return {
        "call": {
            "id": "call-1",
            "provider": "ultravox",
            "provider_call_id": "prov-call-1",
            "status": "completed",
            "duration_seconds": 120,
            "summary": "Cliente interesado en visita",
            "outcome": "interested",
        },
        "customer": {"email": "demo@example.com"},
        "lead": {"id": "lead-2"},
        "custom": {"specialty": "inmobiliaria"},
    }


# ---------------------------------------------------------------------------
# Contratos (payloads de dominio) — 1 a 17
# ---------------------------------------------------------------------------
class DomainEventPayloadContractTests(unittest.TestCase):
    def test_booking_created_valid(self):
        result = validate_domain_event_payload(
            DomainEventType.BOOKING_CREATED.value, _valid_booking_payload()
        )
        self.assertEqual(result["booking"]["id"], "bk-123")

    def test_booking_cancelled_valid(self):
        result = validate_domain_event_payload(
            DomainEventType.BOOKING_CANCELLED.value, _valid_booking_payload()
        )
        self.assertEqual(result["booking"]["status"], "confirmed")

    def test_booking_rescheduled_valid(self):
        result = validate_domain_event_payload(
            DomainEventType.BOOKING_RESCHEDULED.value, _valid_booking_payload()
        )
        self.assertIn("booking", result)

    def test_call_completed_valid(self):
        result = validate_domain_event_payload(
            DomainEventType.CALL_COMPLETED.value, _valid_call_payload()
        )
        self.assertEqual(result["call"]["status"], "completed")

    def test_call_failed_valid(self):
        result = validate_domain_event_payload(
            DomainEventType.CALL_FAILED.value, _valid_call_payload()
        )
        self.assertIn("call", result)

    def test_call_no_answer_valid(self):
        result = validate_domain_event_payload(
            DomainEventType.CALL_NO_ANSWER.value, _valid_call_payload()
        )
        self.assertIn("call", result)

    def test_unsupported_event_type_is_rejected(self):
        with self.assertRaises(UnsupportedDomainEventTypeError):
            validate_domain_event_payload("unknown.type", _valid_booking_payload())

    def test_unexpected_top_level_field_is_rejected(self):
        payload = _valid_booking_payload()
        payload["unexpected"] = "x"
        with self.assertRaises(DomainEventPayloadValidationError):
            validate_domain_event_payload(DomainEventType.BOOKING_CREATED.value, payload)

    def test_unexpected_nested_field_is_rejected(self):
        booking_payload = _valid_booking_payload()
        booking_payload["booking"]["unexpected"] = "x"
        with self.assertRaises(DomainEventPayloadValidationError):
            validate_domain_event_payload(DomainEventType.BOOKING_CREATED.value, booking_payload)

        call_payload = _valid_call_payload()
        call_payload["call"]["unexpected"] = "x"
        with self.assertRaises(DomainEventPayloadValidationError):
            validate_domain_event_payload(DomainEventType.CALL_COMPLETED.value, call_payload)

    def test_naive_datetime_is_rejected(self):
        payload = _valid_booking_payload()
        payload["booking"]["start_at"] = "2026-08-01T15:00:00"
        with self.assertRaises(DomainEventPayloadValidationError):
            validate_domain_event_payload(DomainEventType.BOOKING_CREATED.value, payload)

    def test_end_at_before_start_at_is_rejected(self):
        payload = _valid_booking_payload()
        payload["booking"]["end_at"] = "2026-08-01T14:00:00+00:00"
        with self.assertRaises(DomainEventPayloadValidationError):
            validate_domain_event_payload(DomainEventType.BOOKING_CREATED.value, payload)

    def test_direct_sensitive_key_in_custom_is_rejected(self):
        payload = _valid_booking_payload()
        payload["custom"] = {"api_key": "secret-value"}
        with self.assertRaises(DomainEventPayloadValidationError):
            validate_domain_event_payload(DomainEventType.BOOKING_CREATED.value, payload)

    def test_nested_sensitive_key_in_custom_is_rejected(self):
        payload = _valid_booking_payload()
        payload["custom"] = {"items": [{"deep": {"access_token": "secret-value"}}]}
        with self.assertRaises(DomainEventPayloadValidationError):
            validate_domain_event_payload(DomainEventType.BOOKING_CREATED.value, payload)

    def test_custom_depth_greater_than_five_is_rejected(self):
        payload = _valid_booking_payload()
        payload["custom"] = {"l1": {"l2": {"l3": {"l4": {"l5": {"l6": "too deep"}}}}}}
        with self.assertRaises(DomainEventPayloadValidationError):
            validate_domain_event_payload(DomainEventType.BOOKING_CREATED.value, payload)

    def test_payload_larger_than_32kb_is_rejected(self):
        payload = _valid_booking_payload()
        payload["custom"] = {"blob": "a" * 40000}
        with self.assertRaises(DomainEventPayloadValidationError):
            validate_domain_event_payload(DomainEventType.BOOKING_CREATED.value, payload)

    def test_original_payload_dict_is_not_mutated(self):
        payload = _valid_booking_payload()
        snapshot = copy.deepcopy(payload)
        validate_domain_event_payload(DomainEventType.BOOKING_CREATED.value, payload)
        self.assertEqual(payload, snapshot)

    def test_datetimes_are_normalized_to_iso8601_strings(self):
        payload = _valid_booking_payload()
        result = validate_domain_event_payload(DomainEventType.BOOKING_CREATED.value, payload)
        start_at = result["booking"]["start_at"]
        self.assertIsInstance(start_at, str)
        tz_marker = start_at[10:]
        self.assertTrue("T" in start_at and ("Z" in tz_marker or "+" in tz_marker or "-" in tz_marker))


# ---------------------------------------------------------------------------
# Servicio (DomainEventService) — 18 a 30
# ---------------------------------------------------------------------------
class DomainEventServiceTests(unittest.TestCase):
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
        self.db = SessionLocal()
        self.service = DomainEventService(self.db)

    def tearDown(self):
        self.db.close()

    def _create_tenant(self, slug: str) -> str:
        tenant = Tenant(name=f"Empresa {slug}", slug=slug)
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant.id

    def test_publish_creates_new_event(self):
        tenant_id = self._create_tenant("new-event")
        result = self.service.publish(
            tenant_id=tenant_id,
            event_type=DomainEventType.BOOKING_CREATED.value,
            source="calcom",
            idempotency_key="new-event-key",
            payload=_valid_booking_payload(),
            resource_type="booking",
            resource_id="bk-123",
        )
        self.assertTrue(result.created)
        self.assertIsNotNone(result.event.id)

    def test_publish_sets_pending_status_and_zero_attempts(self):
        tenant_id = self._create_tenant("pending-status")
        result = self.service.publish(
            tenant_id=tenant_id,
            event_type=DomainEventType.BOOKING_CREATED.value,
            source="calcom",
            idempotency_key="pending-status-key",
            payload=_valid_booking_payload(),
        )
        self.assertEqual(result.event.status, "pending")
        self.assertEqual(result.event.attempts, 0)

    def test_repeat_publish_returns_same_row(self):
        tenant_id = self._create_tenant("repeat-same")
        payload = _valid_booking_payload()
        first = self.service.publish(
            tenant_id=tenant_id,
            event_type=DomainEventType.BOOKING_CREATED.value,
            source="calcom",
            idempotency_key="repeat-key",
            payload=payload,
        )
        second = self.service.publish(
            tenant_id=tenant_id,
            event_type=DomainEventType.BOOKING_CREATED.value,
            source="calcom",
            idempotency_key="repeat-key",
            payload=payload,
        )
        self.assertFalse(second.created)
        self.assertEqual(first.event.id, second.event.id)

    def test_repeat_publish_does_not_increase_total_events(self):
        tenant_id = self._create_tenant("repeat-count")
        payload = _valid_booking_payload()
        for _ in range(3):
            self.service.publish(
                tenant_id=tenant_id,
                event_type=DomainEventType.BOOKING_CREATED.value,
                source="calcom",
                idempotency_key="repeat-count-key",
                payload=payload,
            )
        self.assertEqual(self.db.query(DomainEvent).count(), 1)

    def test_same_key_different_payload_raises_conflict(self):
        tenant_id = self._create_tenant("conflict-payload")
        self.service.publish(
            tenant_id=tenant_id,
            event_type=DomainEventType.BOOKING_CREATED.value,
            source="calcom",
            idempotency_key="key-1",
            payload=_valid_booking_payload(),
        )
        other_payload = _valid_booking_payload()
        other_payload["booking"]["id"] = "different-booking-id"
        with self.assertRaises(DomainEventIdempotencyConflictError):
            self.service.publish(
                tenant_id=tenant_id,
                event_type=DomainEventType.BOOKING_CREATED.value,
                source="calcom",
                idempotency_key="key-1",
                payload=other_payload,
            )

    def test_same_key_different_event_type_raises_conflict(self):
        tenant_id = self._create_tenant("conflict-type")
        self.service.publish(
            tenant_id=tenant_id,
            event_type=DomainEventType.BOOKING_CREATED.value,
            source="calcom",
            idempotency_key="shared-key",
            payload=_valid_booking_payload(),
        )
        with self.assertRaises(DomainEventIdempotencyConflictError):
            self.service.publish(
                tenant_id=tenant_id,
                event_type=DomainEventType.CALL_COMPLETED.value,
                source="ultravox",
                idempotency_key="shared-key",
                payload=_valid_call_payload(),
            )

    def test_same_key_allowed_across_different_tenants(self):
        tenant_a = self._create_tenant("tenant-a-key")
        tenant_b = self._create_tenant("tenant-b-key")
        payload = _valid_booking_payload()

        result_a = self.service.publish(
            tenant_id=tenant_a,
            event_type=DomainEventType.BOOKING_CREATED.value,
            source="calcom",
            idempotency_key="shared-across-tenants",
            payload=payload,
        )
        result_b = self.service.publish(
            tenant_id=tenant_b,
            event_type=DomainEventType.BOOKING_CREATED.value,
            source="calcom",
            idempotency_key="shared-across-tenants",
            payload=payload,
        )
        self.assertTrue(result_a.created)
        self.assertTrue(result_b.created)
        self.assertNotEqual(result_a.event.id, result_b.event.id)

    def test_get_event_is_tenant_isolated(self):
        tenant_a = self._create_tenant("iso-a")
        tenant_b = self._create_tenant("iso-b")
        result = self.service.publish(
            tenant_id=tenant_a,
            event_type=DomainEventType.BOOKING_CREATED.value,
            source="calcom",
            idempotency_key="iso-key",
            payload=_valid_booking_payload(),
        )
        self.assertIsNone(self.service.get_event(tenant_id=tenant_b, event_id=result.event.id))
        self.assertIsNotNone(self.service.get_event(tenant_id=tenant_a, event_id=result.event.id))

    def test_get_by_idempotency_key_is_tenant_isolated(self):
        tenant_a = self._create_tenant("iso-key-a")
        tenant_b = self._create_tenant("iso-key-b")
        self.service.publish(
            tenant_id=tenant_a,
            event_type=DomainEventType.BOOKING_CREATED.value,
            source="calcom",
            idempotency_key="iso-lookup-key",
            payload=_valid_booking_payload(),
        )
        self.assertIsNone(
            self.service.get_by_idempotency_key(tenant_id=tenant_b, idempotency_key="iso-lookup-key")
        )
        self.assertIsNotNone(
            self.service.get_by_idempotency_key(tenant_id=tenant_a, idempotency_key="iso-lookup-key")
        )

    def test_available_at_naive_is_rejected(self):
        tenant_id = self._create_tenant("naive-available-at")
        with self.assertRaises(ValueError):
            self.service.publish(
                tenant_id=tenant_id,
                event_type=DomainEventType.BOOKING_CREATED.value,
                source="calcom",
                idempotency_key="naive-at-key",
                payload=_valid_booking_payload(),
                available_at=datetime(2026, 8, 1, 12, 0, 0),
            )

    def test_publish_does_not_create_notification_delivery_rows(self):
        tenant_id = self._create_tenant("no-delivery")
        self.service.publish(
            tenant_id=tenant_id,
            event_type=DomainEventType.BOOKING_CREATED.value,
            source="calcom",
            idempotency_key="no-delivery-key",
            payload=_valid_booking_payload(),
        )
        self.assertEqual(self.db.query(NotificationDelivery).count(), 0)

    def test_session_remains_usable_after_conflict(self):
        tenant_id = self._create_tenant("post-conflict")
        payload = _valid_booking_payload()
        self.service.publish(
            tenant_id=tenant_id,
            event_type=DomainEventType.BOOKING_CREATED.value,
            source="calcom",
            idempotency_key="conflict-key",
            payload=payload,
        )

        conflicting_payload = _valid_booking_payload()
        conflicting_payload["booking"]["id"] = "different-booking-id"
        with self.assertRaises(DomainEventIdempotencyConflictError):
            self.service.publish(
                tenant_id=tenant_id,
                event_type=DomainEventType.BOOKING_CREATED.value,
                source="calcom",
                idempotency_key="conflict-key",
                payload=conflicting_payload,
            )

        # La sesion debe seguir siendo utilizable tras el conflicto.
        result = self.service.publish(
            tenant_id=tenant_id,
            event_type=DomainEventType.BOOKING_CREATED.value,
            source="calcom",
            idempotency_key="another-key",
            payload=payload,
        )
        self.assertTrue(result.created)
        self.assertEqual(self.db.query(DomainEvent).count(), 2)

    def test_integrity_error_recovery_returns_existing_event(self):
        tenant_id = self._create_tenant("race-tenant")
        payload = _valid_booking_payload()
        normalized = validate_domain_event_payload(DomainEventType.BOOKING_CREATED.value, payload)

        existing = DomainEvent(
            tenant_id=tenant_id,
            event_type=DomainEventType.BOOKING_CREATED.value,
            source="calcom",
            idempotency_key="race-key",
            payload_json=normalized,
            status="pending",
            attempts=0,
        )
        self.db.add(existing)
        self.db.commit()
        self.db.refresh(existing)

        call_state = {"count": 0}
        original_lookup = DomainEventService.get_by_idempotency_key

        def flaky_lookup(self_service, *, tenant_id, idempotency_key):
            call_state["count"] += 1
            if call_state["count"] == 1:
                # Simula que, en el momento de la comprobacion previa, la fila
                # insertada por otro proceso concurrente todavia no era visible.
                return None
            return original_lookup(self_service, tenant_id=tenant_id, idempotency_key=idempotency_key)

        with patch.object(DomainEventService, "get_by_idempotency_key", flaky_lookup):
            result = self.service.publish(
                tenant_id=tenant_id,
                event_type=DomainEventType.BOOKING_CREATED.value,
                source="calcom",
                idempotency_key="race-key",
                payload=payload,
            )

        self.assertFalse(result.created)
        self.assertEqual(result.event.id, existing.id)
        self.assertEqual(call_state["count"], 2)

        # La sesion sigue siendo utilizable tras recuperarse del IntegrityError.
        self.assertEqual(self.db.query(DomainEvent).count(), 1)


if __name__ == "__main__":
    unittest.main()
