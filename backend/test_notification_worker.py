import logging
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from uuid import uuid4

TEST_DB_PATH = Path("serviai_notification_worker_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.core import config as config_module
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.crm import CrmContact, CrmLead, CrmPipelineStage
from app.models.identity import Tenant
from app.models.integrations import TenantWhatsAppConfig, TenantWhatsAppTemplate
from app.models.notifications import DomainEvent, NotificationDelivery, TenantNotificationRule
from app.services.domain_event_service import DomainEventService
from app.services.notification_delivery_recovery_service import NotificationDeliveryRecoveryService
from app.services.secret_manager_service import SecretManager
from app.services.whatsapp_client import WhatsAppCloudClient, WhatsAppCloudClientError
from app.workers import notification_worker as worker_module

FIXED_NOW = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
PAST = FIXED_NOW - timedelta(hours=1)

_BOOKING_PAYLOAD = {
    "booking": {"id": "bk-1", "status": "confirmed", "start_at": "2026-08-10T15:30:00+00:00", "timezone": "America/Bogota"},
    "customer": {"phone": "+573001112233"},
    "custom": {"advisor_name": "Ana"},
}

_VARIABLE_MAPPING = {
    "1": {"source": "event_field", "path": "custom.advisor_name"},
    "2": {
        "source": "event_field",
        "path": "booking.start_at",
        "format": "datetime_dmy_24h",
        "timezone": "America/Bogota",
    },
}


class _FakeClient(WhatsAppCloudClient):
    def __init__(self, *, fail: bool = False, message_id: str = "wamid.worker-1"):
        super().__init__()
        self.fail = fail
        self.message_id = message_id
        self.send_calls = 0

    def send_template_message(self, *args, **kwargs):
        self.send_calls += 1
        if self.fail:
            raise WhatsAppCloudClientError("Bearer secrettoken123456789012345 rejected for +573001112233")
        return {"messages": [{"id": self.message_id}]}


class _BaseWorkerTestCase(unittest.TestCase):
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
        self.worker_config = config_module.NotificationWorkerSettings.from_settings(config_module.settings)

    def tearDown(self):
        self.db.close()

    def _create_tenant(self, slug: str = "worker-tenant") -> str:
        tenant = Tenant(name=f"Empresa {slug}", slug=f"{slug}-{uuid4().hex[:8]}")
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant.id

    def _seed_ready_delivery(self, *, status: str = "pending", scheduled_for: datetime = PAST) -> tuple[str, NotificationDelivery]:
        tenant_id = self._create_tenant()
        config = TenantWhatsAppConfig(
            tenant_id=tenant_id,
            provider="whatsapp_cloud",
            status="active",
            phone_number_id="phone-1",
            display_phone_number="+573000000000",
            default_language="es",
            access_token_encrypted=SecretManager().encrypt_secret("EA_test_token_1234567890"),
        )
        template = TenantWhatsAppTemplate(
            tenant_id=tenant_id,
            template_key="tpl_meeting",
            provider_template_name="tpl_meeting",
            name="tpl_meeting",
            category="utility",
            language="es",
            body="Hola {{1}} {{2}}",
            variables_json={
                "parameters": [{"key": "1"}, {"key": "2"}],
                "meta_status": "APPROVED",
                "source": "meta_sync",
            },
            status="active",
        )
        self.db.add_all([config, template])
        self.db.commit()
        self.db.refresh(template)

        rule = TenantNotificationRule(
            tenant_id=tenant_id,
            name=f"rule-{uuid4().hex[:8]}",
            capability_key="booking_notifications",
            event_type="booking.created",
            channel="whatsapp",
            action_type="send_whatsapp_template",
            template_key=template.template_key,
            recipient_strategy="event_customer",
            conditions_json=[],
            variable_mapping_json=_VARIABLE_MAPPING,
        )
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)

        event = DomainEventService(self.db).publish(
            tenant_id=tenant_id,
            event_type="booking.created",
            source="calcom",
            idempotency_key=f"evt-{uuid4().hex[:8]}",
            payload=_BOOKING_PAYLOAD,
            available_at=PAST,
        ).event

        delivery = NotificationDelivery(
            tenant_id=tenant_id,
            domain_event_id=event.id,
            notification_rule_id=rule.id,
            channel="whatsapp",
            recipient="+573001112233",
            template_key=template.template_key,
            status=status,
            scheduled_for=scheduled_for,
            next_attempt_at=scheduled_for if status in ("pending", "failed") else None,
            attempts=0,
            idempotency_key=f"delivery-{uuid4().hex[:8]}",
            metadata_json={},
        )
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return tenant_id, delivery


