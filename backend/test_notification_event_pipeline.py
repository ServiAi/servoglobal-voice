from __future__ import annotations

import inspect
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import event as sa_event, select

TEST_DB_PATH = Path("serviai_notification_event_pipeline_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.crm import CrmBooking, CrmBookingEvent, CrmContact, CrmLead, CrmPipelineStage, CrmVoiceCall
from app.models.identity import Tenant
from app.models.integrations import TenantIntegrationEvent, TenantWhatsAppConfig, TenantWhatsAppTemplate
from app.models.notifications import (
    DomainEvent,
    NotificationDelivery,
    TenantCapability,
    TenantNotificationRecipient,
    TenantNotificationRule,
)
from app.services.secret_manager_service import SecretManager
from app.services.whatsapp_client import WhatsAppCloudClient, WhatsAppCloudClientError
from app.services import notification_event_pipeline as pipeline_module
from app.services.notification_event_pipeline import (
    NotificationEventPipeline,
    run_booking_notification_pipeline_task,
    run_call_notification_pipeline_task,
)

from _integrations_2a_test_base import Integration2ATestCase


@sa_event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


NOW = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
PAST = datetime(2026, 7, 1, 9, 0, 0, tzinfo=timezone.utc)
FUTURE = datetime(2026, 12, 1, 9, 0, 0, tzinfo=timezone.utc)


class _FakeWhatsAppClient(WhatsAppCloudClient):
    def __init__(self, *, fail_phones: set[str] | None = None, message_id: str = "wamid.pipeline-1") -> None:
        super().__init__()
        self.fail_phones = fail_phones or set()
        self.message_id = message_id
        self.send_calls = 0
        self.sent_to: list[str] = []

    def send_template_message(self, config, *, to_phone, template_name, language, components=None):
        self.send_calls += 1
        self.sent_to.append(to_phone)
        if to_phone in self.fail_phones:
            raise WhatsAppCloudClientError("Simulated failure")
        return {"messages": [{"id": f"{self.message_id}-{self.send_calls}"}]}


class _BasePipelineTestCase(unittest.TestCase):
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
        self.client = _FakeWhatsAppClient()
        self.pipeline = NotificationEventPipeline(self.db, whatsapp_client=self.client)

    def tearDown(self):
        self.db.close()

    # ------------------------------------------------------------------
    # fixtures
    # ------------------------------------------------------------------
    def _create_tenant(self) -> str:
        slug = f"tenant-{uuid4().hex[:8]}"
        tenant = Tenant(name=f"Empresa {slug}", slug=slug)
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant.id

    def _configure_whatsapp(self, tenant_id: str) -> TenantWhatsAppConfig:
        config = TenantWhatsAppConfig(
            tenant_id=tenant_id,
            provider="whatsapp_cloud",
            status="active",
            phone_number_id=f"phone-{uuid4().hex[:6]}",
            display_phone_number="+573000000000",
            default_language="es",
            access_token_encrypted=SecretManager().encrypt_secret("EA_test_token_1234567890"),
        )
        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config

    def _create_template(self, tenant_id: str, *, template_key: str = "tpl_pipeline") -> TenantWhatsAppTemplate:
        variables_json = {
            "parameters": [{"key": "1", "label": "Variable 1"}],
            "meta_status": "APPROVED",
            "source": "meta_sync",
        }
        template = TenantWhatsAppTemplate(
            tenant_id=tenant_id,
            template_key=template_key,
            provider_template_name=template_key,
            name=template_key,
            category="utility",
            language="es",
            body="Hola, tu estado es {{1}}",
            variables_json=variables_json,
            status="active",
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    def _enable_capability(self, tenant_id: str, *, capability_key: str = "booking_notifications") -> None:
        self.db.add(TenantCapability(tenant_id=tenant_id, capability_key=capability_key, enabled=True))
        self.db.commit()

    def _create_rule(
        self,
        tenant_id: str,
        *,
        event_type: str,
        template_key: str,
        capability_key: str = "booking_notifications",
        path: str = "booking.status",
        **overrides,
    ) -> TenantNotificationRule:
        defaults = dict(
            tenant_id=tenant_id,
            name=f"rule-{uuid4().hex[:8]}",
            capability_key=capability_key,
            event_type=event_type,
            channel="whatsapp",
            action_type="send_whatsapp_template",
            template_key=template_key,
            recipient_strategy="event_customer",
            recipient_group_key=None,
            conditions_json=[],
            variable_mapping_json={"1": {"source": "event_field", "path": path}},
            schedule_mode="immediate",
            schedule_offset_minutes=0,
            priority=100,
            enabled=True,
        )
        defaults.update(overrides)
        rule = TenantNotificationRule(**defaults)
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def _create_lead(self, tenant_id: str, *, phone: str = "+573001112233", email: str = "lead@example.com"):
        stage = CrmPipelineStage(tenant_id=tenant_id, key="new", name="Nuevo", position=1, is_default=True)
        contact = CrmContact(tenant_id=tenant_id, name="Contacto Test", phone=phone, email=email)
        self.db.add_all([stage, contact])
        self.db.commit()
        self.db.refresh(stage)
        self.db.refresh(contact)
        lead = CrmLead(tenant_id=tenant_id, contact_id=contact.id, current_stage_id=stage.id, status="open")
        self.db.add(lead)
        self.db.commit()
        self.db.refresh(lead)
        return lead.id, contact.id

    def _create_booking(
        self,
        tenant_id: str,
        *,
        lead_id: str | None = None,
        status: str = "accepted",
        start_at: datetime = PAST,
        end_at: datetime | None = None,
        phone: str | None = "+573001112233",
        email: str = "lead@example.com",
        name: str = "Pedro Gomez",
        metadata_json: dict | None = None,
        provider_booking_uid: str = "uid-1",
    ) -> CrmBooking:
        booking = CrmBooking(
            tenant_id=tenant_id,
            lead_id=lead_id,
            contact_id=None,
            provider="calcom",
            provider_booking_id="123",
            provider_booking_uid=provider_booking_uid,
            title="Reserva Cal.com",
            status=status,
            start_at=start_at,
            end_at=end_at or (start_at + timedelta(minutes=30)),
            timezone="America/Bogota",
            duration_minutes=30,
            attendee_name=name,
            attendee_email=email,
            attendee_phone=phone,
            calendar_mode="cal_managed",
            metadata_json=metadata_json or {},
        )
        self.db.add(booking)
        self.db.commit()
        self.db.refresh(booking)
        return booking

    def _create_call(
        self,
        tenant_id: str,
        *,
        lead_id: str | None = None,
        contact_id: str | None = None,
        status: str = "completed",
        summary: str | None = "Resumen de la llamada",
        duration_seconds: int | None = 90,
        provider_call_id: str = "call-uid-1",
    ) -> CrmVoiceCall:
        call = CrmVoiceCall(
            tenant_id=tenant_id,
            lead_id=lead_id,
            contact_id=contact_id,
            provider="ultravox",
            provider_call_id=provider_call_id,
            direction="outbound",
            status=status,
            summary=summary,
            duration_seconds=duration_seconds,
        )
        self.db.add(call)
        self.db.commit()
        self.db.refresh(call)
        return call

    def _deliveries_for(self, tenant_id: str) -> list[NotificationDelivery]:
        return list(
            self.db.scalars(select(NotificationDelivery).where(NotificationDelivery.tenant_id == tenant_id)).all()
        )

    def _events_for(self, tenant_id: str, *, event_type: str | None = None) -> list[DomainEvent]:
        query = select(DomainEvent).where(DomainEvent.tenant_id == tenant_id)
        if event_type:
            query = query.where(DomainEvent.event_type == event_type)
        return list(self.db.scalars(query).all())


# ---------------------------------------------------------------------------
# Booking event pipeline
# ---------------------------------------------------------------------------
class BookingEventPipelineTests(_BasePipelineTestCase):
    def test_booking_created_creates_domain_event(self):
        tenant_id = self._create_tenant()
        booking = self._create_booking(tenant_id)

        result = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )

        self.assertTrue(result.event_created)
        events = self._events_for(tenant_id, event_type="booking.created")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source, "crm_booking")
        self.assertEqual(events[0].resource_id, booking.id)

    def test_booking_payload_includes_booking_customer_lead(self):
        tenant_id = self._create_tenant()
        lead_id, _ = self._create_lead(tenant_id)
        booking = self._create_booking(tenant_id, lead_id=lead_id)

        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        event = self._events_for(tenant_id, event_type="booking.created")[0]
        payload = event.payload_json

        self.assertIn("booking", payload)
        self.assertEqual(payload["booking"]["id"], booking.id)
        self.assertIn("customer", payload)
        self.assertEqual(payload["customer"]["phone"], "+573001112233")
        self.assertIn("lead", payload)
        self.assertEqual(payload["lead"]["id"], lead_id)

    def test_booking_payload_excludes_full_metadata_and_only_copies_notification_custom(self):
        tenant_id = self._create_tenant()
        booking = self._create_booking(
            tenant_id,
            metadata_json={
                "source": "serviglobal_crm",
                "voice_booking_config_id": "vbc-1",
                "notification_custom": {"advisor_name": "Ana"},
            },
        )

        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        payload = self._events_for(tenant_id, event_type="booking.created")[0].payload_json

        self.assertEqual(payload["custom"], {"advisor_name": "Ana"})
        self.assertEqual(set(payload.keys()) <= {"booking", "customer", "lead", "custom"}, True)
        self.assertNotIn("source", payload)
        self.assertNotIn("voice_booking_config_id", payload)

    def test_booking_payload_has_no_secret_like_keys(self):
        tenant_id = self._create_tenant()
        booking = self._create_booking(tenant_id)

        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        payload_text = json.dumps(self._events_for(tenant_id, event_type="booking.created")[0].payload_json)

        for forbidden in ("access_token", "api_key", "client_secret", "Authorization", "Bearer"):
            self.assertNotIn(forbidden, payload_text)

    def test_booking_created_repeat_does_not_duplicate_event_or_delivery_or_resend(self):
        tenant_id = self._create_tenant()
        self._configure_whatsapp(tenant_id)
        template = self._create_template(tenant_id)
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id, event_type="booking.created", template_key=template.template_key)
        booking = self._create_booking(tenant_id)

        first = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        second = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )

        self.assertTrue(first.event_created)
        self.assertFalse(second.event_created)
        self.assertEqual(len(self._events_for(tenant_id, event_type="booking.created")), 1)
        self.assertEqual(len(self._deliveries_for(tenant_id)), 1)
        self.assertEqual(self.client.send_calls, 1)

    def test_booking_cancelled_creates_event_and_repeat_does_not_duplicate(self):
        tenant_id = self._create_tenant()
        booking = self._create_booking(tenant_id, status="cancelled")

        first = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.cancelled", now=NOW
        )
        second = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.cancelled", now=NOW
        )

        self.assertTrue(first.event_created)
        self.assertFalse(second.event_created)
        self.assertEqual(len(self._events_for(tenant_id, event_type="booking.cancelled")), 1)

    def test_booking_rescheduled_idempotency_across_repeats_and_new_dates(self):
        tenant_id = self._create_tenant()
        booking = self._create_booking(tenant_id, status="scheduled", start_at=PAST)

        first = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.rescheduled", now=NOW
        )
        repeat = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.rescheduled", now=NOW
        )
        self.assertTrue(first.event_created)
        self.assertFalse(repeat.event_created)
        self.assertEqual(len(self._events_for(tenant_id, event_type="booking.rescheduled")), 1)

        # A second, genuinely different reschedule must create a distinct event.
        booking.start_at = PAST + timedelta(days=1)
        booking.end_at = booking.start_at + timedelta(minutes=30)
        self.db.commit()
        self.db.refresh(booking)

        second = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.rescheduled", now=NOW
        )
        self.assertTrue(second.event_created)
        self.assertEqual(len(self._events_for(tenant_id, event_type="booking.rescheduled")), 2)

    def test_booking_other_tenant_cannot_be_processed(self):
        tenant_id = self._create_tenant()
        other_tenant_id = self._create_tenant()
        booking = self._create_booking(tenant_id)

        result = self.pipeline.process_booking_event(
            tenant_id=other_tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "booking_not_found")
        self.assertEqual(len(self._events_for(other_tenant_id)), 0)

    def test_booking_not_found_returns_safe_result(self):
        tenant_id = self._create_tenant()

        result = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id="does-not-exist", event_type="booking.created", now=NOW
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "booking_not_found")

    def test_no_rules_creates_zero_deliveries(self):
        tenant_id = self._create_tenant()
        booking = self._create_booking(tenant_id)

        result = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )

        self.assertEqual(result.status, "processed")
        self.assertEqual(result.planned_delivery_count, 0)
        self.assertEqual(len(self._deliveries_for(tenant_id)), 0)

    def test_capability_disabled_creates_zero_deliveries(self):
        tenant_id = self._create_tenant()
        self._configure_whatsapp(tenant_id)
        template = self._create_template(tenant_id)
        self._create_rule(tenant_id, event_type="booking.created", template_key=template.template_key)
        booking = self._create_booking(tenant_id)
        # capability intentionally left disabled/absent

        result = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )

        self.assertEqual(result.planned_delivery_count, 0)
        self.assertEqual(len(self._deliveries_for(tenant_id)), 0)

    def test_immediate_rule_creates_and_executes_delivery(self):
        tenant_id = self._create_tenant()
        self._configure_whatsapp(tenant_id)
        template = self._create_template(tenant_id)
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id, event_type="booking.created", template_key=template.template_key)
        booking = self._create_booking(tenant_id)

        result = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )

        self.assertEqual(result.status, "processed")
        self.assertEqual(result.sent_count, 1)
        self.assertEqual(self.client.send_calls, 1)
        deliveries = self._deliveries_for(tenant_id)
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0].status, "sent")

    def test_future_reminder_stays_pending_and_does_not_call_meta(self):
        tenant_id = self._create_tenant()
        self._configure_whatsapp(tenant_id)
        template = self._create_template(tenant_id)
        self._enable_capability(tenant_id)
        self._create_rule(
            tenant_id,
            event_type="booking.created",
            template_key=template.template_key,
            schedule_mode="relative_to_booking",
            schedule_offset_minutes=-60,
        )
        booking = self._create_booking(tenant_id, start_at=FUTURE)

        result = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )

        self.assertEqual(result.status, "processed")
        self.assertEqual(result.pending_count, 1)
        self.assertEqual(result.sent_count, 0)
        self.assertEqual(self.client.send_calls, 0)
        deliveries = self._deliveries_for(tenant_id)
        self.assertEqual(deliveries[0].status, "pending")

    def test_meta_failure_does_not_revert_booking(self):
        tenant_id = self._create_tenant()
        self._configure_whatsapp(tenant_id)
        template = self._create_template(tenant_id)
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id, event_type="booking.created", template_key=template.template_key)
        booking = self._create_booking(tenant_id, status="accepted")

        failing_pipeline = NotificationEventPipeline(
            self.db, whatsapp_client=_FakeWhatsAppClient(fail_phones={"573001112233"})
        )
        result = failing_pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.failed_count, 1)
        refreshed = self.db.scalar(select(CrmBooking).where(CrmBooking.id == booking.id))
        self.assertEqual(refreshed.status, "accepted")

    def test_invalid_rule_does_not_revert_booking(self):
        tenant_id = self._create_tenant()
        self._enable_capability(tenant_id)
        self._create_rule(
            tenant_id,
            event_type="booking.created",
            template_key="does-not-matter",
            recipient_strategy="configured_group",
            recipient_group_key=None,
        )
        booking = self._create_booking(tenant_id, status="accepted")

        result = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )

        self.assertEqual(result.status, "failed")
        refreshed = self.db.scalar(select(CrmBooking).where(CrmBooking.id == booking.id))
        self.assertEqual(refreshed.status, "accepted")

    def test_email_present_does_not_trigger_email_send(self):
        tenant_id = self._create_tenant()
        self._configure_whatsapp(tenant_id)
        template = self._create_template(tenant_id)
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id, event_type="booking.created", template_key=template.template_key)
        booking = self._create_booking(tenant_id, email="cliente@example.com")

        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )

        deliveries = self._deliveries_for(tenant_id)
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0].channel, "whatsapp")

    def test_only_whatsapp_deliveries_are_executed(self):
        tenant_id = self._create_tenant()
        self._configure_whatsapp(tenant_id)
        template = self._create_template(tenant_id)
        self._enable_capability(tenant_id)
        rule = self._create_rule(tenant_id, event_type="booking.created", template_key=template.template_key)
        booking = self._create_booking(tenant_id)

        # Publish the event and plan it, then hand-craft a non-whatsapp delivery to prove it is skipped.
        result = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        event = self._events_for(tenant_id, event_type="booking.created")[0]
        rogue = NotificationDelivery(
            tenant_id=tenant_id,
            domain_event_id=event.id,
            notification_rule_id=rule.id,
            channel="email",
            recipient="cliente@example.com",
            template_key=rule.template_key,
            status="pending",
            scheduled_for=PAST,
            attempts=0,
            idempotency_key=f"rogue-{uuid4().hex[:8]}",
            metadata_json={},
        )
        self.db.add(rogue)
        self.db.commit()

        calls_before = self.client.send_calls
        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        self.db.refresh(rogue)
        self.assertEqual(rogue.status, "pending")
        self.assertEqual(self.client.send_calls, calls_before)


