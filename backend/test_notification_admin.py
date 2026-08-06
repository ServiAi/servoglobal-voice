from __future__ import annotations

import os
from pathlib import Path
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_notification_admin_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.identity import Tenant, TenantMembership, User
from app.models.integrations import TenantWhatsAppTemplate
from app.models.notifications import DomainEvent, NotificationDelivery, TenantNotificationRule

_BASE = "/api/v1/admin/notifications"

_APPROVED_VARIABLES_JSON = {
    "source": "meta_sync",
    "meta_status": "APPROVED",
    "parameters": [{"key": "1", "label": "Variable 1"}],
}

_VALID_RULE_PAYLOAD = {
    "name": "Confirmacion de reserva",
    "capability_key": "booking_notifications",
    "event_type": "booking.created",
    "template_key": "booking_confirmation",
    "recipient_strategy": "event_customer",
    "conditions_json": [],
    "variable_mapping_json": {"1": {"source": "literal", "value": "Reserva confirmada"}},
    "schedule_mode": "immediate",
    "schedule_offset_minutes": 0,
    "priority": 100,
    "enabled": True,
}


class NotificationAdminTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        app.dependency_overrides.clear()
        self.client = TestClient(app)

        with SessionLocal() as db:
            self.tenant = Tenant(name="Tenant A", slug="tenant-a")
            self.other_tenant = Tenant(name="Tenant B", slug="tenant-b")
            db.add_all([self.tenant, self.other_tenant])
            db.commit()
            db.refresh(self.tenant)
            db.refresh(self.other_tenant)
            self.tenant_id = self.tenant.id
            self.other_tenant_id = self.other_tenant.id

            self.user_ids: dict[str, str] = {}
            for role in ("platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"):
                user = User(email=f"{role}@example.com", name=role, status="active")
                db.add(user)
                db.commit()
                db.refresh(user)
                db.add(TenantMembership(tenant_id=self.tenant_id, user_id=user.id, role=role, status="active"))
                db.commit()
                self.user_ids[role] = user.id

            other_admin = User(email="other-tenant-admin@example.com", name="Other tenant admin", status="active")
            db.add(other_admin)
            db.commit()
            db.refresh(other_admin)
            db.add(TenantMembership(tenant_id=self.other_tenant_id, user_id=other_admin.id, role="tenant_admin", status="active"))
            db.commit()
            self.other_admin_user_id = other_admin.id

            db.add(
                TenantWhatsAppTemplate(
                    tenant_id=self.tenant_id,
                    template_key="booking_confirmation",
                    provider_template_name="booking_confirmation",
                    name="Confirmacion de reserva",
                    category="transactional",
                    language="es",
                    body="Tu reserva ha sido confirmada: {{1}}",
                    variables_json=dict(_APPROVED_VARIABLES_JSON),
                    status="active",
                )
            )
            db.commit()

        self._active_tenant_id = self.tenant_id
        self._active_user_id = self.user_ids["tenant_admin"]
        app.dependency_overrides[get_current_auth_context] = self._auth_context_override

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    async def _auth_context_override(self):
        with SessionLocal() as db:
            tenant = db.get(Tenant, self._active_tenant_id)
            user = db.get(User, self._active_user_id)
            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == self._active_tenant_id,
                    TenantMembership.user_id == self._active_user_id,
                )
            )
            return AuthContext(user=user, tenant=tenant, membership=membership)

    def _as(self, role: str) -> None:
        self._active_tenant_id = self.tenant_id
        self._active_user_id = self.user_ids[role]

    def _as_other_tenant_admin(self) -> None:
        self._active_tenant_id = self.other_tenant_id
        self._active_user_id = self.other_admin_user_id

    def _create_rule(self, **overrides) -> dict:
        payload = {**_VALID_RULE_PAYLOAD, **overrides}
        self._as("tenant_admin")
        response = self.client.post(f"{_BASE}/rules", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _create_recipient(self, **overrides) -> dict:
        payload = {
            "group_key": "sales_team",
            "name": "Equipo comercial",
            "channel": "whatsapp",
            "destination": "+573001112233",
            "status": "active",
            **overrides,
        }
        self._as("tenant_admin")
        response = self.client.post(f"{_BASE}/recipients", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _seed_template(self, *, tenant_id: str, template_key: str, **overrides) -> None:
        with SessionLocal() as db:
            payload = {
                "tenant_id": tenant_id,
                "template_key": template_key,
                "provider_template_name": template_key,
                "name": template_key,
                "category": "transactional",
                "language": "es",
                "body": "Tu reserva ha sido confirmada: {{1}}",
                "variables_json": dict(_APPROVED_VARIABLES_JSON),
                "status": "active",
                **overrides,
            }
            existing = db.scalar(
                select(TenantWhatsAppTemplate).where(
                    TenantWhatsAppTemplate.tenant_id == tenant_id,
                    TenantWhatsAppTemplate.template_key == template_key,
                )
            )
            if existing is not None:
                for key, value in payload.items():
                    if key in ("tenant_id", "template_key"):
                        continue
                    setattr(existing, key, value)
            else:
                db.add(TenantWhatsAppTemplate(**payload))
            db.commit()

    def _seed_delivery(self, *, tenant_id: str, rule_id: str, event_type: str = "booking.created", status: str = "pending", recipient: str = "573001112233", **overrides) -> str:
        with SessionLocal() as db:
            event = DomainEvent(
                tenant_id=tenant_id,
                event_type=event_type,
                source="test",
                idempotency_key=f"idem-{os.urandom(4).hex()}",
                payload_json={"booking": {"id": "b1"}},
                status="processed",
            )
            db.add(event)
            db.commit()
            db.refresh(event)

            delivery = NotificationDelivery(
                tenant_id=tenant_id,
                domain_event_id=event.id,
                notification_rule_id=rule_id,
                channel="whatsapp",
                recipient=recipient,
                template_key="booking_confirmation",
                status=status,
                scheduled_for=overrides.pop("scheduled_for", datetime.now(timezone.utc)),
                idempotency_key=f"delivery-{os.urandom(4).hex()}",
                **overrides,
            )
            db.add(delivery)
            db.commit()
            db.refresh(delivery)
            return delivery.id

    # ---------------------------------------------------------------- auth (7)
    def test_platform_admin_can_read(self):
        self._as("platform_admin")
        response = self.client.get(f"{_BASE}/overview")
        self.assertEqual(response.status_code, 200)

    def test_tenant_admin_can_read_and_write(self):
        self._as("tenant_admin")
        self.assertEqual(self.client.get(f"{_BASE}/rules").status_code, 200)
        self._create_rule()

    def test_tenant_analyst_can_read(self):
        self._as("tenant_analyst")
        response = self.client.get(f"{_BASE}/rules")
        self.assertEqual(response.status_code, 200)

    def test_tenant_analyst_cannot_write(self):
        self._as("tenant_analyst")
        response = self.client.post(f"{_BASE}/rules", json=_VALID_RULE_PAYLOAD)
        self.assertEqual(response.status_code, 403)

    def test_tenant_viewer_can_read(self):
        self._as("tenant_viewer")
        response = self.client.get(f"{_BASE}/rules")
        self.assertEqual(response.status_code, 200)

    def test_tenant_viewer_cannot_write(self):
        self._as("tenant_viewer")
        response = self.client.post(f"{_BASE}/rules", json=_VALID_RULE_PAYLOAD)
        self.assertEqual(response.status_code, 403)

    def test_no_token_returns_401(self):
        del app.dependency_overrides[get_current_auth_context]
        try:
            response = self.client.get(f"{_BASE}/overview")
            self.assertEqual(response.status_code, 401)
        finally:
            app.dependency_overrides[get_current_auth_context] = self._auth_context_override

    # ---------------------------------------------------------- multi-tenant (6)
    def test_tenant_does_not_list_rules_of_other_tenant(self):
        rule = self._create_rule()
        self._as_other_tenant_admin()
        response = self.client.get(f"{_BASE}/rules")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(rule["id"], [item["id"] for item in response.json()])

    def test_tenant_cannot_modify_rules_of_other_tenant_returns_404(self):
        rule = self._create_rule()
        self._as_other_tenant_admin()
        response = self.client.patch(f"{_BASE}/rules/{rule['id']}", json={"priority": 5})
        self.assertEqual(response.status_code, 404)

    def test_tenant_does_not_list_recipients_of_other_tenant(self):
        recipient = self._create_recipient()
        self._as_other_tenant_admin()
        response = self.client.get(f"{_BASE}/recipients")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(recipient["id"], [item["id"] for item in response.json()])

    def test_tenant_cannot_modify_recipients_of_other_tenant_returns_404(self):
        recipient = self._create_recipient()
        self._as_other_tenant_admin()
        response = self.client.patch(f"{_BASE}/recipients/{recipient['id']}", json={"status": "inactive"})
        self.assertEqual(response.status_code, 404)

    def test_tenant_cannot_query_deliveries_of_other_tenant(self):
        rule = self._create_rule()
        delivery_id = self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule["id"])
        self._as_other_tenant_admin()
        response = self.client.get(f"{_BASE}/deliveries")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(delivery_id, [item["id"] for item in response.json()["items"]])

    def test_other_tenant_delivery_id_returns_404(self):
        rule = self._create_rule()
        delivery_id = self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule["id"])
        self._as_other_tenant_admin()
        response = self.client.get(f"{_BASE}/deliveries/{delivery_id}")
        self.assertEqual(response.status_code, 404)

    # ----------------------------------------------------------- capabilities (3)
    def test_capabilities_are_tenant_scoped_with_known_keys(self):
        self._as("tenant_admin")
        response = self.client.get(f"{_BASE}/capabilities")
        self.assertEqual(response.status_code, 200)
        keys = {item["capability_key"] for item in response.json()}
        self.assertEqual(keys, {"booking_notifications", "call_notifications"})
        self.assertTrue(all(item["enabled"] is False for item in response.json()))

    def test_capability_toggle_is_idempotent(self):
        self._as("tenant_admin")
        first = self.client.patch(f"{_BASE}/capabilities/booking_notifications", json={"enabled": True})
        second = self.client.patch(f"{_BASE}/capabilities/booking_notifications", json={"enabled": True})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        listing = self.client.get(f"{_BASE}/capabilities").json()
        booking_rows = [item for item in listing if item["capability_key"] == "booking_notifications"]
        self.assertEqual(len(booking_rows), 1)
        self.assertTrue(booking_rows[0]["enabled"])

    def test_capability_rejects_arbitrary_key(self):
        self._as("tenant_admin")
        response = self.client.patch(f"{_BASE}/capabilities/not_a_real_capability", json={"enabled": True})
        self.assertEqual(response.status_code, 422)

    # ------------------------------------------------------------------ rules (14)
    def test_create_valid_rule(self):
        rule = self._create_rule()
        self.assertEqual(rule["channel"], "whatsapp")
        self.assertEqual(rule["action_type"], "send_whatsapp_template")
        self.assertIsNone(rule["configuration_error"])

    def test_update_valid_rule(self):
        rule = self._create_rule()
        self._as("tenant_admin")
        response = self.client.patch(f"{_BASE}/rules/{rule['id']}", json={"priority": 5})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["priority"], 5)

    def test_enable_rule(self):
        rule = self._create_rule(enabled=False)
        self._as("tenant_admin")
        response = self.client.patch(f"{_BASE}/rules/{rule['id']}/enabled", json={"enabled": True})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["enabled"])

    def test_disable_rule(self):
        rule = self._create_rule()
        self._as("tenant_admin")
        response = self.client.patch(f"{_BASE}/rules/{rule['id']}/enabled", json={"enabled": False})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["enabled"])

    def test_create_rule_duplicate_name_returns_409(self):
        self._create_rule()
        self._as("tenant_admin")
        response = self.client.post(f"{_BASE}/rules", json=_VALID_RULE_PAYLOAD)
        self.assertEqual(response.status_code, 409)

    def test_create_rule_unsupported_capability_key_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(f"{_BASE}/rules", json={**_VALID_RULE_PAYLOAD, "capability_key": "not_real"})
        self.assertEqual(response.status_code, 422)

    def test_create_rule_unsupported_event_type_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(f"{_BASE}/rules", json={**_VALID_RULE_PAYLOAD, "event_type": "invoice.created"})
        self.assertEqual(response.status_code, 422)

    def test_create_rule_unsupported_recipient_strategy_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(f"{_BASE}/rules", json={**_VALID_RULE_PAYLOAD, "recipient_strategy": "magic"})
        self.assertEqual(response.status_code, 422)

    def test_create_rule_configured_group_requires_group_key_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={**_VALID_RULE_PAYLOAD, "recipient_strategy": "configured_group", "recipient_group_key": None},
        )
        self.assertEqual(response.status_code, 422)

    def test_create_rule_event_field_invalid_group_key_path_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={**_VALID_RULE_PAYLOAD, "recipient_strategy": "event_field", "recipient_group_key": "__class__"},
        )
        self.assertEqual(response.status_code, 422)

    def test_create_rule_invalid_condition_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={**_VALID_RULE_PAYLOAD, "conditions_json": [{"field": "booking.status", "operator": "equals"}]},
        )
        self.assertEqual(response.status_code, 422)

    def test_create_rule_invalid_variable_mapping_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={**_VALID_RULE_PAYLOAD, "variable_mapping_json": {"date": {"source": "event_field"}}},
        )
        self.assertEqual(response.status_code, 422)

    def test_create_rule_relative_schedule_on_non_booking_event_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={
                **_VALID_RULE_PAYLOAD,
                "capability_key": "call_notifications",
                "event_type": "call.completed",
                "schedule_mode": "relative_to_booking",
                "schedule_offset_minutes": -60,
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_delete_rule_without_deliveries_succeeds(self):
        rule = self._create_rule()
        self._as("tenant_admin")
        response = self.client.delete(f"{_BASE}/rules/{rule['id']}")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get(f"{_BASE}/rules").json(), [])

    def test_delete_rule_with_deliveries_returns_409(self):
        rule = self._create_rule()
        self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule["id"])
        self._as("tenant_admin")
        response = self.client.delete(f"{_BASE}/rules/{rule['id']}")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "rule_has_deliveries")

    def test_delete_nonexistent_rule_returns_404(self):
        self._as("tenant_admin")
        response = self.client.delete(f"{_BASE}/rules/does-not-exist")
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------ whatsapp templates (11)
    def test_create_rule_nonexistent_template_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={**_VALID_RULE_PAYLOAD, "template_key": "does_not_exist"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "whatsapp_template_not_approved")

    def test_create_rule_other_tenant_template_returns_422(self):
        self._seed_template(tenant_id=self.other_tenant_id, template_key="other_tenant_only")
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={**_VALID_RULE_PAYLOAD, "template_key": "other_tenant_only"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "whatsapp_template_not_approved")

    def test_create_rule_unapproved_template_returns_422(self):
        self._seed_template(
            tenant_id=self.tenant_id,
            template_key="draft_template",
            variables_json={"source": "meta_sync", "meta_status": "DRAFT", "parameters": [{"key": "1", "label": "Variable 1"}]},
        )
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={**_VALID_RULE_PAYLOAD, "template_key": "draft_template"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "whatsapp_template_not_approved")

    def test_create_rule_with_approved_meta_template_succeeds(self):
        rule = self._create_rule()
        self.assertIsNone(rule["configuration_error"])
        self.assertEqual(rule["template_key"], "booking_confirmation")

    def test_create_rule_missing_required_template_variable_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={**_VALID_RULE_PAYLOAD, "variable_mapping_json": {}},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "template_variable_mapping_missing")

    def test_create_rule_accepts_all_required_template_variables(self):
        self._seed_template(
            tenant_id=self.tenant_id,
            template_key="two_param_template",
            variables_json={
                "source": "meta_sync",
                "meta_status": "APPROVED",
                "parameters": [{"key": "1", "label": "Variable 1"}, {"key": "2", "label": "Variable 2"}],
            },
        )
        rule = self._create_rule(
            name="Regla con dos variables",
            template_key="two_param_template",
            variable_mapping_json={
                "1": {"source": "literal", "value": "Hola"},
                "2": {"source": "literal", "value": "Adios"},
            },
        )
        self.assertIsNone(rule["configuration_error"])

    def test_cannot_enable_rule_with_invalid_configuration(self):
        rule = self._create_rule(enabled=False)
        with SessionLocal() as db:
            db_rule = db.get(TenantNotificationRule, rule["id"])
            db_rule.recipient_strategy = "configured_group"
            db_rule.recipient_group_key = None
            db.commit()
        self._as("tenant_admin")
        response = self.client.patch(f"{_BASE}/rules/{rule['id']}/enabled", json={"enabled": True})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "recipient_group_key_required")
        listing = self.client.get(f"{_BASE}/rules").json()
        stored = next(item for item in listing if item["id"] == rule["id"])
        self.assertFalse(stored["enabled"])
        self.assertIsNotNone(stored["configuration_error"])

    def test_cannot_enable_rule_when_template_no_longer_approved(self):
        rule = self._create_rule(enabled=False)
        self._seed_template(tenant_id=self.tenant_id, template_key="booking_confirmation", status="draft")
        self._as("tenant_admin")
        response = self.client.patch(f"{_BASE}/rules/{rule['id']}/enabled", json={"enabled": True})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "whatsapp_template_not_approved")
        listing = self.client.get(f"{_BASE}/rules").json()
        stored = next(item for item in listing if item["id"] == rule["id"])
        self.assertFalse(stored["enabled"])

    def test_can_disable_rule_with_invalid_configuration(self):
        rule = self._create_rule()
        self._seed_template(tenant_id=self.tenant_id, template_key="booking_confirmation", status="draft")
        self._as("tenant_admin")
        response = self.client.patch(f"{_BASE}/rules/{rule['id']}/enabled", json={"enabled": False})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["enabled"])

    def test_capability_response_does_not_expose_config_json(self):
        self._as("tenant_admin")
        response = self.client.patch(f"{_BASE}/capabilities/booking_notifications", json={"enabled": True})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("config_json", response.text)
        listing = self.client.get(f"{_BASE}/capabilities")
        self.assertNotIn("config_json", listing.text)

    def test_recipient_response_does_not_expose_metadata_json(self):
        recipient = self._create_recipient()
        self.assertNotIn("metadata_json", recipient)
        self._as("tenant_admin")
        listing = self.client.get(f"{_BASE}/recipients")
        self.assertNotIn("metadata_json", listing.text)

    # ------------------------------------------------------ numeric conditions (3)
    def test_numeric_condition_with_string_value_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={
                **_VALID_RULE_PAYLOAD,
                "capability_key": "call_notifications",
                "event_type": "call.completed",
                "conditions_json": [{"field": "call.duration_seconds", "operator": "greater_than", "value": "60"}],
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "condition_numeric_value_required")

    def test_numeric_condition_with_number_value_is_valid(self):
        rule = self._create_rule(
            capability_key="call_notifications",
            event_type="call.completed",
            conditions_json=[{"field": "call.duration_seconds", "operator": "greater_than", "value": 60}],
        )
        self.assertIsNone(rule["configuration_error"])

    def test_numeric_condition_with_boolean_value_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={
                **_VALID_RULE_PAYLOAD,
                "capability_key": "call_notifications",
                "event_type": "call.completed",
                "conditions_json": [{"field": "call.duration_seconds", "operator": "greater_than", "value": True}],
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "condition_numeric_value_required")

    # ----------------------------------------------- effective meta parameters (9)
    def test_literal_required_without_value_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={**_VALID_RULE_PAYLOAD, "variable_mapping_json": {"1": {"source": "literal", "required": False}}},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "template_variable_mapping_missing")

    def test_literal_with_empty_string_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={
                **_VALID_RULE_PAYLOAD,
                "variable_mapping_json": {"1": {"source": "literal", "value": "", "required": False}},
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "template_variable_mapping_missing")

    def test_literal_with_zero_value_is_valid(self):
        rule = self._create_rule(variable_mapping_json={"1": {"source": "literal", "value": 0}})
        self.assertIsNone(rule["configuration_error"])

    def test_literal_with_false_value_is_valid(self):
        rule = self._create_rule(variable_mapping_json={"1": {"source": "literal", "value": False}})
        self.assertIsNone(rule["configuration_error"])

    def test_event_field_without_path_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={**_VALID_RULE_PAYLOAD, "variable_mapping_json": {"1": {"source": "event_field"}}},
        )
        self.assertEqual(response.status_code, 422)

    def test_event_field_optional_without_default_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={
                **_VALID_RULE_PAYLOAD,
                "variable_mapping_json": {
                    "1": {"source": "event_field", "path": "booking.status", "required": False}
                },
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "template_variable_mapping_missing")

    def test_event_field_required_with_path_is_valid(self):
        rule = self._create_rule(
            variable_mapping_json={"1": {"source": "event_field", "path": "booking.status", "required": True}}
        )
        self.assertIsNone(rule["configuration_error"])

    def test_event_field_optional_with_default_is_valid(self):
        rule = self._create_rule(
            variable_mapping_json={
                "1": {"source": "event_field", "path": "booking.status", "required": False, "default": "pendiente"}
            }
        )
        self.assertIsNone(rule["configuration_error"])

    def test_cannot_enable_rule_with_ineffective_meta_parameter(self):
        rule = self._create_rule(enabled=False)
        with SessionLocal() as db:
            db_rule = db.get(TenantNotificationRule, rule["id"])
            db_rule.variable_mapping_json = {"1": {"source": "literal", "value": ""}}
            db.commit()
        self._as("tenant_admin")
        response = self.client.patch(f"{_BASE}/rules/{rule['id']}/enabled", json={"enabled": True})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "template_variable_mapping_missing")
        listing = self.client.get(f"{_BASE}/rules").json()
        stored = next(item for item in listing if item["id"] == rule["id"])
        self.assertFalse(stored["enabled"])
        self.assertIsNotNone(stored["configuration_error"])

    # ------------------------------------------------------------- recipients (6)
    def test_create_recipient(self):
        recipient = self._create_recipient()
        self.assertEqual(recipient["destination_masked"], "***2233")
        self.assertNotIn("destination", recipient)

    def test_update_recipient(self):
        recipient = self._create_recipient()
        self._as("tenant_admin")
        response = self.client.patch(f"{_BASE}/recipients/{recipient['id']}", json={"name": "Equipo VIP"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Equipo VIP")

    def test_activate_recipient(self):
        recipient = self._create_recipient(status="inactive")
        self._as("tenant_admin")
        response = self.client.patch(f"{_BASE}/recipients/{recipient['id']}", json={"status": "active"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "active")

    def test_deactivate_recipient(self):
        recipient = self._create_recipient()
        self._as("tenant_admin")
        response = self.client.patch(f"{_BASE}/recipients/{recipient['id']}", json={"status": "inactive"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "inactive")

    def test_create_recipient_duplicate_returns_409(self):
        self._create_recipient()
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/recipients",
            json={"group_key": "sales_team", "name": "Otro", "channel": "whatsapp", "destination": "+573001112233", "status": "active"},
        )
        self.assertEqual(response.status_code, 409)

    def test_create_recipient_invalid_phone_returns_422(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/recipients",
            json={"group_key": "sales_team", "name": "Corto", "channel": "whatsapp", "destination": "123", "status": "active"},
        )
        self.assertEqual(response.status_code, 422)

    def test_recipients_endpoint_has_no_delete(self):
        recipient = self._create_recipient()
        self._as("tenant_admin")
        response = self.client.delete(f"{_BASE}/recipients/{recipient['id']}")
        self.assertEqual(response.status_code, 405)

    # -------------------------------------------------------------- deliveries (10)
    def test_deliveries_list_paginated(self):
        rule = self._create_rule()
        for _ in range(3):
            self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule["id"])
        self._as("tenant_admin")
        response = self.client.get(f"{_BASE}/deliveries", params={"page": 1, "page_size": 2})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["page_size"], 2)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["pages"], 2)
        self.assertEqual(len(payload["items"]), 2)

    def test_deliveries_filter_by_status(self):
        rule = self._create_rule()
        self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule["id"], status="pending")
        self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule["id"], status="failed")
        self._as("tenant_admin")
        response = self.client.get(f"{_BASE}/deliveries", params={"status_filter": "failed"})
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["status"], "failed")

    def test_deliveries_filter_by_event_type(self):
        rule = self._create_rule()
        self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule["id"], event_type="booking.created")
        self._as("tenant_admin")
        response = self.client.get(f"{_BASE}/deliveries", params={"event_type": "booking.cancelled"})
        self.assertEqual(response.json()["total"], 0)

    def test_deliveries_filter_by_rule(self):
        rule_a = self._create_rule(name="Regla A")
        rule_b = self._create_rule(name="Regla B")
        self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule_a["id"])
        self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule_b["id"])
        self._as("tenant_admin")
        response = self.client.get(f"{_BASE}/deliveries", params={"rule_id": rule_a["id"]})
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["rule_id"], rule_a["id"])

    def test_deliveries_filter_by_date_range(self):
        rule = self._create_rule()
        self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule["id"])
        self._as("tenant_admin")
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        response = self.client.get(f"{_BASE}/deliveries", params={"date_from": future})
        self.assertEqual(response.json()["total"], 0)

    def test_deliveries_stable_order(self):
        rule = self._create_rule()
        first_id = self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule["id"])
        second_id = self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule["id"])
        self._as("tenant_admin")
        response = self.client.get(f"{_BASE}/deliveries")
        ids = [item["id"] for item in response.json()["items"]]
        # created_at DESC, id DESC: the delivery seeded second was created at the
        # same or later timestamp, so it must be listed before the first one.
        self.assertEqual(ids, [second_id, first_id])

    def test_deliveries_mask_recipient(self):
        rule = self._create_rule()
        self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule["id"], recipient="573001112233")
        self._as("tenant_admin")
        response = self.client.get(f"{_BASE}/deliveries")
        item = response.json()["items"][0]
        self.assertEqual(item["recipient_masked"], "***2233")
        self.assertNotIn("recipient", item)

    def test_deliveries_do_not_expose_claim_token(self):
        rule = self._create_rule()
        delivery_id = self._seed_delivery(
            tenant_id=self.tenant_id, rule_id=rule["id"], claim_token="secret-token", claimed_at=datetime.now(timezone.utc)
        )
        self._as("tenant_admin")
        response = self.client.get(f"{_BASE}/deliveries/{delivery_id}")
        body = response.text
        self.assertNotIn("claim_token", body)
        self.assertNotIn("secret-token", body)

    def test_deliveries_do_not_expose_payload_json(self):
        rule = self._create_rule()
        delivery_id = self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule["id"])
        self._as("tenant_admin")
        response = self.client.get(f"{_BASE}/deliveries/{delivery_id}")
        self.assertNotIn("payload_json", response.text)

    def test_deliveries_do_not_expose_secret_fields(self):
        rule = self._create_rule()
        delivery_id = self._seed_delivery(tenant_id=self.tenant_id, rule_id=rule["id"])
        self._as("tenant_admin")
        response = self.client.get(f"{_BASE}/deliveries/{delivery_id}")
        for forbidden in ("access_token", "webhook_secret", "api_key", "credentials"):
            self.assertNotIn(forbidden, response.text)


    # -------------------------------------------- event schema registry / dry-run
    def test_catalog_exposes_versioned_event_schemas(self):
        self._as("tenant_viewer")
        response = self.client.get(f"{_BASE}/catalog")
        self.assertEqual(response.status_code, 200)
        catalog = response.json()
        schema = next(item for item in catalog["event_schemas"] if item["event_type"] == "booking.created")
        self.assertEqual(schema["capability_key"], "booking_notifications")
        self.assertEqual(schema["version"], 1)
        self.assertIn("customer.phone", schema["recipient_paths"])
        self.assertIn("booking.status", {field["path"] for field in schema["fields"]})

    def test_event_schema_metadata_endpoints_are_authenticated(self):
        self._as("tenant_analyst")
        events = self.client.get(f"{_BASE}/catalog/capabilities/booking_notifications/events")
        self.assertEqual(events.status_code, 200)
        self.assertEqual(len(events.json()), 3)
        schema = self.client.get(
            f"{_BASE}/catalog/capabilities/booking_notifications/events/booking.created"
        )
        self.assertEqual(schema.status_code, 200)
        self.assertEqual(schema.json()["event_type"], "booking.created")

    def test_create_rule_rejects_mismatched_capability_and_event(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={**_VALID_RULE_PAYLOAD, "capability_key": "call_notifications"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "unsupported_capability_event_pair")

    def test_create_rule_rejects_stale_schema_field(self):
        self._as("tenant_admin")
        response = self.client.post(
            f"{_BASE}/rules",
            json={
                **_VALID_RULE_PAYLOAD,
                "conditions_json": [{"field": "booking.removed_field", "operator": "equals", "value": "x"}],
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "condition_field_not_in_event_schema")

    def test_conditions_mode_any_is_persisted(self):
        rule = self._create_rule(conditions_mode="any")
        self.assertEqual(rule["conditions_mode"], "any")
        self.assertEqual(rule["event_schema_version"], 1)

    def test_dry_run_evaluates_without_creating_delivery(self):
        self._as("tenant_admin")
        body = {
            **_VALID_RULE_PAYLOAD,
            "conditions_mode": "all",
            "conditions_json": [{"field": "booking.status", "operator": "equals", "value": "scheduled"}],
            "event_payload": {
                "booking": {
                    "id": "booking-demo-001",
                    "status": "scheduled",
                    "start_at": "2026-08-12T15:00:00+00:00",
                    "timezone": "America/Bogota",
                },
                "customer": {"phone": "+573001112233"},
                "custom": {},
            },
        }
        response = self.client.post(f"{_BASE}/rules/test", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertTrue(result["matches"])
        self.assertTrue(result["condition_results"][0]["matched"])
        self.assertEqual(result["variables"], {"1": "Reserva confirmada"})
        self.assertNotIn("+573001112233", str(result["recipients_masked"]))
        self.assertIn("Reserva confirmada", result["preview"])
        with SessionLocal() as db:
            self.assertEqual(db.query(NotificationDelivery).count(), 0)

    def test_dry_run_requires_write_role(self):
        self._as("tenant_analyst")
        response = self.client.post(
            f"{_BASE}/rules/test",
            json={**_VALID_RULE_PAYLOAD, "event_payload": {}},
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