class RunOnceTests(_BaseWorkerTestCase):
    def test_once_processes_the_queue(self):
        _, delivery = self._seed_ready_delivery()
        client = _FakeClient()
        exit_code = worker_module.run_once(
            worker_config=self.worker_config,
            worker_id="w1",
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            client_factory=lambda: client,
        )
        self.assertEqual(exit_code, 0)
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "sent")
        self.assertEqual(client.send_calls, 1)

    def test_no_work_returns_cleanly(self):
        exit_code = worker_module.run_once(
            worker_config=self.worker_config, worker_id="w1", session_factory=SessionLocal, now_fn=lambda: FIXED_NOW
        )
        self.assertEqual(exit_code, 0)

    def test_one_failure_does_not_stop_the_batch(self):
        _, ok_delivery = self._seed_ready_delivery()
        _, bad_delivery = self._seed_ready_delivery()

        calls = {"n": 0}

        def factory():
            calls["n"] += 1
            return _FakeClient(fail=(calls["n"] == 1))

        exit_code = worker_module.run_once(
            worker_config=self.worker_config,
            worker_id="w1",
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            client_factory=factory,
        )
        self.assertEqual(exit_code, 0)
        self.db.refresh(ok_delivery)
        self.db.refresh(bad_delivery)
        statuses = {ok_delivery.status, bad_delivery.status}
        self.assertIn("sent", statuses)
        self.assertIn("failed", statuses)

    def test_exit_code_of_individual_failure_is_not_fatal(self):
        _, delivery = self._seed_ready_delivery()
        exit_code = worker_module.run_once(
            worker_config=self.worker_config,
            worker_id="w1",
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            client_factory=lambda: _FakeClient(fail=True),
        )
        self.assertEqual(exit_code, 0)
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "failed")

    def test_uses_a_new_session_per_delivery(self):
        self._seed_ready_delivery()
        self._seed_ready_delivery()
        opened = []
        real_factory = SessionLocal

        def counting_factory():
            session = real_factory()
            opened.append(session)
            return session

        worker_module.run_once(
            worker_config=self.worker_config,
            worker_id="w1",
            session_factory=counting_factory,
            now_fn=lambda: FIXED_NOW,
            client_factory=lambda: _FakeClient(),
        )
        # recovery session + claim session + one session per claimed delivery
        self.assertGreaterEqual(len(opened), 1 + 1 + 2)
        for session in opened:
            session.close()

    def test_recovery_runs_during_once_mode(self):
        tenant_id, delivery = self._seed_ready_delivery()
        # Simulate an abandoned claim with an expired lease and no linked message.
        delivery.status = "processing"
        delivery.claim_token = "stale-token"
        delivery.claimed_at = FIXED_NOW - timedelta(minutes=10)
        delivery.claim_expires_at = FIXED_NOW - timedelta(minutes=5)
        self.db.add(delivery)
        self.db.commit()

        worker_module.run_once(
            worker_config=self.worker_config, worker_id="w1", session_factory=SessionLocal, now_fn=lambda: FIXED_NOW
        )
        self.db.refresh(delivery)
        # Recovery must have reconciled the abandoned claim (no message -> retry).
        self.assertIsNone(delivery.claim_token)
        self.assertEqual(delivery.status, "failed")
        self.assertEqual(delivery.error_message, "worker_claim_expired_before_send")