# ---------------------------------------------------------------------------
# Call event pipeline
# ---------------------------------------------------------------------------
class CallEventPipelineTests(_BasePipelineTestCase):
    def test_status_mapping_to_domain_event_types(self):
        tenant_id = self._create_tenant()
        cases = {
            "completed": "call.completed",
            "failed": "call.failed",
            "no_answer": "call.no_answer",
            "busy": "call.no_answer",
        }
        for status, expected_event_type in cases.items():
            with self.subTest(status=status):
                call = self._create_call(tenant_id, status=status, provider_call_id=f"call-{status}")
                result = self.pipeline.process_call_event(
                    tenant_id=tenant_id, voice_call_id=call.id, now=NOW
                )
                self.assertEqual(result.status, "processed")
                events = self._events_for(tenant_id, event_type=expected_event_type)
                self.assertTrue(any(e.resource_id == call.id for e in events))

    def test_intermediate_statuses_are_ignored(self):
        tenant_id = self._create_tenant()
        for status in ("queued", "ringing", "in_progress", "cancelled", "requested"):
            with self.subTest(status=status):
                call = self._create_call(tenant_id, status=status, provider_call_id=f"call-{status}")
                result = self.pipeline.process_call_event(
                    tenant_id=tenant_id, voice_call_id=call.id, now=NOW
                )
                self.assertEqual(result.status, "ignored")
                self.assertEqual(result.error_code, "call_status_not_notifiable")
                self.assertEqual(len(self._events_for(tenant_id)), 0)

    def test_call_payload_includes_call_contact_and_lead(self):
        tenant_id = self._create_tenant()
        lead_id, contact_id = self._create_lead(tenant_id, phone="+573009998877")
        call = self._create_call(tenant_id, lead_id=lead_id, contact_id=contact_id)

        self.pipeline.process_call_event(tenant_id=tenant_id, voice_call_id=call.id, now=NOW)
        event = self._events_for(tenant_id, event_type="call.completed")[0]
        payload = event.payload_json

        self.assertEqual(payload["call"]["id"], call.id)
        self.assertEqual(payload["customer"]["phone"], "+573009998877")
        self.assertEqual(payload["lead"]["id"], lead_id)

    def test_call_payload_excludes_sensitive_and_direct_phone_fields(self):
        tenant_id = self._create_tenant()
        call = self._create_call(tenant_id)
        call.recording_url = "https://storage.example/rec.mp3"
        call.transcript_url = "https://storage.example/transcript.txt"
        call.to_phone = "+573001112233"
        call.from_number = "+573000000000"
        self.db.commit()

        self.pipeline.process_call_event(tenant_id=tenant_id, voice_call_id=call.id, now=NOW)
        payload_text = json.dumps(self._events_for(tenant_id, event_type="call.completed")[0].payload_json)

        self.assertNotIn("recording_url", payload_text)
        self.assertNotIn("transcript_url", payload_text)
        self.assertNotIn("to_phone", payload_text)
        self.assertNotIn("from_number", payload_text)
        self.assertNotIn("+573000000000", payload_text)

    def test_call_summary_is_truncated_to_4000_characters(self):
        tenant_id = self._create_tenant()
        call = self._create_call(tenant_id, summary="x" * 5000)

        self.pipeline.process_call_event(tenant_id=tenant_id, voice_call_id=call.id, now=NOW)
        payload = self._events_for(tenant_id, event_type="call.completed")[0].payload_json

        self.assertEqual(len(payload["call"]["summary"]), 4000)

    def test_call_completed_repeat_does_not_duplicate_event_or_delivery(self):
        tenant_id = self._create_tenant()
        self._configure_whatsapp(tenant_id)
        template = self._create_template(tenant_id)
        self._enable_capability(tenant_id, capability_key="call_notifications")
        self._create_rule(
            tenant_id,
            event_type="call.completed",
            template_key=template.template_key,
            capability_key="call_notifications",
            path="call.status",
        )
        lead_id, contact_id = self._create_lead(tenant_id)
        call = self._create_call(tenant_id, lead_id=lead_id, contact_id=contact_id)

        first = self.pipeline.process_call_event(tenant_id=tenant_id, voice_call_id=call.id, now=NOW)
        second = self.pipeline.process_call_event(tenant_id=tenant_id, voice_call_id=call.id, now=NOW)

        self.assertTrue(first.event_created)
        self.assertFalse(second.event_created)
        self.assertEqual(len(self._events_for(tenant_id, event_type="call.completed")), 1)
        self.assertEqual(len(self._deliveries_for(tenant_id)), 1)
        self.assertEqual(self.client.send_calls, 1)

    def test_call_other_tenant_cannot_be_processed(self):
        tenant_id = self._create_tenant()
        other_tenant_id = self._create_tenant()
        call = self._create_call(tenant_id)

        result = self.pipeline.process_call_event(tenant_id=other_tenant_id, voice_call_id=call.id, now=NOW)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "voice_call_not_found")

    def test_unreconciled_call_does_not_create_event(self):
        tenant_id = self._create_tenant()

        result = self.pipeline.process_call_event(tenant_id=tenant_id, voice_call_id="unknown", now=NOW)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "voice_call_not_found")
        self.assertEqual(len(self._events_for(tenant_id)), 0)


