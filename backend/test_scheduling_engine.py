from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.integrations import TenantGoogleCalendar, TenantGoogleCalendarConnection
from app.services.google_calendar_oauth_service import GoogleCalendarOAuthService
from app.services.scheduling_availability_service import SchedulingAvailabilityService
from app.services.scheduling_config_service import SchedulingConfigService
from app.services.scheduling_resource_service import SchedulingResourceService


class SchedulingEngineTests(Integration2ATestCase):
    def setUp(self):
        super().setUp()
        with SessionLocal() as db:
            service = GoogleCalendarOAuthService(db)
            self.connection = service.store_connection(
                tenant_id=self.tenant.id,
                user_id=self.user.id,
                google_account_email="schedule@example.com",
                access_token="token",
                refresh_token="refresh",
            )
            self.cal = TenantGoogleCalendar(
                tenant_id=self.tenant.id,
                connection_id=self.connection.id,
                google_calendar_id="primary",
                summary="Primary Calendar",
                is_primary=True,
                is_blocking=True,
                is_booking_destination=True,
            )
            db.add(self.cal)
            db.commit()

    def test_config_service_crud_and_dashboard_summary(self):
        with SessionLocal() as db:
            cfg_service = SchedulingConfigService(db)
            config = cfg_service.get_or_create_config(self.tenant.id)
            self.assertEqual(config.tenant_id, self.tenant.id)
            self.assertEqual(config.timezone, "America/Bogota")
            self.assertEqual(config.default_duration_minutes, 30)

            # Update config
            updated = cfg_service.update_config(
                self.tenant.id,
                {
                    "buffer_before_minutes": 10,
                    "buffer_after_minutes": 15,
                    "slot_interval_minutes": 15,
                },
            )
            self.assertEqual(updated.buffer_before_minutes, 10)
            self.assertEqual(updated.buffer_after_minutes, 15)
            self.assertEqual(updated.slot_interval_minutes, 15)

            # Dashboard summary
            summary = cfg_service.get_dashboard_summary(self.tenant.id)
            self.assertTrue(summary["google_connected"])
            self.assertEqual(summary["connected_calendars_count"], 1)
            self.assertIsInstance(summary["alerts"], list)

    def test_multi_shift_availability_calculation(self):
        with SessionLocal() as db:
            mock_g_service = MagicMock()
            mock_g_service.get_freebusy_intervals.return_value = []

            cfg_service = SchedulingConfigService(db)
            # Monday: 08:00 - 12:00, then 14:00 - 18:00 (lunch break 12:00 - 14:00)
            cfg_service.update_config(
                self.tenant.id,
                {
                    "working_hours_json": {
                        "tuesday": [
                            {"start": "08:00", "end": "12:00"},
                            {"start": "14:00", "end": "18:00"},
                        ]
                    }
                },
            )

            service = SchedulingAvailabilityService(db, google_calendar_service=mock_g_service)
            # 2026-09-15 is a Tuesday
            result = service.get_available_slots(
                tenant_id=self.tenant.id,
                date_input="2026-09-15",
                reference_datetime="2026-09-14 12:00:00",
                timezone_str="America/Bogota",
                slot_duration_minutes=30,
            )

            times = [s["time"] for s in result["available_slots"]]
            # Morning slots
            self.assertIn("08:00", times)
            self.assertIn("11:30", times)
            # Lunch break: NO slots between 12:00 and 14:00
            self.assertNotIn("12:00", times)
            self.assertNotIn("12:30", times)
            self.assertNotIn("13:00", times)
            self.assertNotIn("13:30", times)
            # Afternoon slots
            self.assertIn("14:00", times)
            self.assertIn("17:30", times)

    def test_buffer_before_and_after_blocking_window(self):
        with SessionLocal() as db:
            mock_g_service = MagicMock()
            # Busy interval from 10:00 to 10:30 local (15:00 to 15:30 UTC)
            mock_g_service.get_freebusy_intervals.return_value = [
                {
                    "start": datetime(2026, 9, 15, 15, 0, tzinfo=UTC),
                    "end": datetime(2026, 9, 15, 15, 30, tzinfo=UTC),
                }
            ]

            service = SchedulingAvailabilityService(db, google_calendar_service=mock_g_service)
            # Without buffers: 09:30 should be free, 10:00 busy, 10:30 free
            res_nobuf = service.get_available_slots(
                tenant_id=self.tenant.id,
                date_input="2026-09-15",
                reference_datetime="2026-09-14 12:00:00",
                slot_duration_minutes=30,
                buffer_before_minutes=0,
                buffer_after_minutes=0,
            )
            times_nobuf = [s["time"] for s in res_nobuf["available_slots"]]
            self.assertIn("09:30", times_nobuf)
            self.assertNotIn("10:00", times_nobuf)
            self.assertIn("10:30", times_nobuf)

            # With buffer_before=15 and buffer_after=15:
            # Slot 09:30 (09:30-10:00 + buf_after 15 min = 10:15) overlaps busy (10:00-10:30) -> BLOCKED
            # Slot 10:30 (10:30-11:00 - buf_before 15 min = 10:15) overlaps busy (10:00-10:30) -> BLOCKED
            res_buf = service.get_available_slots(
                tenant_id=self.tenant.id,
                date_input="2026-09-15",
                reference_datetime="2026-09-14 12:00:00",
                slot_duration_minutes=30,
                buffer_before_minutes=15,
                buffer_after_minutes=15,
            )
            times_buf = [s["time"] for s in res_buf["available_slots"]]
            self.assertNotIn("09:30", times_buf)
            self.assertNotIn("10:00", times_buf)
            self.assertNotIn("10:30", times_buf)
            self.assertIn("09:00", times_buf)
            self.assertIn("11:00", times_buf)

    def test_availability_exceptions(self):
        with SessionLocal() as db:
            res_service = SchedulingResourceService(db)
            # Create full-day holiday exception on 2026-09-15
            res_service.create_exception(
                tenant_id=self.tenant.id,
                exception_date=date(2026, 9, 15),
                exception_type="unavailable",
                reason="Festivo Nacional",
            )

            service = SchedulingAvailabilityService(db)
            result = service.get_available_slots(
                tenant_id=self.tenant.id,
                date_input="2026-09-15",
                reference_datetime="2026-09-14 12:00:00",
            )
            self.assertEqual(len(result["available_slots"]), 0)
            self.assertIn("Festivo Nacional", result["summary"])

    def test_round_robin_strict_never_falls_back_to_busy(self):
        with SessionLocal() as db:
            mock_g_service = MagicMock()
            res_service = SchedulingResourceService(db, mock_g_service)

            # Create team
            team = res_service.create_team(tenant_id=self.tenant.id, name="Ventas Inmobiliarias")

            # Create 2 resources
            r1 = res_service.create_resource(
                tenant_id=self.tenant.id,
                name="Asesor 1",
                email="asesor1@example.com",
            )
            r2 = res_service.create_resource(
                tenant_id=self.tenant.id,
                name="Asesor 2",
                email="asesor2@example.com",
            )
            res_service.add_team_member(tenant_id=self.tenant.id, team_id=team.id, resource_id=r1.id)
            res_service.add_team_member(tenant_id=self.tenant.id, team_id=team.id, resource_id=r2.id)

            # Scenario A: Both are free -> picks one of them (least recently
            # assigned; r1/r2 can tie on created_at when created back-to-back,
            # so either is a valid fairness pick)
            slot_time = datetime(2026, 9, 15, 15, 0, tzinfo=UTC)
            chosen, _ = res_service.select_resource_round_robin(
                tenant_id=self.tenant.id,
                team_id=team.id,
                slot_start=slot_time,
            )
            self.assertIsNotNone(chosen)
            self.assertIn(chosen.id, {r1.id, r2.id})

            # Scenario B: Resource 1 has an exception marking them unavailable
            res_service.create_exception(
                tenant_id=self.tenant.id,
                resource_id=r1.id,
                exception_date=date(2026, 9, 16),
                exception_type="unavailable",
                reason="Permiso médico",
            )
            slot_time_b = datetime(2026, 9, 16, 15, 0, tzinfo=UTC)
            chosen_b, _ = res_service.select_resource_round_robin(
                tenant_id=self.tenant.id,
                team_id=team.id,
                slot_start=slot_time_b,
            )
            self.assertIsNotNone(chosen_b)
            self.assertEqual(chosen_b.id, r2.id)  # R1 was skipped, R2 chosen

            # Scenario C: BOTH resources have exceptions (both unavailable)
            res_service.create_exception(
                tenant_id=self.tenant.id,
                resource_id=r2.id,
                exception_date=date(2026, 9, 16),
                exception_type="unavailable",
                reason="Vacaciones",
            )
            chosen_c, _ = res_service.select_resource_round_robin(
                tenant_id=self.tenant.id,
                team_id=team.id,
                slot_start=slot_time_b,
            )
            # STRICT: Must be (None, None), NEVER fall back to busy resource!
            self.assertIsNone(chosen_c)

    def test_tenant_isolation(self):
        # Create second tenant
        tenant_b, user_b = self._seed_tenant_user(slug="tenant-b", email="admin-b@example.com")
        with SessionLocal() as db:
            res_service = SchedulingResourceService(db)
            res_a = res_service.create_resource(tenant_id=self.tenant.id, name="Recurso A")
            res_b = res_service.create_resource(tenant_id=tenant_b.id, name="Recurso B")

            # Tenant A lists only their resources
            list_a = res_service.list_resources(self.tenant.id)
            self.assertEqual(len(list_a), 1)
            self.assertEqual(list_a[0].id, res_a.id)

            # Tenant B cannot access Tenant A resource
            lookup = res_service.get_resource(tenant_b.id, res_a.id)
            self.assertIsNone(lookup)
