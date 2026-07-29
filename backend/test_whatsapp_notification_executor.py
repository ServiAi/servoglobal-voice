import copy
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import event as sa_event

TEST_DB_PATH = Path("serviai_whatsapp_notification_executor_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.domain.notification_variables import (
    NotificationVariableConfigurationError,
    NotificationVariableMappingError,
)
from app.models.crm import CrmActivity, CrmContact, CrmLead, CrmPipelineStage, CrmWhatsAppMessage
from app.models.identity import Tenant
from app.models.integrations import TenantIntegrationEvent, TenantWhatsAppConfig, TenantWhatsAppTemplate
from app.models.notifications import DomainEvent, NotificationDelivery, TenantNotificationRule
from app.services.domain_event_service import DomainEventService
from app.services.notification_delivery_claim_service import NotificationDeliveryClaimService
from app.services.notification_variable_mapper import NotificationVariableMapper
from app.services.secret_manager_service import SecretManager
from app.services.whatsapp_client import WhatsAppCloudClient, WhatsAppCloudClientError
from app.services.whatsapp_message_service import WhatsAppMessageService
from app.services.whatsapp_notification_executor import (
    WhatsAppNotificationExecutionError,
    WhatsAppNotificationExecutor,
)
from app.services.whatsapp_template_service import WhatsAppTemplateService


@sa_event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


FIXED_NOW = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
PAST_SCHEDULE = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
FUTURE_SCHEDULE = datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)

DEFAULT_VARIABLE_MAPPING = {
    "1": {"source": "event_field", "path": "custom.advisor_name"},
    "2": {
        "source": "event_field",
        "path": "booking.start_at",
        "format": "datetime_dmy_24h",
        "timezone": "America/Bogota",
    },
}


def _make_payload(*, lead_id=None, advisor_name="Ana", start_at="2026-08-10T15:30:00+00:00", customer_phone="+573001112233"):
    payload = {
        "booking": {"id": "bk-1", "status": "confirmed", "start_at": start_at, "timezone": "America/Bogota"},
        "customer": {"phone": customer_phone},
        "custom": {"advisor_name": advisor_name},
    }
    if lead_id:
        payload["lead"] = {"id": lead_id, "status": "qualified"}
    return payload


class _FakeWhatsAppClient(WhatsAppCloudClient):
    def __init__(self, *, fail: bool = False, error_message: str = "Simulated failure", message_id: str = "wamid.exec-1"):
        super().__init__()
        self.fail = fail
        self.error_message = error_message
        self.message_id = message_id
        self.send_calls = 0

    def send_template_message(self, *args, **kwargs):
        self.send_calls += 1
        if self.fail:
            raise WhatsAppCloudClientError(self.error_message)
        return {"messages": [{"id": self.message_id}]}