# ---------------------------------------------------------------------------
# Planning & execution
# ---------------------------------------------------------------------------
class PlanningAndExecutionTests(_BasePipelineTestCase):
    def _setup_immediate_rule(self, tenant_id: str, **rule_overrides) -> TenantWhatsAppTemplate:
        self._configure_whatsapp(tenant_id)
        template = self._create_template(tenant_id)
        self._enable_capability(tenant_id)
        self._create_rule(
            tenant_id, event_type="booking.created", template_key=template.template_key, **rule_overrides
        )
        return template

    def test_existing_event_recovers_pending_delivery(self):
        tenant_id = self._create_tenant()
        self._setup_immediate_rule(
            tenant_id, schedule_mode="relative_to_booking", schedule_offset_minutes=-60
        )
        booking = self._create_booking(tenant_id, start_at=FUTURE)

        first = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        self.assertEqual(first.pending_count, 1)

        later = self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        self.assertFalse(later.event_created)
        self.assertEqual(later.planned_delivery_count, 1)
        self.assertEqual(len(self._deliveries_for(tenant_id)), 1)

    def test_failed_delivery_is_not_retried_in_this_phase(self):
        tenant_id = self._create_tenant()
        self._setup_immediate_rule(tenant_id)
        booking = self._create_booking(tenant_id)

        failing_pipeline = NotificationEventPipeline(
            self.db, whatsapp_client=_FakeWhatsAppClient(fail_phones={"573001112233"})
        )
        failing_pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        deliveries = self._deliveries_for(tenant_id)
        self.assertEqual(deliveries[0].status, "failed")

        calls_before = failing_pipeline._whatsapp_client.send_calls
        result = failing_pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        self.assertEqual(failing_pipeline._whatsapp_client.send_calls, calls_before)
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.sent_count, 0)

    def test_sent_delivered_read_deliveries_are_not_reexecuted(self):
        tenant_id = self._create_tenant()
        self._setup_immediate_rule(tenant_id)
        booking = self._create_booking(tenant_id)

        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        delivery = self._deliveries_for(tenant_id)[0]
        for terminal_status in ("delivered", "read"):
            delivery.status = terminal_status
            self.db.commit()
            calls_before = self.client.send_calls
            result = self.pipeline.process_booking_event(
                tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
            )
            self.assertEqual(self.client.send_calls, calls_before)
            self.assertEqual(result.sent_count, 1)

    def test_one_failed_recipient_does_not_block_another_and_result_is_partial(self):
        tenant_id = self._create_tenant()
        self._configure_whatsapp(tenant_id)
        template = self._create_template(tenant_id)
        self._enable_capability(tenant_id)
        self.db.add_all(
            [
                TenantNotificationRecipient(
                    tenant_id=tenant_id,
                    group_key="advisors",
                    name="Asesor 1",
                    channel="whatsapp",
                    destination="+573001110001",
                    status="active",
                ),
                TenantNotificationRecipient(
                    tenant_id=tenant_id,
                    group_key="advisors",
                    name="Asesor 2",
                    channel="whatsapp",
                    destination="+573001110002",
                    status="active",
                ),
            ]
        )
        self.db.commit()
        self._create_rule(
            tenant_id,
            event_type="booking.created",
            template_key=template.template_key,
            recipient_strategy="configured_group",
            recipient_group_key="advisors",
        )
        booking = self._create_booking(tenant_id)

        mixed_pipeline = NotificationEventPipeline(
            self.db, whatsapp_client=_FakeWhatsAppClient(fail_phones={"573001110002"})
        )
        result = mixed_pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.sent_count, 1)
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(len(self._deliveries_for(tenant_id)), 2)

    def test_no_second_notification_delivery_is_created_on_repeat(self):
        tenant_id = self._create_tenant()
        self._setup_immediate_rule(tenant_id)
        booking = self._create_booking(tenant_id)

        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        self.assertEqual(len(self._deliveries_for(tenant_id)), 1)

    def test_idempotency_keys_do_not_contain_phone_numbers(self):
        tenant_id = self._create_tenant()
        self._setup_immediate_rule(tenant_id)
        booking = self._create_booking(tenant_id, phone="+573001112233")

        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        event = self._events_for(tenant_id, event_type="booking.created")[0]
        delivery = self._deliveries_for(tenant_id)[0]

        self.assertNotIn("+573001112233", event.idempotency_key)
        self.assertNotIn("+573001112233", delivery.idempotency_key)

    def test_no_external_service_besides_injected_fake_client_is_used(self):
        tenant_id = self._create_tenant()
        self._setup_immediate_rule(tenant_id)
        booking = self._create_booking(tenant_id)

        with patch("app.services.whatsapp_client.httpx.Client") as real_http_client:
            self.pipeline.process_booking_event(
                tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
            )
        real_http_client.assert_not_called()
        self.assertEqual(self.client.send_calls, 1)

    def test_provider_failure_schedules_a_retry_via_retry_policy(self):
        tenant_id = self._create_tenant()
        self._setup_immediate_rule(tenant_id)
        booking = self._create_booking(tenant_id)

        failing_pipeline = NotificationEventPipeline(
            self.db, whatsapp_client=_FakeWhatsAppClient(fail_phones={"573001112233"})
        )
        failing_pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        delivery = self._deliveries_for(tenant_id)[0]
        self.assertEqual(delivery.status, "failed")
        self.assertIsNotNone(delivery.next_attempt_at)
        self.assertIsNone(delivery.claim_token)


