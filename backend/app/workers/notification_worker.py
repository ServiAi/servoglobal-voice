"""Durable WhatsApp notification worker.

Runs as an independent process from the API:

    python -m app.workers.notification_worker            # loop forever
    python -m app.workers.notification_worker --once      # drain the queue and exit

It never runs inside FastAPI's lifecycle and must never be replaced by
BackgroundTasks — durability comes from PostgreSQL row claims
(SELECT ... FOR UPDATE SKIP LOCKED), not from the worker process itself.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from app.core.config import NotificationWorkerConfigurationError, NotificationWorkerSettings, settings
from app.db.session import SessionLocal, engine
from app.services.notification_delivery_claim_service import NotificationDeliveryClaimService
from app.services.notification_delivery_recovery_service import NotificationDeliveryRecoveryService
from app.services.notification_retry_policy import NotificationRetryPolicy
from app.services.whatsapp_notification_executor import (
    WhatsAppNotificationExecutionError,
    WhatsAppNotificationExecutor,
)

logger = logging.getLogger(__name__)

_MAX_ONCE_BATCHES = 200

_EMPTY_COUNTERS = {
    "claimed": 0,
    "sent": 0,
    "failed": 0,
    "retried": 0,
    "dead_lettered": 0,
    "manual_review": 0,
    "cancelled": 0,
    "recovered": 0,
}


class NotificationWorkerStartupError(RuntimeError):
    pass


class _ShutdownFlag:
    def __init__(self) -> None:
        self.stop_requested = False

    def request_stop(self, *_args: object) -> None:
        self.stop_requested = True


def _install_signal_handlers(flag: _ShutdownFlag) -> None:
    signal.signal(signal.SIGTERM, flag.request_stop)
    signal.signal(signal.SIGINT, flag.request_stop)


def _require_postgresql(*, skip_check: bool) -> None:
    if skip_check:
        return
    if engine.dialect.name != "postgresql":
        raise NotificationWorkerStartupError("notification_worker_requires_postgresql")


def _make_retry_policy(db, worker_config: NotificationWorkerSettings) -> NotificationRetryPolicy:
    return NotificationRetryPolicy(
        db,
        base_retry_seconds=worker_config.base_retry_seconds,
        max_retry_seconds=worker_config.max_retry_seconds,
        jitter_seconds=worker_config.jitter_seconds,
    )


def run_cycle(
    *,
    worker_config: NotificationWorkerSettings,
    session_factory: Callable[[], object] = SessionLocal,
    now_fn: Callable[[], datetime] | None = None,
    run_recovery: bool = True,
    client_factory: Callable[[], object] | None = None,
) -> dict[str, int]:
    resolve_now = now_fn or (lambda: datetime.now(timezone.utc))
    counters = dict(_EMPTY_COUNTERS)

    if run_recovery:
        recovery_db = session_factory()
        try:
            retry_policy = _make_retry_policy(recovery_db, worker_config)
            recovery_service = NotificationDeliveryRecoveryService(recovery_db, retry_policy=retry_policy)
            outcomes = recovery_service.recover_batch(
                now=resolve_now(),
                legacy_stale_seconds=worker_config.legacy_stale_seconds,
                max_attempts=worker_config.max_attempts,
                batch_size=worker_config.recovery_batch_size,
            )
            counters["recovered"] = len(outcomes)
        finally:
            recovery_db.close()

    claim_db = session_factory()
    try:
        claims = NotificationDeliveryClaimService(claim_db).claim_batch(
            now=resolve_now(),
            lease_seconds=worker_config.lease_seconds,
            max_attempts=worker_config.max_attempts,
            batch_size=worker_config.batch_size,
        )
    finally:
        claim_db.close()

    counters["claimed"] = len(claims)

    # A claimed batch is always processed to completion: shutdown is only
    # honored before the *next* batch is claimed (see run_forever), never
    # mid-batch, so a delivery is never abandoned in `processing` just
    # because a shutdown signal happened to arrive while we were working.
    for claim in claims:
        db = session_factory()
        try:
            executor = WhatsAppNotificationExecutor(
                db,
                client_factory() if client_factory is not None else None,
                lease_seconds=worker_config.lease_seconds,
                max_attempts=worker_config.max_attempts,
            )
            now = resolve_now()
            try:
                result = executor.execute_claimed(
                    tenant_id=claim.tenant_id,
                    delivery_id=claim.delivery_id,
                    claim_token=claim.claim_token,
                    now=now,
                )
            except WhatsAppNotificationExecutionError as exc:
                logger.error(
                    "notification_worker_execution_error tenant_id=%s delivery_id=%s error_code=%s",
                    exc.tenant_id,
                    exc.delivery_id,
                    exc.code,
                )
                decision = _make_retry_policy(db, worker_config).apply_failure(
                    tenant_id=claim.tenant_id,
                    delivery_id=claim.delivery_id,
                    now=now,
                    error_code=exc.code,
                    retryable=False,
                    max_attempts=worker_config.max_attempts,
                    expected_claim_token=claim.claim_token,
                    allowed_current_statuses={"processing", "failed"},
                )
                counters["failed"] += 1
                _bump_decision_counter(counters, decision.action)
                continue

            if result.outcome == "sent":
                counters["sent"] += 1
            elif result.outcome == "cancelled":
                counters["cancelled"] += 1
            elif result.outcome == "manual_review":
                counters["manual_review"] += 1
            elif result.outcome in ("stale_claim_reconciled", "stale_claim_ignored"):
                pass
            elif result.outcome == "failed":
                counters["failed"] += 1
                decision = _make_retry_policy(db, worker_config).apply_failure(
                    tenant_id=claim.tenant_id,
                    delivery_id=claim.delivery_id,
                    now=now,
                    error_code=result.error_code or "whatsapp_provider_send_failed",
                    retryable=result.retryable if result.retryable is not None else True,
                    max_attempts=worker_config.max_attempts,
                    expected_claim_token=claim.claim_token,
                    allowed_current_statuses={"processing", "failed"},
                )
                _bump_decision_counter(counters, decision.action)
        except Exception as exc:  # noqa: BLE001 - one delivery must never stop the batch
            logger.error(
                "notification_worker_unexpected_error tenant_id=%s delivery_id=%s error_type=%s",
                claim.tenant_id,
                claim.delivery_id,
                type(exc).__name__,
            )
            counters["failed"] += 1
        finally:
            db.close()

    return counters


def _bump_decision_counter(counters: dict[str, int], action: str) -> None:
    if action == "retry":
        counters["retried"] += 1
    elif action == "dead_letter":
        counters["dead_lettered"] += 1
    elif action == "manual_review":
        counters["manual_review"] += 1


def run_once(
    *,
    worker_config: NotificationWorkerSettings,
    worker_id: str,
    session_factory: Callable[[], object] = SessionLocal,
    now_fn: Callable[[], datetime] | None = None,
    client_factory: Callable[[], object] | None = None,
) -> int:
    total_claimed = 0
    for batch_index in range(_MAX_ONCE_BATCHES):
        counters = run_cycle(
            worker_config=worker_config,
            session_factory=session_factory,
            now_fn=now_fn,
            run_recovery=(batch_index == 0),
            client_factory=client_factory,
        )
        total_claimed += counters["claimed"]
        if counters["claimed"] == 0:
            break
    logger.info("notification_worker_once_complete worker_id=%s claimed_total=%s", worker_id, total_claimed)
    return 0


def run_forever(
    *,
    worker_config: NotificationWorkerSettings,
    worker_id: str,
    session_factory: Callable[[], object] = SessionLocal,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    install_signals: bool = True,
    client_factory: Callable[[], object] | None = None,
    shutdown_flag: "_ShutdownFlag | None" = None,
) -> int:
    flag = shutdown_flag if shutdown_flag is not None else _ShutdownFlag()
    if install_signals:
        _install_signal_handlers(flag)

    resolve_now = now_fn or (lambda: datetime.now(timezone.utc))
    last_recovery_at: datetime | None = None

    while not flag.stop_requested:
        now = resolve_now()
        run_recovery = (
            last_recovery_at is None
            or (now - last_recovery_at).total_seconds() >= worker_config.recovery_interval_seconds
        )
        counters = run_cycle(
            worker_config=worker_config,
            session_factory=session_factory,
            now_fn=lambda: now,
            run_recovery=run_recovery,
            client_factory=client_factory,
        )
        if run_recovery:
            last_recovery_at = now
        if counters["claimed"] == 0 and not flag.stop_requested:
            sleep_fn(worker_config.poll_seconds)

    logger.info("notification_worker_stopped worker_id=%s", worker_id)
    return 0


def main(
    argv: list[str] | None = None,
    *,
    skip_postgresql_check: bool = False,
    session_factory: Callable[[], object] = SessionLocal,
    client_factory: Callable[[], object] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="notification_worker")
    parser.add_argument("--once", action="store_true", help="Drain the due-delivery queue once and exit")
    args = parser.parse_args(argv)

    try:
        worker_config = NotificationWorkerSettings.from_settings(settings)
    except NotificationWorkerConfigurationError:
        logger.error("notification_worker_configuration_error")
        return 1

    try:
        _require_postgresql(skip_check=skip_postgresql_check)
    except NotificationWorkerStartupError:
        logger.error("notification_worker_startup_error error_code=notification_worker_requires_postgresql")
        return 1

    worker_id = uuid.uuid4().hex[:12]
    logger.info("notification_worker_starting worker_id=%s once=%s", worker_id, args.once)

    if args.once:
        return run_once(
            worker_config=worker_config,
            worker_id=worker_id,
            session_factory=session_factory,
            client_factory=client_factory,
        )
    return run_forever(
        worker_config=worker_config,
        worker_id=worker_id,
        session_factory=session_factory,
        client_factory=client_factory,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