class _BaseExecutorTestCase(unittest.TestCase):
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

    def tearDown(self):
        self.db.close()

    def _create_tenant(self, slug: str) -> str:
        tenant = Tenant(name=f"Empresa {slug}", slug=slug)
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant.id

    def _configure_whatsapp(self, tenant_id: str, *, phone_number_id: str = "phone-1") -> TenantWhatsAppConfig:
        config = TenantWhatsAppConfig(
            tenant_id=tenant_id,
            provider="whatsapp_cloud",
            status="active",
            phone_number_id=phone_number_id,
            display_phone_number="+573000000000",
            default_language="es",
            access_token_encrypted=SecretManager().encrypt_secret("EA_test_token_1234567890"),
        )
        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config

    def _create_synced_template(
        self,
        tenant_id: str,
        *,
        template_key: str = "tpl_meeting",
        keys: tuple[str, ...] = ("1", "2"),
        body: str = "Hola, tu asesor es {{1}}. Cita: {{2}}",
        approved: bool = True,
    ) -> TenantWhatsAppTemplate:
        variables_json = {"parameters": [{"key": key, "label": f"Variable {key}"} for key in keys]}
        if approved:
            variables_json["meta_status"] = "APPROVED"
            variables_json["source"] = "meta_sync"
        template = TenantWhatsAppTemplate(
            tenant_id=tenant_id,
            template_key=template_key,
            provider_template_name=template_key,
            name=template_key,
            category="utility",
            language="es",
            body=body,
            variables_json=variables_json,
            status="active",
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    def _create_rule(self, tenant_id: str, **overrides) -> TenantNotificationRule:
        defaults = dict(
            tenant_id=tenant_id,
            name=f"regla-{uuid4().hex[:8]}",
            capability_key="booking_notifications",
            event_type="booking.created",
            channel="whatsapp",
            action_type="send_whatsapp_template",
            template_key="tpl_meeting",
            recipient_strategy="event_customer",
            recipient_group_key=None,
            conditions_json=[],
            variable_mapping_json=copy.deepcopy(DEFAULT_VARIABLE_MAPPING),
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

    def _create_lead(self, tenant_id: str, *, phone: str = "+573001112233") -> tuple[str, str]:
        stage = CrmPipelineStage(tenant_id=tenant_id, key="new", name="Nuevo", position=1, is_default=True)
        contact = CrmContact(tenant_id=tenant_id, name="Lead Test", phone=phone)
        self.db.add_all([stage, contact])
        self.db.commit()
        self.db.refresh(stage)
        self.db.refresh(contact)
        lead = CrmLead(tenant_id=tenant_id, contact_id=contact.id, current_stage_id=stage.id, status="open")
        self.db.add(lead)
        self.db.commit()
        self.db.refresh(lead)
        return lead.id, contact.id

    def _create_event(self, tenant_id: str, payload: dict, *, event_type: str = "booking.created"):
        return DomainEventService(self.db).publish(
            tenant_id=tenant_id,
            event_type=event_type,
            source="calcom",
            idempotency_key=f"evt-{uuid4().hex[:8]}",
            payload=payload,
            available_at=PAST_SCHEDULE,
        ).event

    def _create_delivery(
        self,
        tenant_id: str,
        event,
        rule: TenantNotificationRule,
        *,
        recipient: str = "+573001112233",
        status: str = "pending",
        scheduled_for: datetime = PAST_SCHEDULE,
    ) -> NotificationDelivery:
        delivery = NotificationDelivery(
            tenant_id=tenant_id,
            domain_event_id=event.id,
            notification_rule_id=rule.id,
            channel="whatsapp",
            recipient=recipient,
            template_key=rule.template_key,
            status=status,
            scheduled_for=scheduled_for,
            attempts=0,
            idempotency_key=f"delivery-{uuid4().hex[:8]}",
            metadata_json={},
        )
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return delivery

    def _seed_happy_path(
        self,
        *,
        status: str = "pending",
        scheduled_for: datetime = PAST_SCHEDULE,
        with_lead: bool = True,
        phone_number_id: str = "phone-1",
    ) -> dict:
        tenant_id = self._create_tenant(f"tenant-{uuid4().hex[:8]}")
        self._configure_whatsapp(tenant_id, phone_number_id=phone_number_id)
        template = self._create_synced_template(tenant_id)
        rule = self._create_rule(tenant_id, template_key=template.template_key)
        lead_id = contact_id = None
        if with_lead:
            lead_id, contact_id = self._create_lead(tenant_id)
        payload = _make_payload(lead_id=lead_id)
        event = self._create_event(tenant_id, payload)
        delivery = self._create_delivery(tenant_id, event, rule, status=status, scheduled_for=scheduled_for)
        return {
            "tenant_id": tenant_id,
            "template": template,
            "rule": rule,
            "event": event,
            "delivery": delivery,
            "lead_id": lead_id,
            "contact_id": contact_id,
        }


# ---------------------------------------------------------------------------
# Mapeador de variables — 1 a 15
# ---------------------------------------------------------------------------
class NotificationVariableMapperTests(unittest.TestCase):
    def setUp(self):
        self.mapper = NotificationVariableMapper()

    def test_string_field(self):
        mapping = {"var": {"source": "event_field", "path": "custom.name"}}
        payload = {"custom": {"name": "Ana"}}
        result = self.mapper.map_variables(tenant_id="t1", rule_id="r1", mapping=mapping, payload=payload)
        self.assertEqual(result["var"], "Ana")

    def test_literal(self):
        mapping = {"var": {"source": "literal", "value": "Hola"}}
        result = self.mapper.map_variables(tenant_id="t1", rule_id="r1", mapping=mapping, payload={})
        self.assertEqual(result["var"], "Hola")

    def test_missing_required_field_raises(self):
        mapping = {"var": {"source": "event_field", "path": "custom.missing"}}
        with self.assertRaises(NotificationVariableMappingError) as cm:
            self.mapper.map_variables(tenant_id="t1", rule_id="r1", mapping=mapping, payload={"custom": {}})
        self.assertEqual(cm.exception.code, "required_field_missing")

    def test_missing_optional_field_is_omitted(self):
        mapping = {"var": {"source": "event_field", "path": "custom.missing", "required": False}}
        result = self.mapper.map_variables(tenant_id="t1", rule_id="r1", mapping=mapping, payload={"custom": {}})
        self.assertNotIn("var", result)

    def test_default_is_used_when_missing(self):
        mapping = {"var": {"source": "event_field", "path": "custom.missing", "default": "N/A"}}
        result = self.mapper.map_variables(tenant_id="t1", rule_id="r1", mapping=mapping, payload={"custom": {}})
        self.assertEqual(result["var"], "N/A")

    def test_invalid_path_rejected(self):
        mapping = {"var": {"source": "event_field", "path": "custom.__class__"}}
        with self.assertRaises(NotificationVariableConfigurationError):
            self.mapper.map_variables(tenant_id="t1", rule_id="r1", mapping=mapping, payload={"custom": {}})

    def test_dict_or_list_value_rejected(self):
        mapping = {"var": {"source": "event_field", "path": "custom.data"}}
        with self.assertRaises(NotificationVariableMappingError) as cm:
            self.mapper.map_variables(
                tenant_id="t1", rule_id="r1", mapping=mapping, payload={"custom": {"data": {"a": 1}}}
            )
        self.assertEqual(cm.exception.code, "field_value_type_not_allowed")

    def test_date_iso_format(self):
        mapping = {"var": {"source": "event_field", "path": "custom.dt", "format": "date_iso"}}
        payload = {"custom": {"dt": "2026-08-10T10:30:00-05:00"}}
        result = self.mapper.map_variables(tenant_id="t1", rule_id="r1", mapping=mapping, payload=payload)
        self.assertEqual(result["var"], "2026-08-10")

    def test_date_dmy_format(self):
        mapping = {"var": {"source": "event_field", "path": "custom.dt", "format": "date_dmy"}}
        payload = {"custom": {"dt": "2026-08-10T10:30:00-05:00"}}
        result = self.mapper.map_variables(tenant_id="t1", rule_id="r1", mapping=mapping, payload=payload)
        self.assertEqual(result["var"], "10/08/2026")

    def test_time_24h_format(self):
        mapping = {"var": {"source": "event_field", "path": "custom.dt", "format": "time_24h"}}
        payload = {"custom": {"dt": "2026-08-10T10:30:00-05:00"}}
        result = self.mapper.map_variables(tenant_id="t1", rule_id="r1", mapping=mapping, payload=payload)
        self.assertEqual(result["var"], "10:30")

    def test_timezone_conversion(self):
        mapping = {
            "var": {
                "source": "event_field",
                "path": "custom.dt",
                "format": "datetime_dmy_24h",
                "timezone": "America/Bogota",
            }
        }
        payload = {"custom": {"dt": "2026-08-10T15:30:00+00:00"}}
        result = self.mapper.map_variables(tenant_id="t1", rule_id="r1", mapping=mapping, payload=payload)
        self.assertEqual(result["var"], "10/08/2026 10:30")

    def test_invalid_timezone_rejected(self):
        mapping = {
            "var": {
                "source": "event_field",
                "path": "custom.dt",
                "format": "date_iso",
                "timezone": "Not/AZone",
            }
        }
        payload = {"custom": {"dt": "2026-08-10T10:30:00-05:00"}}
        with self.assertRaises(NotificationVariableMappingError) as cm:
            self.mapper.map_variables(tenant_id="t1", rule_id="r1", mapping=mapping, payload=payload)
        self.assertEqual(cm.exception.code, "invalid_timezone")

    def test_naive_datetime_rejected(self):
        mapping = {"var": {"source": "event_field", "path": "custom.dt", "format": "date_iso"}}
        payload = {"custom": {"dt": "2026-08-10T10:30:00"}}
        with self.assertRaises(NotificationVariableMappingError) as cm:
            self.mapper.map_variables(tenant_id="t1", rule_id="r1", mapping=mapping, payload=payload)
        self.assertEqual(cm.exception.code, "datetime_naive_not_allowed")

    def test_mapping_not_mutated(self):
        mapping = {"var": {"source": "literal", "value": "hello"}}
        original = copy.deepcopy(mapping)
        self.mapper.map_variables(tenant_id="t1", rule_id="r1", mapping=mapping, payload={})
        self.assertEqual(mapping, original)

    def test_payload_not_mutated(self):
        mapping = {"var": {"source": "event_field", "path": "custom.name"}}
        payload = {"custom": {"name": "Ana"}}
        original = copy.deepcopy(payload)
        self.mapper.map_variables(tenant_id="t1", rule_id="r1", mapping=mapping, payload=payload)
        self.assertEqual(payload, original)


# ---------------------------------------------------------------------------
# Plantillas aprobadas — 16 a 20
# ---------------------------------------------------------------------------
class WhatsAppApprovedTemplateTests(_BaseExecutorTestCase):
    def setUp(self):
        super().setUp()
        self.tenant_id = self._create_tenant("template-tenant")
        self.templates = WhatsAppTemplateService(self.db)

    def test_parameters_keep_meta_order(self):
        template = self._create_synced_template(self.tenant_id, keys=("2", "1"), body="Hola {{2}} {{1}}")
        variables = {"1": "uno", "2": "dos"}
        components = self.templates.build_approved_template_components(template, variables)
        texts = [item["text"] for item in components[0]["parameters"]]
        self.assertEqual(texts, ["dos", "uno"])

    def test_missing_required_variable_raises(self):
        template = self._create_synced_template(self.tenant_id)
        with self.assertRaises(ValueError):
            self.templates.build_approved_template_components(template, {"1": "solo uno"})

    def test_template_without_parameters_produces_empty_components(self):
        template = self._create_synced_template(self.tenant_id, keys=(), body="Hola sin variables")
        components = self.templates.build_approved_template_components(template, {})
        self.assertEqual(components, [])

    def test_unapproved_template_rejected(self):
        template = self._create_synced_template(self.tenant_id, approved=False)
        with self.assertRaisesRegex(ValueError, "approved by Meta"):
            self.templates.get_synced_template(
                self.tenant_id, template_key=template.template_key, provider_template_name=None
            )

    def test_template_from_other_tenant_rejected(self):
        template = self._create_synced_template(self.tenant_id)
        other_tenant_id = self._create_tenant("other-template-tenant")
        with self.assertRaises(ValueError):
            self.templates.get_synced_template(
                other_tenant_id, template_key=template.template_key, provider_template_name=None
            )


# ---------------------------------------------------------------------------
# Ejecutor — 21 a 49
# ---------------------------------------------------------------------------
class WhatsAppNotificationExecutorTests(_BaseExecutorTestCase):
    def test_pending_due_delivery_sends(self):
        ctx = self._seed_happy_path()
        client = _FakeWhatsAppClient()
        result = WhatsAppNotificationExecutor(self.db, client=client).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "sent")
        self.assertEqual(client.send_calls, 1)

    def test_future_delivery_returns_not_due(self):
        ctx = self._seed_happy_path(scheduled_for=FUTURE_SCHEDULE)
        result = WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "not_due")

    def test_not_due_does_not_increment_attempts(self):
        ctx = self._seed_happy_path(scheduled_for=FUTURE_SCHEDULE)
        WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].attempts, 0)

    def test_sent_delivery_does_not_resend(self):
        ctx = self._seed_happy_path(status="sent")
        client = _FakeWhatsAppClient()
        result = WhatsAppNotificationExecutor(self.db, client=client).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "already_completed")
        self.assertEqual(client.send_calls, 0)

    def test_delivered_delivery_does_not_resend(self):
        ctx = self._seed_happy_path(status="delivered")
        client = _FakeWhatsAppClient()
        result = WhatsAppNotificationExecutor(self.db, client=client).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "already_completed")
        self.assertEqual(client.send_calls, 0)

    def test_read_delivery_does_not_resend(self):
        ctx = self._seed_happy_path(status="read")
        client = _FakeWhatsAppClient()
        result = WhatsAppNotificationExecutor(self.db, client=client).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "already_completed")
        self.assertEqual(client.send_calls, 0)

    def test_skipped_delivery_does_not_send(self):
        ctx = self._seed_happy_path(status="skipped")
        client = _FakeWhatsAppClient()
        result = WhatsAppNotificationExecutor(self.db, client=client).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "skipped")
        self.assertEqual(client.send_calls, 0)

    def test_cancelled_delivery_does_not_send(self):
        ctx = self._seed_happy_path(status="cancelled")
        client = _FakeWhatsAppClient()
        result = WhatsAppNotificationExecutor(self.db, client=client).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "cancelled")
        self.assertEqual(client.send_calls, 0)

    def test_processing_delivery_is_rejected(self):
        ctx = self._seed_happy_path(status="processing")
        with self.assertRaises(WhatsAppNotificationExecutionError) as cm:
            WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
                tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
            )
        self.assertEqual(cm.exception.code, "delivery_already_processing")

    def test_execution_increments_attempts(self):
        ctx = self._seed_happy_path()
        WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].attempts, 1)

    def test_uses_correct_tenant_configuration(self):
        ctx = self._seed_happy_path()
        result = WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.message.tenant_id, ctx["tenant_id"])

    def test_uses_correct_tenant_template(self):
        ctx = self._seed_happy_path()
        result = WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.message.template_id, ctx["template"].id)

    def test_does_not_cross_tenants(self):
        ctx_a = self._seed_happy_path()
        ctx_b = self._seed_happy_path()
        WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
            tenant_id=ctx_a["tenant_id"], delivery_id=ctx_a["delivery"].id, now=FIXED_NOW
        )
        self.db.refresh(ctx_b["delivery"])
        self.assertEqual(ctx_b["delivery"].status, "pending")
        count = self.db.query(CrmWhatsAppMessage).filter(CrmWhatsAppMessage.tenant_id == ctx_b["tenant_id"]).count()
        self.assertEqual(count, 0)

    def test_tenant_mismatch_is_rejected(self):
        ctx_a = self._seed_happy_path()
        ctx_b = self._seed_happy_path()
        delivery = self._create_delivery(ctx_a["tenant_id"], ctx_b["event"], ctx_b["rule"], scheduled_for=PAST_SCHEDULE)
        with self.assertRaises(WhatsAppNotificationExecutionError) as cm:
            WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
                tenant_id=ctx_a["tenant_id"], delivery_id=delivery.id, now=FIXED_NOW
            )
        self.assertEqual(cm.exception.code, "delivery_related_records_missing")

    def test_creates_crm_whatsapp_message(self):
        ctx = self._seed_happy_path()
        WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        count = self.db.query(CrmWhatsAppMessage).filter(CrmWhatsAppMessage.tenant_id == ctx["tenant_id"]).count()
        self.assertEqual(count, 1)

    def test_saves_provider_message_id(self):
        ctx = self._seed_happy_path()
        client = _FakeWhatsAppClient(message_id="wamid.custom-1")
        result = WhatsAppNotificationExecutor(self.db, client=client).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.delivery.provider_message_id, "wamid.custom-1")

    def test_delivery_ends_sent(self):
        ctx = self._seed_happy_path()
        result = WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.delivery.status, "sent")
        self.assertIsNotNone(result.delivery.sent_at)

    def test_message_ends_sent(self):
        ctx = self._seed_happy_path()
        result = WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.message.status, "sent")

    def test_metadata_links_delivery_and_message(self):
        ctx = self._seed_happy_path()
        result = WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.delivery.metadata_json.get("crm_whatsapp_message_id"), result.message.id)
        self.assertEqual(result.message.metadata_json.get("notification_delivery_id"), ctx["delivery"].id)

    def test_links_lead_and_contact_when_present(self):
        ctx = self._seed_happy_path(with_lead=True)
        result = WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.message.lead_id, ctx["lead_id"])
        self.assertEqual(result.message.contact_id, ctx["contact_id"])

    def test_works_without_lead(self):
        ctx = self._seed_happy_path(with_lead=False)
        result = WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "sent")
        self.assertIsNone(result.message.lead_id)

    def test_meta_error_leaves_both_failed(self):
        ctx = self._seed_happy_path()
        client = _FakeWhatsAppClient(fail=True, error_message="Simulated Meta failure")
        result = WhatsAppNotificationExecutor(self.db, client=client).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.delivery.status, "failed")
        self.assertEqual(result.message.status, "failed")

    def test_error_is_sanitized(self):
        ctx = self._seed_happy_path()
        client = _FakeWhatsAppClient(
            fail=True, error_message="Bearer abcdefghijklmnopqrstuvwx0123456789 rejected"
        )
        result = WhatsAppNotificationExecutor(self.db, client=client).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertNotIn("abcdefghijklmnopqrstuvwx0123456789", result.delivery.error_message)

    def test_error_does_not_contain_phone(self):
        ctx = self._seed_happy_path()
        client = _FakeWhatsAppClient(fail=True, error_message="Failed for +573001112233")
        result = WhatsAppNotificationExecutor(self.db, client=client).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        self.assertNotIn("573001112233", result.delivery.error_message)

    def test_missing_variable_leaves_delivery_failed(self):
        ctx = self._seed_happy_path()
        ctx["event"].payload_json = {**ctx["event"].payload_json, "custom": {}}
        self.db.add(ctx["event"])
        self.db.commit()
        client = _FakeWhatsAppClient()
        with self.assertRaises(WhatsAppNotificationExecutionError) as cm:
            WhatsAppNotificationExecutor(self.db, client=client).execute(
                tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
            )
        self.assertEqual(cm.exception.code, "required_field_missing")
        self.assertEqual(client.send_calls, 0)
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "failed")

    def test_invalid_template_leaves_delivery_failed(self):
        ctx = self._seed_happy_path()
        ctx["template"].status = "inactive"
        self.db.add(ctx["template"])
        self.db.commit()
        with self.assertRaises(WhatsAppNotificationExecutionError) as cm:
            WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
                tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
            )
        self.assertEqual(cm.exception.code, "template_configuration_invalid")
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "failed")

    def test_session_usable_after_failure(self):
        ctx = self._seed_happy_path()
        ctx["template"].status = "inactive"
        self.db.add(ctx["template"])
        self.db.commit()
        with self.assertRaises(WhatsAppNotificationExecutionError):
            WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
                tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
            )
        other_tenant_id = self._create_tenant("post-failure-tenant")
        self.assertIsNotNone(other_tenant_id)

    def test_reexecuting_failed_delivery_increments_attempts(self):
        ctx = self._seed_happy_path()
        ctx["template"].status = "inactive"
        self.db.add(ctx["template"])
        self.db.commit()
        executor = WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient())
        with self.assertRaises(WhatsAppNotificationExecutionError):
            executor.execute(tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW)
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].attempts, 1)
        self.assertEqual(ctx["delivery"].status, "failed")

        ctx["template"].status = "active"
        self.db.add(ctx["template"])
        self.db.commit()
        result = executor.execute(tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW)
        self.assertEqual(result.outcome, "sent")
        self.assertEqual(result.delivery.attempts, 2)

    def test_does_not_create_new_delivery(self):
        ctx = self._seed_happy_path()
        WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW
        )
        count = self.db.query(NotificationDelivery).filter(NotificationDelivery.tenant_id == ctx["tenant_id"]).count()
        self.assertEqual(count, 1)

    def test_only_uses_injected_client(self):
        ctx = self._seed_happy_path()
        client = _FakeWhatsAppClient()
        executor = WhatsAppNotificationExecutor(self.db, client=client)
        self.assertIs(executor._message_service.client, client)
        executor.execute(tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, now=FIXED_NOW)
        self.assertEqual(client.send_calls, 1)


