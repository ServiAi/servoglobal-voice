from __future__ import annotations

import httpx
import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.core.scheduling_exceptions import (
    SchedulingAuthenticationError,
    SchedulingConflictError,
    SchedulingNotFoundError,
    SchedulingPermissionError,
    SchedulingUpstreamError,
    SchedulingValidationError,
)
from app.models.identity import Tenant, TenantMembership, User
from app.models.integrations import (
    TenantAgentSchedulingConfig,
    TenantBookingConfig,
    TenantIntegrationEvent,
    TenantSchedulingEventType,
    TenantSchedulingProviderObject,
    TenantSchedulingSchedule,
)
from app.services.calcom_client import CalComClient, CalComClientConfig, sanitize_calcom_error
from app.services.calcom_sync_service import CalComSyncService
from app.services.scheduling_provider_resolver import SchedulingProviderResolver


class CalComClientV2UnitTests(unittest.TestCase):
    def setUp(self):
        self.client = CalComClient(base_url="https://api.cal.com/v2")
        self.config = CalComClientConfig(api_key="cal_live_secret123")

    @patch("app.services.calcom_client.httpx.request")
    def test_get_current_user_and_discovery(self, mock_request):
        # 1. /me
        mock_request.side_effect = [
            httpx.Response(200, json={"status": "success", "data": {"id": 100, "username": "sales", "email": "sales@company.com"}}),
            httpx.Response(200, json={"status": "success", "data": [{"id": 1, "name": "Default", "isDefault": True}]}),
            httpx.Response(200, json={"status": "success", "data": [{"id": 10, "title": "Demo 30min", "slug": "demo-30"}]}),
            httpx.Response(200, json={"status": "success", "data": [{"id": 5, "name": "Sales Team"}]}),
        ]

        discovery = self.client.discover_account(self.config)
        self.assertEqual(discovery["user"]["username"], "sales")
        self.assertEqual(discovery["counts"]["schedules"], 1)
        self.assertEqual(discovery["counts"]["event_types"], 1)
        self.assertEqual(discovery["counts"]["teams"], 1)

    @patch("app.services.calcom_client.httpx.request")
    def test_schedule_crud(self, mock_request):
        mock_request.side_effect = [
            httpx.Response(200, json={"status": "success", "data": [{"id": 1, "name": "Horario comercial"}]}),
            httpx.Response(200, json={"status": "success", "data": {"id": 1, "name": "Horario comercial"}}),
            httpx.Response(201, json={"status": "success", "data": {"id": 2, "name": "Nuevo horario"}}),
            httpx.Response(200, json={"status": "success", "data": {"id": 2, "name": "Horario editado"}}),
            httpx.Response(204, text=""),
        ]

        schedules = self.client.list_schedules(self.config)
        self.assertEqual(len(schedules), 1)

        sched = self.client.get_schedule(self.config, 1)
        self.assertEqual(sched["name"], "Horario comercial")

        created = self.client.create_schedule(self.config, {"name": "Nuevo horario"})
        self.assertEqual(created["id"], 2)

        updated = self.client.update_schedule(self.config, 2, {"name": "Horario editado"})
        self.assertEqual(updated["name"], "Horario editado")

        deleted = self.client.delete_schedule(self.config, 2)
        self.assertTrue(deleted)

    @patch("app.services.calcom_client.httpx.request")
    def test_event_type_crud(self, mock_request):
        mock_request.side_effect = [
            httpx.Response(200, json={"status": "success", "data": [{"id": 50, "title": "Demo", "slug": "demo"}]}),
            httpx.Response(200, json={"status": "success", "data": {"id": 50, "title": "Demo", "slug": "demo"}}),
            httpx.Response(201, json={"status": "success", "data": {"id": 51, "title": "Consultoría", "slug": "consultoria"}}),
            httpx.Response(200, json={"status": "success", "data": {"id": 51, "title": "Consultoría VIP", "slug": "consultoria-vip"}}),
            httpx.Response(204, text=""),
        ]

        ets = self.client.list_event_types(self.config)
        self.assertEqual(len(ets), 1)

        et = self.client.get_event_type(self.config, 50)
        self.assertEqual(et["slug"], "demo")

        created = self.client.create_event_type(self.config, {"title": "Consultoría", "slug": "consultoria"})
        self.assertEqual(created["id"], 51)

        updated = self.client.update_event_type(self.config, 51, {"title": "Consultoría VIP"})
        self.assertEqual(updated["title"], "Consultoría VIP")

        deleted = self.client.delete_event_type(self.config, 51)
        self.assertTrue(deleted)

    @patch("app.services.calcom_client.httpx.request")
    def test_error_mapping_and_secret_sanitization(self, mock_request):
        # 401
        mock_request.return_value = httpx.Response(401, text="Bearer cal_live_secret123 is invalid")
        with self.assertRaises(SchedulingAuthenticationError) as ctx:
            self.client.get_current_user(self.config)
        self.assertNotIn("cal_live_secret123", str(ctx.exception))
        self.assertIn("redacted", str(ctx.exception))

        # 403 plan
        mock_request.return_value = httpx.Response(403, text="Feature teams requires organization plan")
        with self.assertRaises(SchedulingPermissionError) as ctx:
            self.client.list_teams(self.config)
        self.assertIn("no permite administrar equipos", str(ctx.exception))

        # 404
        mock_request.return_value = httpx.Response(404, text="Not found")
        with self.assertRaises(SchedulingNotFoundError):
            self.client.get_schedule(self.config, 999)

        # 409
        mock_request.return_value = httpx.Response(409, text="Conflict slug already exists")
        with self.assertRaises(SchedulingConflictError):
            self.client.create_event_type(self.config, {"slug": "existing"})

        # 422
        mock_request.return_value = httpx.Response(422, text="Validation error in duration")
        with self.assertRaises(SchedulingValidationError):
            self.client.create_event_type(self.config, {"duration": -5})

        # 500
        mock_request.return_value = httpx.Response(500, text="Internal server error")
        with self.assertRaises(SchedulingUpstreamError):
            self.client.list_schedules(self.config)