class ProviderFailureBackoffTests(_BaseWorkerTestCase):
    """The executor never finalizes a provider failure itself (Fix: preserve
    notification claim through finalization) -- these confirm the worker's
    immediate call to NotificationRetryPolicy.apply_failure right after is
    what actually applies backoff, clears the claim, and dead-letters
    permanent errors."""

    def test_provider_failure_leaves_a_real_backoff_window(self):
        _, delivery = self._seed_ready_delivery()
        worker_module.run_cycle(
            worker_config=self.worker_config,
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            client_factory=lambda: _FakeClient(fail=True),
        )
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "failed")
        self.assertIsNotNone(delivery.next_attempt_at)
        stored = delivery.next_attempt_at
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        self.assertGreater(stored, FIXED_NOW)

    def test_provider_failure_uses_the_configured_base_backoff(self):
        _, delivery = self._seed_ready_delivery()
        worker_module.run_cycle(
            worker_config=self.worker_config,
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            client_factory=lambda: _FakeClient(fail=True),
        )
        self.db.refresh(delivery)
        stored = delivery.next_attempt_at
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        expected_max = FIXED_NOW + timedelta(seconds=self.worker_config.base_retry_seconds + self.worker_config.jitter_seconds)
        self.assertLessEqual(stored, expected_max)

    def test_provider_failure_clears_the_claim_after_the_policy_runs(self):
        _, delivery = self._seed_ready_delivery()
        worker_module.run_cycle(
            worker_config=self.worker_config,
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            client_factory=lambda: _FakeClient(fail=True),
        )
        self.db.refresh(delivery)
        self.assertIsNone(delivery.claim_token)
        self.assertIsNone(delivery.claimed_at)
        self.assertIsNone(delivery.claim_expires_at)

    def test_second_provider_failure_increases_the_backoff(self):
        _, delivery = self._seed_ready_delivery()
        worker_module.run_cycle(
            worker_config=self.worker_config,
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            client_factory=lambda: _FakeClient(fail=True),
        )
        self.db.refresh(delivery)
        first_delay = delivery.next_attempt_at - FIXED_NOW.replace(tzinfo=None)

        second_now = FIXED_NOW + timedelta(seconds=1)
        delivery.next_attempt_at = second_now
        self.db.add(delivery)
        self.db.commit()
        worker_module.run_cycle(
            worker_config=self.worker_config,
            session_factory=SessionLocal,
            now_fn=lambda: second_now,
            client_factory=lambda: _FakeClient(fail=True),
        )
        self.db.refresh(delivery)
        second_delay = delivery.next_attempt_at - second_now.replace(tzinfo=None)
        self.assertGreater(second_delay, first_delay)

    def test_max_attempts_produces_dead_letter(self):
        _, delivery = self._seed_ready_delivery()
        now = FIXED_NOW
        for _ in range(self.worker_config.max_attempts):
            worker_module.run_cycle(
                worker_config=self.worker_config,
                session_factory=SessionLocal,
                now_fn=lambda n=now: n,
                client_factory=lambda: _FakeClient(fail=True),
            )
            self.db.refresh(delivery)
            if delivery.status == "dead_letter":
                break
            delivery.next_attempt_at = now
            self.db.add(delivery)
            self.db.commit()
            now = now + timedelta(seconds=1)
        self.assertEqual(delivery.status, "dead_letter")
        # dead_letter is not in CLAIMABLE_STATUSES, so it can never be
        # reclaimed and retried again by mistake.
        self.assertIsNone(delivery.claim_token)
        self.assertIsNone(delivery.next_attempt_at)

    def test_permanent_variable_error_dead_letters_without_calling_meta(self):
        tenant_id, delivery = self._seed_ready_delivery()
        event = self.db.query(DomainEvent).filter(DomainEvent.id == delivery.domain_event_id).first()
        event.payload_json = {**event.payload_json, "custom": {}}
        self.db.add(event)
        self.db.commit()

        client = _FakeClient()
        worker_module.run_cycle(
            worker_config=self.worker_config,
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            client_factory=lambda: client,
        )
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "dead_letter")
        self.assertEqual(client.send_calls, 0)
        # Never left as a plain "failed" that a later batch could reclaim
        # and retry against the same permanently-broken configuration.
        self.assertIsNone(delivery.claim_token)

    def test_permanent_template_error_dead_letters(self):
        tenant_id, delivery = self._seed_ready_delivery()
        template = self.db.query(TenantWhatsAppTemplate).filter(TenantWhatsAppTemplate.tenant_id == tenant_id).first()
        template.status = "inactive"
        self.db.add(template)
        self.db.commit()

        worker_module.run_cycle(
            worker_config=self.worker_config,
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            client_factory=lambda: _FakeClient(),
        )
        self.db.refresh(delivery)
        self.assertEqual(delivery.status, "dead_letter")

    def test_worker_own_failure_is_not_treated_as_stale_owner(self):
        # The worker applies apply_failure with its own freshly-claimed
        # token immediately after its own failed attempt -- that must never
        # be rejected as a stale claim.
        _, delivery = self._seed_ready_delivery()
        counters = worker_module.run_cycle(
            worker_config=self.worker_config,
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            client_factory=lambda: _FakeClient(fail=True),
        )
        self.assertEqual(counters["retried"], 1)
        self.assertEqual(counters["dead_lettered"], 0)
        self.db.refresh(delivery)
        # A stale_owner outcome would have left the delivery untouched
        # (still "processing" with the original claim); it must instead
        # show the retry policy's real decision.
        self.assertEqual(delivery.status, "failed")
        self.assertIsNone(delivery.claim_token)

    def test_provider_failure_increments_retried_counter(self):
        self._seed_ready_delivery()
        counters = worker_module.run_cycle(
            worker_config=self.worker_config,
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            client_factory=lambda: _FakeClient(fail=True),
        )
        self.assertEqual(counters["retried"], 1)

    def test_permanent_failure_increments_dead_lettered_counter(self):
        tenant_id, delivery = self._seed_ready_delivery()
        event = self.db.query(DomainEvent).filter(DomainEvent.id == delivery.domain_event_id).first()
        event.payload_json = {**event.payload_json, "custom": {}}
        self.db.add(event)
        self.db.commit()

        counters = worker_module.run_cycle(
            worker_config=self.worker_config,
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            client_factory=lambda: _FakeClient(),
        )
        self.assertEqual(counters["dead_lettered"], 1)

    def test_delivery_ends_the_cycle_in_the_expected_state(self):
        _, ok_delivery = self._seed_ready_delivery()
        _, failing_delivery = self._seed_ready_delivery()
        event = self.db.query(DomainEvent).filter(DomainEvent.id == failing_delivery.domain_event_id).first()
        event.payload_json = {**event.payload_json, "custom": {}}
        self.db.add(event)
        self.db.commit()

        worker_module.run_cycle(
            worker_config=self.worker_config,
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            client_factory=lambda: _FakeClient(),
        )
        self.db.refresh(ok_delivery)
        self.db.refresh(failing_delivery)
        self.assertEqual(ok_delivery.status, "sent")
        self.assertEqual(failing_delivery.status, "dead_letter")