# ---------------------------------------------------------------------------
# Webhook y sincronizacion de entregas — 50 a 60
# ---------------------------------------------------------------------------
class WhatsAppWebhookDeliverySyncTests(_BaseExecutorTestCase):
    def _seed_webhook_pair(
        self,
        *,
        phone_number_id: str = "phone-1",
        provider_message_id: str = "wamid.status-1",
        message_status: str = "sent",
        delivery_status: str = "sent",
        with_lead: bool = True,
        link_delivery: bool = True,
    ) -> dict:
        ctx = self._seed_happy_path(status=delivery_status, with_lead=with_lead, phone_number_id=phone_number_id)
        if link_delivery:
            ctx["delivery"].provider_message_id = provider_message_id
            ctx["delivery"].sent_at = FIXED_NOW
            self.db.add(ctx["delivery"])
            self.db.commit()
            self.db.refresh(ctx["delivery"])
        message = CrmWhatsAppMessage(
            tenant_id=ctx["tenant_id"],
            lead_id=ctx["lead_id"],
            contact_id=ctx["contact_id"],
            provider_message_id=provider_message_id,
            direction="outbound",
            to_phone="+573001112233",
            status=message_status,
            metadata_json={},
            sent_at=FIXED_NOW,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        ctx["message"] = message
        ctx["phone_number_id"] = phone_number_id
        ctx["provider_message_id"] = provider_message_id
        return ctx

    @staticmethod
    def _webhook_payload(*, phone_number_id: str, provider_message_id: str, status: str, errors=None) -> dict:
        status_item = {"id": provider_message_id, "status": status}
        if errors is not None:
            status_item["errors"] = errors
        return {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": phone_number_id},
                                "statuses": [status_item],
                            }
                        }
                    ]
                }
            ]
        }

    def test_webhook_sent_updates_delivery(self):
        ctx = self._seed_webhook_pair(delivery_status="pending")
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="sent",
            )
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "sent")
        self.assertIsNotNone(ctx["delivery"].sent_at)

    def test_webhook_delivered_updates_delivery(self):
        ctx = self._seed_webhook_pair(delivery_status="sent")
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="delivered",
            )
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "delivered")
        self.assertIsNotNone(ctx["delivery"].delivered_at)

    def test_webhook_read_updates_delivery(self):
        ctx = self._seed_webhook_pair(delivery_status="delivered")
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="read",
            )
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "read")
        self.assertIsNotNone(ctx["delivery"].read_at)

    def test_webhook_failed_updates_delivery(self):
        # "pending" is not a protected status, so a failed webhook may still
        # apply here (unlike "sent", which must never be degraded — see
        # test_webhook_sent_is_never_degraded_by_failed below).
        ctx = self._seed_webhook_pair(delivery_status="pending")
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="failed",
                errors=[{"message": "Bearer abcdefghijklmnopqrstuvwx0123456789 for +573001112233 failed"}],
            )
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "failed")
        self.assertIsNotNone(ctx["delivery"].failed_at)
        self.assertIsNotNone(ctx["delivery"].error_message)
        self.assertNotIn("abcdefghijklmnopqrstuvwx0123456789", ctx["delivery"].error_message)
        self.assertNotIn("573001112233", ctx["delivery"].error_message)

    def test_webhook_sent_is_never_degraded_by_failed(self):
        ctx = self._seed_webhook_pair(delivery_status="sent")
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="failed",
            )
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "sent")

    def test_webhook_delivered_is_never_degraded_by_failed(self):
        ctx = self._seed_webhook_pair(delivery_status="delivered")
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="failed",
            )
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "delivered")

    def test_webhook_read_is_never_degraded_by_failed(self):
        ctx = self._seed_webhook_pair(delivery_status="read")
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="failed",
            )
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "read")

    def test_webhook_cancelled_is_never_degraded_by_failed(self):
        ctx = self._seed_webhook_pair(delivery_status="cancelled")
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="failed",
            )
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "cancelled")

    def test_webhook_manual_review_promotes_to_sent(self):
        ctx = self._seed_webhook_pair(delivery_status="manual_review")
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="sent",
            )
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "sent")

    def test_webhook_manual_review_promotes_to_delivered(self):
        ctx = self._seed_webhook_pair(delivery_status="manual_review")
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="delivered",
            )
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "delivered")

    def test_webhook_read_not_degraded_by_later_delivered(self):
        ctx = self._seed_webhook_pair(delivery_status="read")
        ctx["delivery"].read_at = FIXED_NOW
        ctx["delivery"].delivered_at = FIXED_NOW
        self.db.add(ctx["delivery"])
        self.db.commit()
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="delivered",
            )
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "read")

    def test_webhook_other_tenant_not_updated(self):
        ctx_a = self._seed_webhook_pair(phone_number_id="phone-a", provider_message_id="wamid.shared", delivery_status="sent")
        ctx_b = self._seed_webhook_pair(phone_number_id="phone-b", provider_message_id="wamid.shared", delivery_status="sent")
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(phone_number_id="phone-a", provider_message_id="wamid.shared", status="delivered")
        )
        self.db.refresh(ctx_a["delivery"])
        self.db.refresh(ctx_b["delivery"])
        self.assertEqual(ctx_a["delivery"].status, "delivered")
        self.assertEqual(ctx_b["delivery"].status, "sent")

    def test_webhook_message_without_delivery_still_works(self):
        ctx = self._seed_webhook_pair(delivery_status="pending", link_delivery=False)
        response = WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="delivered",
            )
        )
        self.assertEqual(response["statuses"], 1)
        self.db.refresh(ctx["message"])
        self.assertEqual(ctx["message"].status, "delivered")
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "pending")

    def test_webhook_does_not_store_full_payload(self):
        ctx = self._seed_webhook_pair(delivery_status="sent")
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="delivered",
            )
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].metadata_json, {})
        self.db.refresh(ctx["message"])
        self.assertNotIn("entry", str(ctx["message"].metadata_json))

    def test_webhook_preserves_crm_whatsapp_message_update(self):
        ctx = self._seed_webhook_pair(delivery_status="sent")
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="read",
            )
        )
        self.db.refresh(ctx["message"])
        self.assertEqual(ctx["message"].status, "read")
        self.assertIsNotNone(ctx["message"].read_at)

    def test_webhook_preserves_integration_events_and_activities(self):
        ctx = self._seed_webhook_pair(delivery_status="sent", with_lead=True)
        WhatsAppMessageService(self.db).handle_webhook_payload(
            self._webhook_payload(
                phone_number_id=ctx["phone_number_id"],
                provider_message_id=ctx["provider_message_id"],
                status="delivered",
            )
        )
        event = (
            self.db.query(TenantIntegrationEvent)
            .filter(TenantIntegrationEvent.event_type == "whatsapp_status_delivered")
            .first()
        )
        self.assertIsNotNone(event)
        activity = (
            self.db.query(CrmActivity).filter(CrmActivity.activity_type == "whatsapp_status_delivered").first()
        )
        self.assertIsNotNone(activity)