class CalComSyncServiceIntegrationTests(Integration2ATestCase):
    def test_sync_upserts_projections_and_marks_missing(self):
        self.configure_calcom()

        mock_discovery = {
            "user": {"id": 12, "username": "dr_smith", "email": "smith@clinic.com"},
            "schedules": [
                {
                    "id": 101,
                    "name": "Horario Médico",
                    "timeZone": "America/Bogota",
                    "isDefault": True,
                    "availability": {"monday": [{"start": "08:00", "end": "12:00"}]},
                }
            ],
            "event_types": [
                {
                    "id": 201,
                    "title": "Consulta General",
                    "slug": "consulta-general",
                    "length": 45,
                    "scheduleId": 101,
                }
            ],
            "teams": [
                {"id": 301, "name": "Médicos Generales", "slug": "medicos-generales"}
            ],
        }

        with patch("app.services.calcom_sync_service.CalComClient.discover_account", return_value=mock_discovery):
            with SessionLocal() as db:
                sync_service = CalComSyncService(db)
                result = sync_service.sync(self.tenant.id)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["counts"]["schedules"], 1)
        self.assertEqual(result["counts"]["event_types"], 1)
        self.assertEqual(result["counts"]["teams"], 1)

        # Verify DB projections
        with SessionLocal() as db:
            schedules = list(db.scalars(select(TenantSchedulingSchedule).where(TenantSchedulingSchedule.tenant_id == self.tenant.id)))
            event_types = list(db.scalars(select(TenantSchedulingEventType).where(TenantSchedulingEventType.tenant_id == self.tenant.id)))
            provider_objs = list(db.scalars(select(TenantSchedulingProviderObject).where(TenantSchedulingProviderObject.tenant_id == self.tenant.id)))
            events = list(db.scalars(select(TenantIntegrationEvent).where(TenantIntegrationEvent.tenant_id == self.tenant.id, TenantIntegrationEvent.event_type == "calcom_sync")))

        self.assertEqual(len(schedules), 1)
        self.assertEqual(schedules[0].name, "Horario Médico")
        self.assertEqual(schedules[0].provider_schedule_id, "101")
        self.assertEqual(schedules[0].sync_status, "synced")

        self.assertEqual(len(event_types), 1)
        self.assertEqual(event_types[0].name, "Consulta General")
        self.assertEqual(event_types[0].duration_minutes, 45)
        self.assertEqual(event_types[0].provider_event_type_id, "201")
        self.assertEqual(event_types[0].local_schedule_id, schedules[0].id)

        self.assertEqual(len(provider_objs), 3)  # schedule, event_type, team
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].status, "success")

        # Repeat sync with missing event type -> marks remote_deleted
        mock_discovery_deleted = {
            "user": {"id": 12, "username": "dr_smith"},
            "schedules": [mock_discovery["schedules"][0]],
            "event_types": [],  # Event type removed remotely
            "teams": [],
        }
        with patch("app.services.calcom_sync_service.CalComClient.discover_account", return_value=mock_discovery_deleted):
            with SessionLocal() as db:
                sync_service = CalComSyncService(db)
                sync_service.sync(self.tenant.id)

        with SessionLocal() as db:
            et = db.scalar(select(TenantSchedulingEventType).where(TenantSchedulingEventType.tenant_id == self.tenant.id, TenantSchedulingEventType.provider_event_type_id == "201"))
            self.assertIsNotNone(et)
            self.assertEqual(et.sync_status, "remote_deleted")


