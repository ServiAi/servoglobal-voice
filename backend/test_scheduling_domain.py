"""Pure Scheduling domain rules: no database, no framework, no network."""

import unittest
from datetime import UTC, datetime

from pydantic import ValidationError

from app.modules.scheduling.application.calcom_webhook import calcom_webhook_status, safe_webhook_metadata
from app.modules.scheduling.domain.booking import (
    activity_title,
    booking_end,
    booking_is_google,
    calcom_booking_fields,
    calcom_create_payload,
    is_google_booking,
    safe_provider_summary,
)
from app.modules.scheduling.domain.contracts import CreateBookingCommand
from app.modules.scheduling.domain.errors import (
    BookingCustomerNotFoundError,
    BookingNotFoundError,
    SchedulingConfigurationError,
    SchedulingError,
)


class ProviderSelectionTests(unittest.TestCase):
    def test_new_booking_uses_google_when_configured_or_in_insert_mode(self) -> None:
        self.assertTrue(is_google_booking("google_calendar", "cal_managed"))
        self.assertTrue(is_google_booking("calcom", "crm_google_insert"))
        self.assertFalse(is_google_booking("calcom", "cal_managed"))
        self.assertFalse(is_google_booking(None, None))

    def test_existing_booking_is_google_by_provider_or_event_id(self) -> None:
        self.assertTrue(booking_is_google("google_calendar", None))
        self.assertTrue(booking_is_google("calcom", "evt_1"))
        self.assertFalse(booking_is_google("calcom", None))
        self.assertFalse(booking_is_google("calcom", ""))


class CalComMappingTests(unittest.TestCase):
    def test_response_fields_default_status_and_unwrap_data(self) -> None:
        fields = calcom_booking_fields({"data": {"id": 7, "uid": "u7", "status": "ACCEPTED", "meeting_url": "https://m"}})
        self.assertEqual(fields["provider_booking_id"], "7")
        self.assertEqual(fields["provider_booking_uid"], "u7")
        self.assertEqual(fields["status"], "accepted")
        self.assertEqual(fields["meeting_url"], "https://m")

    def test_empty_ids_mean_keep_current_and_status_defaults_to_accepted(self) -> None:
        fields = calcom_booking_fields({})
        self.assertIsNone(fields["provider_booking_id"])
        self.assertIsNone(fields["provider_booking_uid"])
        self.assertEqual(fields["status"], "accepted")

    def test_booking_uid_alias_and_flat_response(self) -> None:
        self.assertEqual(calcom_booking_fields({"bookingUid": "b1"})["provider_booking_uid"], "b1")
        self.assertEqual(safe_provider_summary({"data": {"id": 1, "bookingUid": "b1", "status": "x", "secret": "no"}}),
                         {"provider_booking_id": 1, "provider_booking_uid": "b1", "status": "x"})

    def test_create_payload_carries_ids_but_never_the_tenant(self) -> None:
        payload = calcom_create_payload(
            start_at=datetime(2026, 7, 2, 15, 0, tzinfo=UTC),
            attendee_name="Pedro", attendee_email="p@example.com", attendee_phone="+573001112233",
            attendee_timezone="America/Bogota", language="es",
            booking_fields_responses={"source": "voice", "x": 1},
            booking_id="b1", lead_id="l1", contact_id="c1",
            event_type_id=5, event_type_slug="demo", username="u", team_slug="t", organization_slug="org",
        )
        self.assertEqual(payload["start"], "2026-07-02T15:00:00Z")
        self.assertEqual(payload["bookingFieldsResponses"]["source"], "crm")  # CRM stamp wins
        self.assertEqual(payload["metadata"]["crm_booking_id"], "b1")
        self.assertEqual(payload["metadata"]["tenant_slug"], "org")
        self.assertEqual(payload["eventTypeId"], 5)
        self.assertNotIn("tenant_id", payload)
        self.assertNotIn("tenant_id", payload["metadata"])

    def test_create_payload_omits_unset_routing(self) -> None:
        payload = calcom_create_payload(
            start_at=datetime(2026, 7, 2, 15, 0), attendee_name="P", attendee_email="p@example.com",
            attendee_phone=None, attendee_timezone="UTC", language="es", booking_fields_responses={},
            booking_id="b", lead_id=None, contact_id=None, event_type_id=None, event_type_slug=None,
            username=None, team_slug=None, organization_slug=None,
        )
        for key in ("eventTypeId", "eventTypeSlug", "username", "teamSlug", "organizationSlug"):
            self.assertNotIn(key, payload)
        self.assertNotIn("tenant_slug", payload["metadata"])