# ---------------------------------------------------------------------------
# Schedule reconciliation (Phase 6)
# ---------------------------------------------------------------------------
class ScheduleReconciliationPipelineTests(_BasePipelineTestCase):
    def _setup_reminder_rule(self, tenant_id: str) -> None:
        self._configure_whatsapp(tenant_id)
        template = self._create_template(tenant_id)
        self._enable_capability(tenant_id)
        self._create_rule(
            tenant_id,
            event_type="booking.created",
            template_key=template.template_key,
            schedule_mode="relative_to_booking",
            schedule_offset_minutes=-60,
        )
        self._create_rule(
            tenant_id,
            event_type="booking.rescheduled",
            template_key=template.template_key,
            schedule_mode="relative_to_booking",
            schedule_offset_minutes=-60,
            name="regla-pipeline-rescheduled",
        )

    def test_booking_cancelled_cancels_prior_pending_reminder(self):
        tenant_id = self._create_tenant()
        self._setup_reminder_rule(tenant_id)
        booking = self._create_booking(tenant_id, start_at=FUTURE)

        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        pending_delivery = self._deliveries_for(tenant_id)[0]
        self.assertEqual(pending_delivery.status, "pending")

        booking.status = "cancelled"
        self.db.add(booking)
        self.db.commit()
        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.cancelled", now=NOW
        )

        self.db.refresh(pending_delivery)
        self.assertEqual(pending_delivery.status, "cancelled")
        self.assertIsNone(pending_delivery.next_attempt_at)

    def test_booking_rescheduled_cancels_prior_pending_reminder(self):
        tenant_id = self._create_tenant()
        self._setup_reminder_rule(tenant_id)
        booking = self._create_booking(tenant_id, start_at=FUTURE)

        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        pending_delivery = self._deliveries_for(tenant_id)[0]

        booking.start_at = FUTURE + timedelta(days=1)
        booking.end_at = booking.start_at + timedelta(minutes=30)
        self.db.add(booking)
        self.db.commit()
        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.rescheduled", now=NOW
        )

        self.db.refresh(pending_delivery)
        self.assertEqual(pending_delivery.status, "cancelled")
        self.assertEqual(pending_delivery.error_message, "booking_schedule_superseded")

    def test_reconciliation_does_not_touch_other_bookings(self):
        tenant_id = self._create_tenant()
        self._setup_reminder_rule(tenant_id)
        untouched_booking = self._create_booking(tenant_id, start_at=FUTURE, provider_booking_uid="uid-untouched")
        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=untouched_booking.id, event_type="booking.created", now=NOW
        )
        untouched_delivery = self._deliveries_for(tenant_id)[0]

        other_booking = self._create_booking(tenant_id, start_at=FUTURE, provider_booking_uid="uid-other")
        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=other_booking.id, event_type="booking.created", now=NOW
        )
        other_booking.status = "cancelled"
        self.db.add(other_booking)
        self.db.commit()
        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=other_booking.id, event_type="booking.cancelled", now=NOW
        )

        self.db.refresh(untouched_delivery)
        self.assertEqual(untouched_delivery.status, "pending")

    def test_call_event_does_not_trigger_reconciliation(self):
        tenant_id = self._create_tenant()
        self._configure_whatsapp(tenant_id)
        template = self._create_template(tenant_id)
        self._enable_capability(tenant_id, capability_key="call_notifications")
        self._create_rule(
            tenant_id,
            event_type="call.completed",
            template_key=template.template_key,
            capability_key="call_notifications",
            path="call.status",
        )
        call = self._create_call(tenant_id)
        result = self.pipeline.process_call_event(tenant_id=tenant_id, voice_call_id=call.id, now=NOW)
        # No exception, no crm_booking reconciliation side effects — the call
        # pipeline result must complete normally.
        self.assertIn(result.status, ("processed", "partial"))