# ---------------------------------------------------------------------------
# execute_claimed — token ownership, FK linkage, cancellation (Phase 6)
# ---------------------------------------------------------------------------
class WhatsAppExecuteClaimedTests(_BaseExecutorTestCase):
    def _claim(self, tenant_id, delivery_id, *, now=FIXED_NOW, lease_seconds=120, max_attempts=5):
        return NotificationDeliveryClaimService(self.db).claim_one(
            tenant_id=tenant_id, delivery_id=delivery_id, now=now, lease_seconds=lease_seconds, max_attempts=max_attempts
        )

    def _create_event_with_resource(self, tenant_id, *, event_type, resource_id, created_at):
        payload = _make_payload()
        result = DomainEventService(self.db).publish(
            tenant_id=tenant_id,
            event_type=event_type,
            source="calcom",
            idempotency_key=f"evt-{uuid4().hex[:8]}",
            payload=payload,
            resource_type="crm_booking",
            resource_id=resource_id,
            available_at=PAST_SCHEDULE,
        )
        event = result.event
        event.created_at = created_at
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def test_execute_claimed_accepts_correct_token(self):
        ctx = self._seed_happy_path()
        claim = self._claim(ctx["tenant_id"], ctx["delivery"].id)
        result = WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute_claimed(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, claim_token=claim.claim_token, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "sent")

    def test_execute_claimed_rejects_wrong_token(self):
        ctx = self._seed_happy_path()
        self._claim(ctx["tenant_id"], ctx["delivery"].id)
        with self.assertRaises(WhatsAppNotificationExecutionError) as cm:
            WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute_claimed(
                tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, claim_token="wrong-token", now=FIXED_NOW
            )
        self.assertEqual(cm.exception.code, "delivery_claim_mismatch")

    def test_execute_claimed_rejects_wrong_token_without_disturbing_real_claim(self):
        ctx = self._seed_happy_path()
        claim = self._claim(ctx["tenant_id"], ctx["delivery"].id)
        with self.assertRaises(WhatsAppNotificationExecutionError):
            WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute_claimed(
                tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, claim_token="wrong-token", now=FIXED_NOW
            )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "processing")
        self.assertEqual(ctx["delivery"].claim_token, claim.claim_token)

    def test_execute_claimed_rejects_empty_token(self):
        ctx = self._seed_happy_path()
        self._claim(ctx["tenant_id"], ctx["delivery"].id)
        with self.assertRaises(WhatsAppNotificationExecutionError) as cm:
            WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute_claimed(
                tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, claim_token="", now=FIXED_NOW
            )
        self.assertEqual(cm.exception.code, "delivery_claim_mismatch")

    def test_execute_claimed_rejects_wrong_tenant(self):
        ctx = self._seed_happy_path()
        claim = self._claim(ctx["tenant_id"], ctx["delivery"].id)
        other_tenant_id = self._create_tenant("wrong-tenant")
        with self.assertRaises(WhatsAppNotificationExecutionError) as cm:
            WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute_claimed(
                tenant_id=other_tenant_id, delivery_id=ctx["delivery"].id, claim_token=claim.claim_token, now=FIXED_NOW
            )
        self.assertEqual(cm.exception.code, "delivery_not_found")

    def test_execute_claimed_does_not_increment_attempts(self):
        ctx = self._seed_happy_path()
        claim = self._claim(ctx["tenant_id"], ctx["delivery"].id)
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].attempts, 1)
        WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute_claimed(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, claim_token=claim.claim_token, now=FIXED_NOW
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].attempts, 1)

    def test_message_stores_notification_delivery_fk(self):
        ctx = self._seed_happy_path()
        claim = self._claim(ctx["tenant_id"], ctx["delivery"].id)
        result = WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute_claimed(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, claim_token=claim.claim_token, now=FIXED_NOW
        )
        self.assertEqual(result.message.notification_delivery_id, ctx["delivery"].id)

    def test_send_template_notification_rejects_delivery_from_other_tenant(self):
        ctx_a = self._seed_happy_path()
        ctx_b = self._seed_happy_path()
        service = WhatsAppMessageService(self.db, client=_FakeWhatsAppClient())
        with self.assertRaises(ValueError):
            service.send_template_notification(
                tenant_id=ctx_a["tenant_id"],
                to_phone="+573001112233",
                template_key=ctx_a["template"].template_key,
                variables={"1": "x", "2": "y"},
                metadata={},
                notification_delivery_id=ctx_b["delivery"].id,
            )

    def test_cancel_requested_delivery_is_cancelled_not_sent(self):
        ctx = self._seed_happy_path()
        claim = self._claim(ctx["tenant_id"], ctx["delivery"].id)
        delivery = ctx["delivery"]
        self.db.refresh(delivery)
        delivery.metadata_json = {"cancel_requested": True, "cancel_reason": "booking_cancelled"}
        self.db.add(delivery)
        self.db.commit()
        client = _FakeWhatsAppClient()
        result = WhatsAppNotificationExecutor(self.db, client=client).execute_claimed(
            tenant_id=ctx["tenant_id"], delivery_id=delivery.id, claim_token=claim.claim_token, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "cancelled")
        self.assertEqual(client.send_calls, 0)
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "cancelled")
        self.assertIsNone(delivery.claim_token)

    def test_superseded_event_delivery_is_cancelled(self):
        tenant_id = self._create_tenant("superseded-tenant")
        self._configure_whatsapp(tenant_id)
        template = self._create_synced_template(tenant_id)
        rule = self._create_rule(tenant_id, template_key=template.template_key)
        booking_id = "bk-superseded"
        created_event = self._create_event_with_resource(
            tenant_id, event_type="booking.created", resource_id=booking_id, created_at=PAST_SCHEDULE
        )
        delivery = self._create_delivery(tenant_id, created_event, rule, scheduled_for=PAST_SCHEDULE)
        self._create_event_with_resource(
            tenant_id,
            event_type="booking.cancelled",
            resource_id=booking_id,
            created_at=PAST_SCHEDULE + timedelta(seconds=10),
        )
        claim = self._claim(tenant_id, delivery.id)
        client = _FakeWhatsAppClient()
        result = WhatsAppNotificationExecutor(self.db, client=client).execute_claimed(
            tenant_id=tenant_id, delivery_id=delivery.id, claim_token=claim.claim_token, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "cancelled")
        self.assertEqual(client.send_calls, 0)

    def test_latest_event_delivery_is_not_treated_as_superseded(self):
        tenant_id = self._create_tenant("latest-tenant")
        self._configure_whatsapp(tenant_id)
        template = self._create_synced_template(tenant_id)
        rule = self._create_rule(tenant_id, template_key=template.template_key)
        booking_id = "bk-latest"
        self._create_event_with_resource(
            tenant_id, event_type="booking.created", resource_id=booking_id, created_at=PAST_SCHEDULE
        )
        rescheduled_event = self._create_event_with_resource(
            tenant_id,
            event_type="booking.rescheduled",
            resource_id=booking_id,
            created_at=PAST_SCHEDULE + timedelta(seconds=10),
        )
        delivery = self._create_delivery(tenant_id, rescheduled_event, rule, scheduled_for=PAST_SCHEDULE)
        claim = self._claim(tenant_id, delivery.id)
        client = _FakeWhatsAppClient()
        result = WhatsAppNotificationExecutor(self.db, client=client).execute_claimed(
            tenant_id=tenant_id, delivery_id=delivery.id, claim_token=claim.claim_token, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "sent")
        self.assertEqual(client.send_calls, 1)

    def test_normal_call_delivery_is_not_considered_superseded(self):
        # Deliveries with no crm_booking resource (e.g. call events) never go
        # through the superseding check.
        ctx = self._seed_happy_path()
        claim = self._claim(ctx["tenant_id"], ctx["delivery"].id)
        result = WhatsAppNotificationExecutor(self.db, client=_FakeWhatsAppClient()).execute_claimed(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, claim_token=claim.claim_token, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "sent")

    # -----------------------------------------------------------------
    # Post-Meta finalization when the claim is stolen mid-flight (Fix 3)
    # -----------------------------------------------------------------
    def _steal_claim_after_send(self, executor, ctx, *, new_status="processing", new_claim_token="tok-new-owner"):
        """Wrap the executor's send call so that, right after Meta answers,
        a different (newer) execution appears to own the delivery — as if
        its lease had expired and someone else reclaimed it while the HTTP
        call was in flight."""
        original_send = executor._message_service.send_template_notification

        def wrapped(*args, **kwargs):
            result = original_send(*args, **kwargs)
            delivery = (
                self.db.query(NotificationDelivery).filter(NotificationDelivery.id == ctx["delivery"].id).one()
            )
            delivery.status = new_status
            delivery.claim_token = new_claim_token
            self.db.add(delivery)
            self.db.commit()
            return result

        executor._message_service.send_template_notification = wrapped
        return executor

    def test_stale_owner_does_not_overwrite_sent_with_positive_evidence(self):
        ctx = self._seed_happy_path()
        claim = self._claim(ctx["tenant_id"], ctx["delivery"].id)
        client = _FakeWhatsAppClient()
        executor = self._steal_claim_after_send(
            WhatsAppNotificationExecutor(self.db, client=client), ctx
        )
        result = executor.execute_claimed(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, claim_token=claim.claim_token, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "stale_claim_reconciled")
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "sent")

    def test_stale_owner_does_not_overwrite_manual_review(self):
        ctx = self._seed_happy_path()
        claim = self._claim(ctx["tenant_id"], ctx["delivery"].id)
        client = _FakeWhatsAppClient()
        executor = self._steal_claim_after_send(
            WhatsAppNotificationExecutor(self.db, client=client), ctx, new_status="manual_review", new_claim_token=None
        )
        result = executor.execute_claimed(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, claim_token=claim.claim_token, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "stale_claim_ignored")
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "manual_review")

    def test_stale_owner_never_clears_the_new_claim_token(self):
        ctx = self._seed_happy_path()
        claim = self._claim(ctx["tenant_id"], ctx["delivery"].id)
        client = _FakeWhatsAppClient()
        executor = self._steal_claim_after_send(
            WhatsAppNotificationExecutor(self.db, client=client), ctx, new_claim_token="tok-brand-new"
        )
        executor.execute_claimed(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, claim_token=claim.claim_token, now=FIXED_NOW
        )
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].claim_token, "tok-brand-new")

    def test_stale_reconciliation_never_calls_meta_again(self):
        ctx = self._seed_happy_path()
        claim = self._claim(ctx["tenant_id"], ctx["delivery"].id)
        client = _FakeWhatsAppClient()
        executor = self._steal_claim_after_send(
            WhatsAppNotificationExecutor(self.db, client=client), ctx
        )
        executor.execute_claimed(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, claim_token=claim.claim_token, now=FIXED_NOW
        )
        self.assertEqual(client.send_calls, 1)

    def test_stale_reconciliation_preserves_delivered_evidence(self):
        ctx = self._seed_happy_path()
        claim = self._claim(ctx["tenant_id"], ctx["delivery"].id)
        client = _FakeWhatsAppClient()
        executor = WhatsAppNotificationExecutor(self.db, client=client)
        real_send = executor._message_service.send_template_notification

        def wrapped(*args, **kwargs):
            result = real_send(*args, **kwargs)
            delivery = (
                self.db.query(NotificationDelivery).filter(NotificationDelivery.id == ctx["delivery"].id).one()
            )
            delivery.status = "processing"
            delivery.claim_token = "tok-new-owner"
            self.db.add(delivery)
            result.message.status = "delivered"
            result.message.delivered_at = FIXED_NOW
            self.db.add(result.message)
            self.db.commit()
            return result

        executor._message_service.send_template_notification = wrapped
        result = executor.execute_claimed(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, claim_token=claim.claim_token, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "stale_claim_reconciled")
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "delivered")

    def test_stale_reconciliation_preserves_read_evidence(self):
        ctx = self._seed_happy_path()
        claim = self._claim(ctx["tenant_id"], ctx["delivery"].id)
        client = _FakeWhatsAppClient()
        executor = WhatsAppNotificationExecutor(self.db, client=client)
        real_send = executor._message_service.send_template_notification

        def wrapped(*args, **kwargs):
            result = real_send(*args, **kwargs)
            delivery = (
                self.db.query(NotificationDelivery).filter(NotificationDelivery.id == ctx["delivery"].id).one()
            )
            delivery.status = "processing"
            delivery.claim_token = "tok-new-owner"
            self.db.add(delivery)
            result.message.status = "read"
            result.message.delivered_at = FIXED_NOW
            result.message.read_at = FIXED_NOW
            self.db.add(result.message)
            self.db.commit()
            return result

        executor._message_service.send_template_notification = wrapped
        result = executor.execute_claimed(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, claim_token=claim.claim_token, now=FIXED_NOW
        )
        self.assertEqual(result.outcome, "stale_claim_reconciled")
        self.db.refresh(ctx["delivery"])
        self.assertEqual(ctx["delivery"].status, "read")