class BookingRulesTests(unittest.TestCase):
    def test_end_and_activity_titles(self) -> None:
        self.assertEqual(booking_end(datetime(2026, 1, 1, 10, 0), 45), datetime(2026, 1, 1, 10, 45))
        self.assertEqual(activity_title("booking_failed"), "Reserva fallida")
        self.assertEqual(activity_title("unknown_type"), "unknown_type")

    def test_webhook_status_and_metadata_whitelist(self) -> None:
        self.assertEqual(calcom_webhook_status("BOOKING_CANCELLED", {}), "cancelled")
        self.assertEqual(calcom_webhook_status("BOOKING_CREATED", {"status": "PENDING"}), "pending")
        self.assertEqual(calcom_webhook_status("OTHER", {}), "updated")
        self.assertEqual(
            safe_webhook_metadata({"metadata": {"crm_booking_id": "b", "source": "serviglobal_crm", "api_key": "no"}}),
            {"crm_booking_id": "b", "crm_lead_id": "", "source": "serviglobal_crm"},
        )
        self.assertEqual(safe_webhook_metadata({"metadata": "nope"}), {})


class CommandAndErrorTests(unittest.TestCase):
    def test_validated_keeps_the_http_contract_constraints(self) -> None:
        command = CreateBookingCommand.validated(start="2026-07-02T15:00:00Z", attendee_name="P", attendee_email="p@x.co")
        self.assertEqual((command.timezone, command.notes, dict(command.booking_fields_responses)), ("America/Bogota", None, {}))
        for bad in (
            {"attendee_name": ""},
            {"attendee_email": "x"},
            {"attendee_phone": "1" * 81},
            {"notes": {"not": "a string"}},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                CreateBookingCommand.validated(
                    **{"start": "2026-07-02T15:00:00Z", "attendee_name": "P", "attendee_email": "p@x.co", **bad}
                )

    def test_command_is_immutable(self) -> None:
        command = CreateBookingCommand(start="s", attendee_name="n", attendee_email="e@x.co")
        with self.assertRaises(Exception):
            command.start = "other"  # type: ignore[misc]

    def test_business_errors_are_value_errors_with_the_historic_messages(self) -> None:
        for error, message in (
            (BookingNotFoundError(), "Booking not found"),
            (BookingCustomerNotFoundError(), "Lead not found"),
        ):
            self.assertIsInstance(error, ValueError)
            self.assertIsInstance(error, SchedulingError)
            self.assertEqual(str(error), message)
        self.assertTrue(issubclass(SchedulingConfigurationError, ValueError))


class BookingConsistencyDomainTests(unittest.TestCase):
    def test_half_open_overlap(self) -> None:
        from datetime import timedelta

        from app.modules.scheduling.domain.booking import SLOT_BLOCKING_STATUSES, intervals_overlap

        t = datetime(2030, 1, 1, 15, tzinfo=UTC)
        h = timedelta(minutes=30)
        self.assertTrue(intervals_overlap(t, t + 2 * h, t + h, t + 3 * h))
        self.assertFalse(intervals_overlap(t, t + h, t + h, t + 2 * h))  # adjacent
        self.assertTrue({"pending", "accepted", "scheduled"} <= SLOT_BLOCKING_STATUSES)
        self.assertFalse({"failed", "cancelled"} & SLOT_BLOCKING_STATUSES)

    def test_key_normalisation(self) -> None:
        from app.modules.scheduling.domain.operations import normalize_idempotency_key

        self.assertIsNone(normalize_idempotency_key(None))
        self.assertIsNone(normalize_idempotency_key("  "))
        self.assertEqual(normalize_idempotency_key(" voice:s1:abc-1 "), "voice:s1:abc-1")
        for bad in ("a b", "x" * 129, "ñ", "a/b"):
            with self.assertRaises(ValueError):
                normalize_idempotency_key(bad)

    def test_fingerprints_are_deterministic_and_discriminating(self) -> None:
        from app.modules.scheduling.domain.operations import create_fingerprint, reschedule_fingerprint

        t = datetime(2030, 1, 1, 15, tzinfo=UTC)
        base = dict(tenant_id="t", lead_id="l", start_at=t, timezone="UTC", resource_id="r")
        self.assertEqual(create_fingerprint(**base), create_fingerprint(**base))
        self.assertNotEqual(create_fingerprint(**base), create_fingerprint(**{**base, "start_at": t.replace(hour=16)}))
        self.assertNotEqual(create_fingerprint(**base), create_fingerprint(**{**base, "tenant_id": "t2"}))
        self.assertNotEqual(
            reschedule_fingerprint(booking_id="b", new_start_at=t), reschedule_fingerprint(booking_id="b", new_start_at=t.replace(hour=16))
        )

    def test_outcome_unknown_classification(self) -> None:
        from app.modules.scheduling.domain.operations import is_outcome_unknown

        class ReadTimeout(Exception):
            pass

        wrapped = ValueError("Google failed")
        wrapped.__cause__ = ReadTimeout("slow")
        self.assertTrue(is_outcome_unknown(wrapped))
        self.assertTrue(is_outcome_unknown(TimeoutError()))
        self.assertFalse(is_outcome_unknown(ValueError("400 bad request")))

    def test_new_errors_stay_business_errors(self) -> None:
        from app.modules.scheduling.domain.errors import (
            BookingOperationInProgressError,
            IdempotencyConflictError,
            SlotConflictError,
        )

        for cls in (SlotConflictError, IdempotencyConflictError, BookingOperationInProgressError):
            self.assertTrue(issubclass(cls, SchedulingError) and issubclass(cls, ValueError))


if __name__ == "__main__":
    unittest.main()