# ---------------------------------------------------------------------------
# BookingService integration
# ---------------------------------------------------------------------------
class BookingServiceIntegrationTests(Integration2ATestCase):
    def test_successful_booking_invokes_pipeline_with_correct_tenant(self):
        self.configure_calcom()
        lead_id, _ = self.seed_lead()

        with patch("app.services.booking_service.CalComClient.create_booking") as create_booking, patch(
            "app.services.booking_service.NotificationEventPipeline.process_booking_event"
        ) as process_event:
            create_booking.return_value = {"data": {"id": 1, "uid": "uid-1", "status": "accepted"}}
            response = self.client.post(
                f"/api/v1/crm/leads/{lead_id}/bookings",
                json={
                    "start": "2026-07-02T15:00:00Z",
                    "attendee_name": "Pedro Gomez",
                    "attendee_email": "lead@example.com",
                    "attendee_phone": "+573001112233",
                },
            )

        self.assertEqual(response.status_code, 200)
        process_event.assert_called_once()
        kwargs = process_event.call_args.kwargs
        self.assertEqual(kwargs["tenant_id"], self.tenant.id)
        self.assertEqual(kwargs["event_type"], "booking.created")

    def test_failed_booking_does_not_invoke_pipeline(self):
        from app.services.booking_service import BookingService
        from app.schemas.crm import BookingCreateRequest

        self.configure_calcom()
        lead_id, _ = self.seed_lead()

        with patch("app.services.booking_service.CalComClient.create_booking") as create_booking, patch(
            "app.services.booking_service.NotificationEventPipeline.process_booking_event"
        ) as process_event:
            create_booking.side_effect = RuntimeError("cal.com is down")
            with SessionLocal() as db, self.assertRaises(RuntimeError):
                BookingService(db).create_lead_booking(
                    tenant_id=self.tenant.id,
                    lead_id=lead_id,
                    body=BookingCreateRequest(
                        start="2026-07-02T15:00:00Z",
                        attendee_name="Pedro Gomez",
                        attendee_email="lead@example.com",
                    ),
                )

        process_event.assert_not_called()
        process_event.assert_not_called()

    def test_pipeline_error_does_not_change_successful_booking_response(self):
        self.configure_calcom()
        lead_id, _ = self.seed_lead()

        with patch("app.services.booking_service.CalComClient.create_booking") as create_booking, patch(
            "app.services.booking_service.NotificationEventPipeline.process_booking_event"
        ) as process_event:
            create_booking.return_value = {"data": {"id": 1, "uid": "uid-1", "status": "accepted"}}
            process_event.side_effect = RuntimeError("boom")
            response = self.client.post(
                f"/api/v1/crm/leads/{lead_id}/bookings",
                json={
                    "start": "2026-07-02T15:00:00Z",
                    "attendee_name": "Pedro Gomez",
                    "attendee_email": "lead@example.com",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "accepted")

    def test_cancellation_invokes_booking_cancelled(self):
        self.configure_calcom()
        lead_id, contact_id = self.seed_lead()
        from app.services.booking_service import BookingService

        with SessionLocal() as db:
            from datetime import UTC, datetime as dt

            booking = CrmBooking(
                tenant_id=self.tenant.id,
                lead_id=lead_id,
                contact_id=contact_id,
                provider="calcom",
                provider_booking_uid="uid-cancel",
                status="accepted",
                start_at=dt(2026, 7, 2, 15, 0, tzinfo=UTC),
                end_at=dt(2026, 7, 2, 15, 30, tzinfo=UTC),
                timezone="America/Bogota",
                attendee_name="Pedro Gomez",
                attendee_email="lead@example.com",
                calendar_mode="cal_managed",
            )
            db.add(booking)
            db.commit()
            db.refresh(booking)
            booking_id = booking.id

            with patch("app.services.booking_service.CalComClient.cancel_booking") as cancel_booking, patch(
                "app.services.booking_service.NotificationEventPipeline.process_booking_event"
            ) as process_event:
                cancel_booking.return_value = {"data": {"status": "cancelled"}}
                BookingService(db).cancel_lead_booking(tenant_id=self.tenant.id, booking_id=booking_id)

        process_event.assert_called_once()
        self.assertEqual(process_event.call_args.kwargs["event_type"], "booking.cancelled")

    def test_reschedule_invokes_booking_rescheduled_and_persists_new_dates(self):
        self.configure_calcom()
        lead_id, contact_id = self.seed_lead()
        from app.services.booking_service import BookingService
        from datetime import UTC, datetime as dt

        with SessionLocal() as db:
            booking = CrmBooking(
                tenant_id=self.tenant.id,
                lead_id=lead_id,
                contact_id=contact_id,
                provider="calcom",
                provider_booking_uid="uid-resched",
                status="accepted",
                start_at=dt(2026, 7, 2, 15, 0, tzinfo=UTC),
                end_at=dt(2026, 7, 2, 15, 30, tzinfo=UTC),
                timezone="America/Bogota",
                duration_minutes=30,
                attendee_name="Pedro Gomez",
                attendee_email="lead@example.com",
                calendar_mode="cal_managed",
            )
            db.add(booking)
            db.commit()
            db.refresh(booking)
            booking_id = booking.id

            with patch("app.services.booking_service.CalComClient.reschedule_booking") as reschedule_booking, patch(
                "app.services.booking_service.NotificationEventPipeline.process_booking_event"
            ) as process_event:
                reschedule_booking.return_value = {"data": {"status": "accepted"}}
                BookingService(db).reschedule_lead_booking(
                    tenant_id=self.tenant.id, booking_id=booking_id, new_start_time="2026-07-03T16:00:00Z"
                )

            refreshed = db.get(CrmBooking, booking_id)
            # SQLite drops tzinfo on round-trip; compare wall-clock values instead of
            # calling astimezone() (which would reinterpret a naive value as local time).
            self.assertEqual(refreshed.start_at.replace(tzinfo=None), dt(2026, 7, 3, 16, 0))
            self.assertEqual(refreshed.end_at.replace(tzinfo=None), dt(2026, 7, 3, 16, 30))

        process_event.assert_called_once()
        self.assertEqual(process_event.call_args.kwargs["event_type"], "booking.rescheduled")


# ---------------------------------------------------------------------------
# Cal.com webhook
# ---------------------------------------------------------------------------
class CalComWebhookNotificationTests(Integration2ATestCase):
    def _seed_booking(self, *, lead_id, contact_id, start=None):
        from datetime import UTC, datetime as dt

        with SessionLocal() as db:
            booking = CrmBooking(
                tenant_id=self.tenant.id,
                lead_id=lead_id,
                contact_id=contact_id,
                provider="calcom",
                status="pending",
                start_at=start or dt(2026, 7, 2, 15, 0, tzinfo=UTC),
                end_at=(start or dt(2026, 7, 2, 15, 0, tzinfo=UTC)) + timedelta(minutes=30),
                timezone="America/Bogota",
                attendee_name="Pedro Gomez",
                attendee_email="lead@example.com",
                calendar_mode="cal_managed",
            )
            db.add(booking)
            db.commit()
            db.refresh(booking)
            return booking.id

    def _post_webhook(self, trigger_event, booking_id, lead_id, extra_payload=None):
        payload = {
            "triggerEvent": trigger_event,
            "payload": {
                "id": 1,
                "uid": "uid-1",
                "status": "accepted",
                "startTime": "2026-07-02T15:00:00Z",
                "metadata": {"crm_booking_id": booking_id, "crm_lead_id": lead_id, "source": "serviglobal_crm"},
                **(extra_payload or {}),
            },
        }
        with patch.dict(os.environ, {"CALCOM_WEBHOOK_SECRET": ""}):
            return self.client.post("/api/v1/calcom/webhook", json=payload)

    def test_booking_created_cancelled_rescheduled_schedule_background_task(self):
        lead_id, contact_id = self.seed_lead()
        for trigger_event in ("BOOKING_CREATED", "BOOKING_CANCELLED", "BOOKING_RESCHEDULED"):
            with self.subTest(trigger_event=trigger_event):
                booking_id = self._seed_booking(lead_id=lead_id, contact_id=contact_id)
                with patch(
                    "app.api.endpoints.calcom.run_booking_notification_pipeline_task"
                ) as run_task:
                    response = self._post_webhook(trigger_event, booking_id, lead_id)

                self.assertEqual(response.status_code, 200)
                run_task.assert_called_once()
                kwargs = run_task.call_args.kwargs
                self.assertEqual(set(kwargs.keys()), {"tenant_id", "booking_id", "event_type"})
                self.assertEqual(kwargs["tenant_id"], self.tenant.id)
                self.assertEqual(kwargs["booking_id"], booking_id)

    def test_webhook_does_not_call_legacy_notification_service_or_meta(self):
        lead_id, contact_id = self.seed_lead()
        booking_id = self._seed_booking(lead_id=lead_id, contact_id=contact_id)

        with patch(
            "app.services.notification_service.notification_service.notify_new_booking"
        ) as legacy_notify, patch("app.services.meta_client.meta_client.send_template") as meta_send:
            response = self._post_webhook("BOOKING_CREATED", booking_id, lead_id)

        self.assertEqual(response.status_code, 200)
        legacy_notify.assert_not_called()
        meta_send.assert_not_called()

    def test_unreconciled_booking_does_not_schedule_notification(self):
        payload = {
            "triggerEvent": "BOOKING_CREATED",
            "payload": {"id": 1, "uid": "uid-1", "status": "accepted", "startTime": "2026-07-02T15:00:00Z"},
        }
        with patch.dict(os.environ, {"CALCOM_WEBHOOK_SECRET": ""}), patch(
            "app.api.endpoints.calcom.run_booking_notification_pipeline_task"
        ) as run_task:
            response = self.client.post("/api/v1/calcom/webhook", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ignored", "reason": "booking_unreconciled"})
        run_task.assert_not_called()

    def test_repeated_webhook_is_idempotent(self):
        lead_id, contact_id = self.seed_lead()
        booking_id = self._seed_booking(lead_id=lead_id, contact_id=contact_id)

        for _ in range(2):
            response = self._post_webhook("BOOKING_CREATED", booking_id, lead_id)
            self.assertEqual(response.status_code, 200)

        with SessionLocal() as db:
            events = list(
                db.scalars(select(DomainEvent).where(DomainEvent.resource_id == booking_id)).all()
            )
        self.assertEqual(len(events), 1)

    def test_hmac_signature_validation_still_works(self):
        import hashlib
        import hmac as hmac_module

        body = json.dumps({"triggerEvent": "BOOKING_CREATED", "payload": {}}).encode("utf-8")
        signature = hmac_module.new(b"hook-secret", body, digestmod=hashlib.sha256).hexdigest()

        with patch.dict(os.environ, {"CALCOM_WEBHOOK_SECRET": "hook-secret"}):
            response = self.client.post(
                "/api/v1/calcom/webhook",
                content=body,
                headers={"Content-Type": "application/json", "X-Cal-Signature-256": signature},
            )
        self.assertEqual(response.status_code, 200)

    def test_response_does_not_expose_tenant_or_booking_id(self):
        lead_id, contact_id = self.seed_lead()
        booking_id = self._seed_booking(lead_id=lead_id, contact_id=contact_id)

        response = self._post_webhook("BOOKING_CREATED", booking_id, lead_id)
        body = response.json()

        self.assertNotIn("tenant_id", body)
        self.assertNotIn("booking_id", body)
        self.assertNotIn(booking_id, json.dumps(body))
        self.assertNotIn(self.tenant.id, json.dumps(body))


class CalComWebhookHardeningTests(Integration2ATestCase):
    """Security-blocker fixes: source validation, provider/id reconciliation, sanitized errors."""

    def _seed_booking(
        self,
        *,
        lead_id=None,
        contact_id=None,
        provider="calcom",
        provider_booking_id=None,
        provider_booking_uid=None,
        status="pending",
        start=None,
    ):
        from datetime import UTC, datetime as dt

        with SessionLocal() as db:
            booking = CrmBooking(
                tenant_id=self.tenant.id,
                lead_id=lead_id,
                contact_id=contact_id,
                provider=provider,
                provider_booking_id=provider_booking_id,
                provider_booking_uid=provider_booking_uid,
                status=status,
                start_at=start or dt(2026, 7, 2, 15, 0, tzinfo=UTC),
                end_at=(start or dt(2026, 7, 2, 15, 0, tzinfo=UTC)) + timedelta(minutes=30),
                timezone="America/Bogota",
                attendee_name="Pedro Gomez",
                attendee_email="lead@example.com",
                calendar_mode="cal_managed",
            )
            db.add(booking)
            db.commit()
            db.refresh(booking)
            return booking.id

    def _post_webhook(self, *, metadata, trigger_event="BOOKING_CREATED", provider_id="1", provider_uid="uid-1"):
        payload = {
            "triggerEvent": trigger_event,
            "payload": {
                "id": provider_id,
                "uid": provider_uid,
                "status": "accepted",
                "startTime": "2026-07-02T15:00:00Z",
                "metadata": metadata,
            },
        }
        with patch.dict(os.environ, {"CALCOM_WEBHOOK_SECRET": ""}), patch(
            "app.api.endpoints.calcom.run_booking_notification_pipeline_task"
        ) as run_task:
            response = self.client.post("/api/v1/calcom/webhook", json=payload)
        return response, run_task

    def test_missing_source_is_unreconciled(self):
        lead_id, contact_id = self.seed_lead()
        booking_id = self._seed_booking(lead_id=lead_id, contact_id=contact_id)

        response, run_task = self._post_webhook(
            metadata={"crm_booking_id": booking_id, "crm_lead_id": lead_id}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ignored", "reason": "booking_unreconciled"})
        run_task.assert_not_called()

    def test_wrong_source_is_unreconciled(self):
        lead_id, contact_id = self.seed_lead()
        booking_id = self._seed_booking(lead_id=lead_id, contact_id=contact_id)

        response, run_task = self._post_webhook(
            metadata={"crm_booking_id": booking_id, "crm_lead_id": lead_id, "source": "external_system"}
        )

        self.assertEqual(response.json(), {"status": "ignored", "reason": "booking_unreconciled"})
        run_task.assert_not_called()

    def test_non_calcom_provider_booking_is_not_reconciled(self):
        lead_id, contact_id = self.seed_lead()
        booking_id = self._seed_booking(lead_id=lead_id, contact_id=contact_id, provider="google_calendar")

        response, run_task = self._post_webhook(
            metadata={"crm_booking_id": booking_id, "crm_lead_id": lead_id, "source": "serviglobal_crm"}
        )

        self.assertEqual(response.json(), {"status": "ignored", "reason": "booking_unreconciled"})
        run_task.assert_not_called()

    def test_mismatched_lead_id_is_not_reconciled(self):
        lead_id, contact_id = self.seed_lead()
        booking_id = self._seed_booking(lead_id=lead_id, contact_id=contact_id)

        response, run_task = self._post_webhook(
            metadata={
                "crm_booking_id": booking_id,
                "crm_lead_id": "someone-elses-lead-id",
                "source": "serviglobal_crm",
            }
        )

        self.assertEqual(response.json(), {"status": "ignored", "reason": "booking_unreconciled"})
        run_task.assert_not_called()

    def test_metadata_lead_present_but_booking_has_no_lead_is_not_reconciled(self):
        _, contact_id = self.seed_lead()
        booking_id = self._seed_booking(lead_id=None, contact_id=contact_id)

        response, run_task = self._post_webhook(
            metadata={"crm_booking_id": booking_id, "crm_lead_id": "some-lead-id", "source": "serviglobal_crm"}
        )

        self.assertEqual(response.json(), {"status": "ignored", "reason": "booking_unreconciled"})
        run_task.assert_not_called()

    def test_mismatched_provider_booking_uid_is_not_reconciled(self):
        lead_id, contact_id = self.seed_lead()
        booking_id = self._seed_booking(
            lead_id=lead_id, contact_id=contact_id, provider_booking_uid="existing-uid"
        )

        response, run_task = self._post_webhook(
            metadata={"crm_booking_id": booking_id, "crm_lead_id": lead_id, "source": "serviglobal_crm"},
            provider_uid="attacker-supplied-uid",
        )

        self.assertEqual(response.json(), {"status": "ignored", "reason": "booking_unreconciled"})
        run_task.assert_not_called()

    def test_mismatched_provider_booking_id_is_not_reconciled(self):
        lead_id, contact_id = self.seed_lead()
        booking_id = self._seed_booking(
            lead_id=lead_id, contact_id=contact_id, provider_booking_id="999"
        )

        response, run_task = self._post_webhook(
            metadata={"crm_booking_id": booking_id, "crm_lead_id": lead_id, "source": "serviglobal_crm"},
            provider_id="111",
        )

        self.assertEqual(response.json(), {"status": "ignored", "reason": "booking_unreconciled"})
        run_task.assert_not_called()

    def test_rejected_reconciliation_does_not_modify_booking_or_create_event_or_schedule_task(self):
        lead_id, contact_id = self.seed_lead()
        booking_id = self._seed_booking(
            lead_id=lead_id,
            contact_id=contact_id,
            provider_booking_uid="existing-uid",
            status="pending",
        )

        response, run_task = self._post_webhook(
            metadata={"crm_booking_id": booking_id, "crm_lead_id": lead_id, "source": "serviglobal_crm"},
            provider_uid="attacker-supplied-uid",
        )

        self.assertEqual(response.json(), {"status": "ignored", "reason": "booking_unreconciled"})
        run_task.assert_not_called()
        with SessionLocal() as db:
            booking = db.get(CrmBooking, booking_id)
            events = list(
                db.scalars(select(CrmBookingEvent).where(CrmBookingEvent.booking_id == booking_id)).all()
            )
        self.assertEqual(booking.status, "pending")
        self.assertEqual(booking.provider_booking_uid, "existing-uid")
        self.assertEqual(events, [])

    def test_internal_exception_returns_sanitized_error_and_does_not_log_exception_message(self):
        lead_id, contact_id = self.seed_lead()
        booking_id = self._seed_booking(lead_id=lead_id, contact_id=contact_id)

        with patch.dict(os.environ, {"CALCOM_WEBHOOK_SECRET": ""}), patch(
            "app.api.endpoints.calcom._sync_crm_booking_from_calcom_webhook"
        ) as sync_mock, patch("app.api.endpoints.calcom.logger.error") as error_log:
            sync_mock.side_effect = RuntimeError(
                "db error for secreto@example.com password=hunter2 select * from crm_bookings"
            )
            response = self.client.post(
                "/api/v1/calcom/webhook",
                json={
                    "triggerEvent": "BOOKING_CREATED",
                    "payload": {
                        "id": 1,
                        "uid": "uid-1",
                        "status": "accepted",
                        "startTime": "2026-07-02T15:00:00Z",
                        "metadata": {
                            "crm_booking_id": booking_id,
                            "crm_lead_id": lead_id,
                            "source": "serviglobal_crm",
                        },
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body, {"status": "error", "reason": "webhook_processing_failed"})
        self.assertNotIn("detail", body)

        logged = " ".join(str(call) for call in error_log.call_args_list)
        self.assertNotIn("secreto@example.com", logged)
        self.assertNotIn("hunter2", logged)
        self.assertNotIn("select * from crm_bookings", logged)
        self.assertIn("RuntimeError", logged)

    def test_valid_booking_created_flow_still_reconciles(self):
        lead_id, contact_id = self.seed_lead()
        booking_id = self._seed_booking(lead_id=lead_id, contact_id=contact_id)

        response, run_task = self._post_webhook(
            metadata={"crm_booking_id": booking_id, "crm_lead_id": lead_id, "source": "serviglobal_crm"}
        )

        self.assertEqual(response.json(), {"status": "processing_notifications"})
        run_task.assert_called_once()

    def test_valid_cancellation_and_reschedule_flows_still_work(self):
        lead_id, contact_id = self.seed_lead()
        for trigger_event in ("BOOKING_CANCELLED", "BOOKING_RESCHEDULED"):
            with self.subTest(trigger_event=trigger_event):
                booking_id = self._seed_booking(lead_id=lead_id, contact_id=contact_id)
                response, run_task = self._post_webhook(
                    trigger_event=trigger_event,
                    metadata={
                        "crm_booking_id": booking_id,
                        "crm_lead_id": lead_id,
                        "source": "serviglobal_crm",
                    },
                )
                self.assertEqual(response.json(), {"status": "processing_notifications"})
                run_task.assert_called_once()

    def test_hmac_signature_still_validated_with_hardened_reconciliation(self):
        import hashlib
        import hmac as hmac_module

        body = json.dumps({"triggerEvent": "BOOKING_CREATED", "payload": {}}).encode("utf-8")
        signature = hmac_module.new(b"hook-secret", body, digestmod=hashlib.sha256).hexdigest()
        invalid_signature = signature[:-1] + ("0" if signature[-1] != "0" else "1")

        with patch.dict(os.environ, {"CALCOM_WEBHOOK_SECRET": "hook-secret"}):
            response = self.client.post(
                "/api/v1/calcom/webhook",
                content=body,
                headers={"Content-Type": "application/json", "X-Cal-Signature-256": invalid_signature},
            )

        self.assertEqual(response.status_code, 403)

    def test_legacy_notification_service_remains_disconnected(self):
        lead_id, contact_id = self.seed_lead()
        booking_id = self._seed_booking(lead_id=lead_id, contact_id=contact_id)

        with patch(
            "app.services.notification_service.notification_service.notify_new_booking"
        ) as legacy_notify:
            response, run_task = self._post_webhook(
                metadata={"crm_booking_id": booking_id, "crm_lead_id": lead_id, "source": "serviglobal_crm"}
            )

        self.assertEqual(response.json(), {"status": "processing_notifications"})
        legacy_notify.assert_not_called()


# ---------------------------------------------------------------------------
# Voice webhook
# ---------------------------------------------------------------------------
class VoiceWebhookNotificationTests(Integration2ATestCase):
    def _seed_call(self, *, provider_call_id="call-1", lead_id=None, contact_id=None):
        if lead_id is None or contact_id is None:
            lead_id, contact_id = self.seed_lead(email=f"{uuid4().hex[:8]}@example.com")
        with SessionLocal() as db:
            call = CrmVoiceCall(
                tenant_id=self.tenant.id,
                lead_id=lead_id,
                contact_id=contact_id,
                provider="ultravox",
                provider_call_id=provider_call_id,
                direction="outbound",
                status="in_progress",
            )
            db.add(call)
            db.commit()
            db.refresh(call)
            return call.id

    def test_terminal_statuses_schedule_notification_task(self):
        lead_id, contact_id = self.seed_lead()
        cases = {
            "completed": {"status": "ended"},
            "failed": {"status": "failed"},
            "no_answer": {"status": "ended", "endReason": "no_answer"},
            "busy": {"status": "ended", "endReason": "busy"},
        }
        for expected_status, call_fields in cases.items():
            with self.subTest(expected_status=expected_status):
                call_id = self._seed_call(
                    provider_call_id=f"call-{expected_status}", lead_id=lead_id, contact_id=contact_id
                )
                payload = {"event": "call.ended", "call": {"id": f"call-{expected_status}", **call_fields}}
                with patch("app.api.endpoints.voice_webhook.run_call_notification_pipeline_task") as run_task:
                    response = self.client.post("/api/v1/voice/webhook/ultravox", json=payload)

                self.assertEqual(response.status_code, 200)
                run_task.assert_called_once()
                kwargs = run_task.call_args.kwargs
                self.assertEqual(set(kwargs.keys()), {"tenant_id", "voice_call_id"})
                self.assertEqual(kwargs["tenant_id"], self.tenant.id)
                self.assertEqual(kwargs["voice_call_id"], call_id)

    def test_intermediate_status_does_not_schedule_task(self):
        call_id = self._seed_call(provider_call_id="call-ringing")
        payload = {"event": "call.updated", "call": {"id": "call-ringing", "status": "ringing"}}
        with patch("app.api.endpoints.voice_webhook.run_call_notification_pipeline_task") as run_task:
            response = self.client.post("/api/v1/voice/webhook/ultravox", json=payload)

        self.assertEqual(response.status_code, 200)
        run_task.assert_not_called()

    def test_unreconciled_call_does_not_schedule_task(self):
        payload = {"event": "call.ended", "call": {"id": "unknown-call", "status": "ended"}}
        with patch("app.api.endpoints.voice_webhook.run_call_notification_pipeline_task") as run_task:
            response = self.client.post("/api/v1/voice/webhook/ultravox", json=payload)

        self.assertEqual(response.status_code, 200)
        run_task.assert_not_called()

    def test_pipeline_error_does_not_change_webhook_response(self):
        call_id = self._seed_call(provider_call_id="call-safe")
        payload = {"event": "call.ended", "call": {"id": "call-safe", "status": "ended"}}
        with patch(
            "app.services.notification_event_pipeline.NotificationEventPipeline.process_call_event"
        ) as process_event:
            process_event.side_effect = RuntimeError("boom")
            response = self.client.post("/api/v1/voice/webhook/ultravox", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "processed")

    def test_signature_validation_still_works_when_no_secret_configured(self):
        call_id = self._seed_call(provider_call_id="call-sig")
        payload = {"event": "call.ended", "call": {"id": "call-sig", "status": "ended"}}
        response = self.client.post("/api/v1/voice/webhook/ultravox", json=payload)
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
class NotificationEventPipelineSecurityTests(_BasePipelineTestCase):
    def test_no_payload_or_pii_is_logged_on_failure(self):
        tenant_id = self._create_tenant()
        self._configure_whatsapp(tenant_id)
        template = self._create_template(tenant_id)
        self._enable_capability(tenant_id)
        self._create_rule(tenant_id, event_type="booking.created", template_key=template.template_key)
        booking = self._create_booking(tenant_id, phone="+573001112233", email="secreto@example.com")

        failing_pipeline = NotificationEventPipeline(
            self.db, whatsapp_client=_FakeWhatsAppClient(fail_phones={"573001112233"})
        )
        with patch("app.services.notification_event_pipeline.logger.error") as error_log:
            failing_pipeline.process_booking_event(
                tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
            )

        logged = " ".join(str(call) for call in error_log.call_args_list)
        self.assertNotIn("+573001112233", logged)
        self.assertNotIn("secreto@example.com", logged)
        self.assertNotIn("Pedro Gomez", logged)

    def test_run_booking_task_does_not_raise_and_does_not_receive_pii(self):
        tenant_id = self._create_tenant()
        booking = self._create_booking(tenant_id)
        # The adapter must only accept identifiers, never payload/PII kwargs.
        params = inspect.signature(run_booking_notification_pipeline_task).parameters
        self.assertEqual(set(params.keys()), {"tenant_id", "booking_id", "event_type"})
        run_booking_notification_pipeline_task(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created"
        )

    def test_run_call_task_signature_is_identifiers_only(self):
        params = inspect.signature(run_call_notification_pipeline_task).parameters
        self.assertEqual(set(params.keys()), {"tenant_id", "voice_call_id"})

    def test_booking_payload_never_contains_calcom_or_ultravox_style_keys(self):
        tenant_id = self._create_tenant()
        booking = self._create_booking(tenant_id)
        self.pipeline.process_booking_event(
            tenant_id=tenant_id, booking_id=booking.id, event_type="booking.created", now=NOW
        )
        payload = self._events_for(tenant_id, event_type="booking.created")[0].payload_json
        self.assertLessEqual(set(payload.keys()), {"booking", "customer", "lead", "custom"})
        for forbidden in ("attendees", "responses", "recordingUrl", "transcriptUrl", "webhook"):
            self.assertNotIn(forbidden, payload)

    def test_platform_tenant_is_never_used(self):
        tenant_id = self._create_tenant()
        result = self.pipeline.process_call_event(tenant_id=tenant_id, voice_call_id="missing", now=NOW)
        self.assertEqual(result.status, "failed")
        events = list(
            self.db.scalars(select(TenantIntegrationEvent).where(TenantIntegrationEvent.tenant_id == "platform")).all()
        )
        self.assertEqual(events, [])

    def test_module_source_has_no_dynamic_execution_or_reflection_primitives(self):
        source = inspect.getsource(pipeline_module)
        for forbidden in ("eval(", "exec(", "getattr("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