class SchedulingProviderResolverAndMultitenancyTests(Integration2ATestCase):
    def test_provider_resolver_runtime_and_admin(self):
        with SessionLocal() as db:
            resolver = SchedulingProviderResolver(db)
            admin_google = resolver.resolve_admin_provider(self.tenant.id, "google_calendar")
            self.assertFalse(admin_google.capabilities().native_schedules)

            admin_calcom = resolver.resolve_admin_provider(self.tenant.id, "calcom")
            self.assertTrue(admin_calcom.capabilities().native_schedules)

    def test_strict_multitenancy_isolation(self):
        # Create Tenant B
        with SessionLocal() as db:
            tenant_b = Tenant(name="Tenant B", slug="tenant-b")
            user_b = User(email="tenant_b@example.com", name="User B", status="active", is_internal=False)
            db.add_all([tenant_b, user_b])
            db.commit()
            db.refresh(tenant_b)
            db.refresh(user_b)

            # Add schedule and event type to Tenant B
            sched_b = TenantSchedulingSchedule(
                tenant_id=tenant_b.id,
                provider="calcom",
                name="Horario Secreto B",
                provider_schedule_id="sched-b",
            )
            et_b = TenantSchedulingEventType(
                tenant_id=tenant_b.id,
                provider="calcom",
                name="Cita Confidencial B",
                slug="cita-b",
                provider_event_type_id="et-b",
            )
            db.add_all([sched_b, et_b])
            db.commit()
            sched_b_id = sched_b.id
            et_b_id = et_b.id

        # Authenticated as Tenant A via self.client
        # Querying schedules must not return Tenant B's schedule
        resp = self.client.get("/api/v1/scheduling/schedules")
        self.assertEqual(resp.status_code, 200)
        names = [s["name"] for s in resp.json()]
        self.assertNotIn("Horario Secreto B", names)

        # Querying event types must not return Tenant B's event type
        resp = self.client.get("/api/v1/scheduling/event-types")
        self.assertEqual(resp.status_code, 200)
        et_names = [e["name"] for e in resp.json()]
        self.assertNotIn("Cita Confidencial B", et_names)

        # Tenant A trying to mutate Tenant B's event type must fail / not affect Tenant B
        resp = self.client.patch(f"/api/v1/scheduling/event-types/{et_b_id}", json={"name": "Hacked"})
        with SessionLocal() as db:
            et_check = db.scalar(select(TenantSchedulingEventType).where(TenantSchedulingEventType.id == et_b_id))
            self.assertEqual(et_check.name, "Cita Confidencial B")
            self.assertEqual(et_check.tenant_id, tenant_b.id)


if __name__ == "__main__":
    unittest.main()
