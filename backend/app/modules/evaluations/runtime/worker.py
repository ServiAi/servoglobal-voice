from __future__ import annotations

import argparse
import logging
import signal
import time
from datetime import datetime, timezone

from app.db.session import SessionLocal, engine
from app.modules.evaluations.application.execute_evaluation import EvaluationExecutor

logger = logging.getLogger(__name__)
_BATCH_SIZE = 25
_LEASE_SECONDS = 60
_POLL_SECONDS = 1


def run_cycle(*, session_factory=SessionLocal, now_fn=None) -> dict[str, int]:
    now = now_fn or (lambda: datetime.now(timezone.utc))
    claim_db = session_factory()
    try:
        claims = EvaluationExecutor(_repository(claim_db)).claim_batch(
            now=now(), lease_seconds=_LEASE_SECONDS, batch_size=_BATCH_SIZE
        )
    finally:
        claim_db.close()
    completed = failed = stale = 0
    for claim in claims:
        db = session_factory()
        try:
            if EvaluationExecutor(_repository(db)).execute(claim, now=now()):
                completed += 1
            else:
                stale += 1
        except Exception as exc:  # safe code only; never log evidence or exception text
            logger.error(
                "evaluation_worker_unexpected_error tenant_id=%s run_id=%s error_type=%s",
                claim["tenant_id"], claim["run_id"], type(exc).__name__,
            )
            failed += 1
        finally:
            db.close()
    return {"claimed": len(claims), "completed": completed, "failed": failed, "claim_lost": stale}


def run_once(*, session_factory=SessionLocal, now_fn=None) -> dict[str, int]:
    return run_cycle(session_factory=session_factory, now_fn=now_fn)


def _repository(db):
    from app.modules.evaluations.infrastructure.repositories import EvaluationRepository

    return EvaluationRepository(db)


def run_forever(*, session_factory=SessionLocal, sleep_fn=time.sleep, stop_flag=None) -> None:
    stopped = stop_flag if stop_flag is not None else {"value": False}
    previous_term = signal.getsignal(signal.SIGTERM)
    previous_int = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGTERM, lambda *_: stopped.__setitem__("value", True))
    signal.signal(signal.SIGINT, lambda *_: stopped.__setitem__("value", True))
    try:
        while not stopped["value"]:
            stats = run_cycle(session_factory=session_factory)
            if stats["claimed"] == 0:
                sleep_fn(_POLL_SECONDS)
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)


def main(argv: list[str] | None = None, *, session_factory=SessionLocal) -> int:
    parser = argparse.ArgumentParser(prog="evaluation_worker")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if engine.dialect.name != "postgresql":
        logger.error("evaluation_worker_requires_postgresql")
        return 1
    if args.once:
        run_once(session_factory=session_factory)
    else:
        run_forever(session_factory=session_factory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