class RunCycleShutdownTests(_BaseWorkerTestCase):
    def test_stop_requested_mid_batch_still_finishes_the_whole_batch(self):
        # run_cycle no longer accepts (or consults) a should_stop callback:
        # a claimed batch is always drained in full. This simulates a
        # SIGTERM/SIGINT arriving while the first delivery is in flight.
        _, first = self._seed_ready_delivery()
        _, second = self._seed_ready_delivery()
        flag = worker_module._ShutdownFlag()
        calls = {"n": 0}

        def factory():
            calls["n"] += 1
            if calls["n"] == 1:
                flag.request_stop()
            return _FakeClient()

        counters = worker_module.run_cycle(
            worker_config=self.worker_config,
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            client_factory=factory,
        )
        self.assertTrue(flag.stop_requested)
        self.assertEqual(counters["claimed"], 2)
        self.assertEqual(counters["sent"], 2)
        self.db.refresh(first)
        self.db.refresh(second)
        self.assertEqual(first.status, "sent")
        self.assertEqual(second.status, "sent")

    def test_forever_sigterm_during_batch_finishes_batch_then_stops(self):
        _, first = self._seed_ready_delivery()
        _, second = self._seed_ready_delivery()
        flag = worker_module._ShutdownFlag()
        calls = {"n": 0}

        def factory():
            calls["n"] += 1
            if calls["n"] == 1:
                flag.request_stop()
            return _FakeClient()

        sleep_calls = {"n": 0}

        def sleep_fn(_seconds):
            sleep_calls["n"] += 1

        cycle_calls = {"n": 0}
        real_run_cycle = worker_module.run_cycle

        def counting_run_cycle(**kwargs):
            cycle_calls["n"] += 1
            return real_run_cycle(**kwargs)

        with mock.patch.object(worker_module, "run_cycle", side_effect=counting_run_cycle):
            exit_code = worker_module.run_forever(
                worker_config=self.worker_config,
                worker_id="w1",
                session_factory=SessionLocal,
                now_fn=lambda: FIXED_NOW,
                sleep_fn=sleep_fn,
                install_signals=False,
                client_factory=factory,
                shutdown_flag=flag,
            )
        self.assertEqual(exit_code, 0)
        self.db.refresh(first)
        self.db.refresh(second)
        self.assertEqual(first.status, "sent")
        self.assertEqual(second.status, "sent")
        self.assertNotIn("processing", {first.status, second.status})
        # Only one batch (one run_cycle call) is ever claimed: the flag was
        # already set by the time the current batch finished, so run_forever
        # must not claim a second batch.
        self.assertEqual(cycle_calls["n"], 1)
        self.assertEqual(sleep_calls["n"], 0)

    def test_sigint_handler_sets_the_same_flag_as_sigterm(self):
        flag = worker_module._ShutdownFlag()
        with mock.patch("app.workers.notification_worker.signal.signal") as mock_signal:
            worker_module._install_signal_handlers(flag)
        handlers = {call.args[0]: call.args[1] for call in mock_signal.call_args_list}
        import signal as signal_module

        self.assertFalse(flag.stop_requested)
        handlers[signal_module.SIGINT](signal_module.SIGINT, None)
        self.assertTrue(flag.stop_requested)

    def test_forever_loop_stops_claiming_new_batches_once_flag_is_set(self):
        flag = worker_module._ShutdownFlag()
        call_count = {"n": 0}

        def sleep_and_stop(_seconds):
            call_count["n"] += 1
            flag.request_stop()

        exit_code = worker_module.run_forever(
            worker_config=self.worker_config,
            worker_id="w1",
            session_factory=SessionLocal,
            now_fn=lambda: FIXED_NOW,
            sleep_fn=sleep_and_stop,
            install_signals=False,
            shutdown_flag=flag,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(call_count["n"], 1)

    def test_shutdown_flag_request_stop_sets_flag(self):
        flag = worker_module._ShutdownFlag()
        self.assertFalse(flag.stop_requested)
        flag.request_stop()
        self.assertTrue(flag.stop_requested)

    def test_signal_handlers_are_installed_for_sigterm_and_sigint(self):
        flag = worker_module._ShutdownFlag()
        with mock.patch("app.workers.notification_worker.signal.signal") as mock_signal:
            worker_module._install_signal_handlers(flag)
        registered = {call.args[0] for call in mock_signal.call_args_list}
        import signal as signal_module

        self.assertIn(signal_module.SIGTERM, registered)
        self.assertIn(signal_module.SIGINT, registered)


class RecoveryIntervalTests(_BaseWorkerTestCase):
    def test_recovery_respects_interval_in_forever_mode(self):
        flag = worker_module._ShutdownFlag()
        ticks = iter([FIXED_NOW, FIXED_NOW + timedelta(seconds=5), FIXED_NOW + timedelta(seconds=10)])
        stop_after = {"n": 0}

        def now_fn():
            try:
                return next(ticks)
            except StopIteration:
                flag.request_stop()
                return FIXED_NOW + timedelta(seconds=10)

        def sleep_fn(_seconds):
            stop_after["n"] += 1
            if stop_after["n"] >= 2:
                flag.request_stop()

        real_recover_batch = NotificationDeliveryRecoveryService.recover_batch

        def _wrapped(self_, **kwargs):
            return real_recover_batch(self_, **kwargs)

        with mock.patch.object(
            NotificationDeliveryRecoveryService, "recover_batch", side_effect=_wrapped, autospec=True
        ) as spy:
            worker_module.run_forever(
                worker_config=self.worker_config,
                worker_id="w1",
                session_factory=SessionLocal,
                now_fn=now_fn,
                sleep_fn=sleep_fn,
                install_signals=False,
                shutdown_flag=flag,
            )
        # Recovery interval (60s default) is far larger than the few seconds
        # elapsed between iterations, so recovery must run only on the first one.
        self.assertEqual(spy.call_count, 1)


class ConfigurationAndDialectTests(_BaseWorkerTestCase):
    def test_invalid_config_fails_safely(self):
        original = config_module.settings.NOTIFICATION_WORKER_MAX_ATTEMPTS
        config_module.settings.NOTIFICATION_WORKER_MAX_ATTEMPTS = 0
        try:
            exit_code = worker_module.main(["--once"], skip_postgresql_check=True)
        finally:
            config_module.settings.NOTIFICATION_WORKER_MAX_ATTEMPTS = original
        self.assertEqual(exit_code, 1)

    def test_sqlite_is_rejected_for_real_runs(self):
        exit_code = worker_module.main(["--once"], skip_postgresql_check=False)
        self.assertEqual(exit_code, 1)

    def test_postgresql_dialect_is_accepted(self):
        fake_engine = mock.Mock()
        fake_engine.dialect.name = "postgresql"
        with mock.patch.object(worker_module, "engine", fake_engine):
            worker_module._require_postgresql(skip_check=False)  # must not raise

    def test_skip_check_bypasses_dialect_requirement(self):
        worker_module._require_postgresql(skip_check=True)  # must not raise even on sqlite


class LoggingSafetyTests(_BaseWorkerTestCase):
    def test_execution_error_logs_do_not_contain_sensitive_data(self):
        tenant_id, delivery = self._seed_ready_delivery()
        # Break the template so execution fails before ever calling the provider.
        event = self.db.query(DomainEvent).filter(DomainEvent.id == delivery.domain_event_id).first()
        event.payload_json = {**event.payload_json, "custom": {}}
        self.db.add(event)
        self.db.commit()

        with self.assertLogs("app.workers.notification_worker", level="ERROR") as captured:
            worker_module.run_cycle(
                worker_config=self.worker_config,
                session_factory=SessionLocal,
                now_fn=lambda: FIXED_NOW,
                client_factory=lambda: _FakeClient(),
            )
        joined = "\n".join(captured.output)
        self.assertNotIn("+573001112233", joined)
        self.assertNotIn("@", joined)


if __name__ == "__main__":
    unittest.main()