# ---------------------------------------------------------------------------
# Meta responds without a usable provider message id (Fix 5)
# ---------------------------------------------------------------------------
class WhatsAppMissingProviderMessageIdTests(_BaseExecutorTestCase):
    class _NoIdClient(WhatsAppCloudClient):
        def __init__(self, payload):
            super().__init__()
            self._payload = payload
            self.send_calls = 0

        def send_template_message(self, *args, **kwargs):
            self.send_calls += 1
            return self._payload

    def _claim(self, tenant_id, delivery_id, *, now=FIXED_NOW, lease_seconds=120, max_attempts=5):
        return NotificationDeliveryClaimService(self.db).claim_one(
            tenant_id=tenant_id, delivery_id=delivery_id, now=now, lease_seconds=lease_seconds, max_attempts=max_attempts
        )

    def _run(self, payload):
        ctx = self._seed_happy_path()
        claim = self._claim(ctx["tenant_id"], ctx["delivery"].id)
        client = self._NoIdClient(payload)
        result = WhatsAppNotificationExecutor(self.db, client=client).execute_claimed(
            tenant_id=ctx["tenant_id"], delivery_id=ctx["delivery"].id, claim_token=claim.claim_token, now=FIXED_NOW
        )
        return ctx, client, result

    def test_empty_payload_is_manual_review(self):
        _, _, result = self._run({})
        self.assertEqual(result.outcome, "manual_review")

    def test_empty_messages_list_is_manual_review(self):
        _, _, result = self._run({"messages": []})
        self.assertEqual(result.outcome, "manual_review")

    def test_message_without_id_key_is_manual_review(self):
        _, _, result = self._run({"messages": [{}]})
        self.assertEqual(result.outcome, "manual_review")

    def test_empty_id_string_is_manual_review(self):
        _, _, result = self._run({"messages": [{"id": ""}]})
        self.assertEqual(result.outcome, "manual_review")

    def test_manual_review_error_code_and_retryable_flag(self):
        _, _, result = self._run({})
        self.assertEqual(result.error_code, "whatsapp_provider_message_id_missing")
        self.assertFalse(result.retryable)

    def test_manual_review_leaves_no_next_attempt(self):
        ctx, _, result = self._run({})
        self.db.refresh(ctx["delivery"])
        self.assertIsNone(ctx["delivery"].next_attempt_at)

    def test_manual_review_clears_the_claim(self):
        ctx, _, result = self._run({})
        self.db.refresh(ctx["delivery"])
        self.assertIsNone(ctx["delivery"].claim_token)
        self.assertIsNone(ctx["delivery"].claimed_at)
        self.assertIsNone(ctx["delivery"].claim_expires_at)

    def test_notification_delivery_id_is_preserved(self):
        ctx, _, result = self._run({})
        self.assertEqual(result.delivery.id, ctx["delivery"].id)
        self.assertEqual(result.message.notification_delivery_id, ctx["delivery"].id)

    def test_message_stays_queued_not_sent(self):
        _, _, result = self._run({})
        self.assertEqual(result.message.status, "queued")

    def test_no_second_send_attempt_is_made(self):
        _, client, _ = self._run({})
        self.assertEqual(client.send_calls, 1)


if __name__ == "__main__":
    unittest.main()
