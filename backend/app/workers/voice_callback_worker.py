from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.db.session import SessionLocal
from app.modules.voice_experiences.public import create_callback_worker, run_callback_worker

logger = logging.getLogger(__name__)


async def amain() -> None:
    worker = create_callback_worker(
        SessionLocal,
        starting_lease_seconds=settings.VOICE_CALLBACK_STARTING_LEASE_SECONDS,
        reconcile_after_seconds=settings.VOICE_CALLBACK_RECONCILE_AFTER_SECONDS,
        max_active_seconds=settings.VOICE_CALLBACK_MAX_ACTIVE_SECONDS,
    )
    logger.info("Voice callback worker started")
    await run_callback_worker(worker)


def main() -> None:
    try:
        asyncio.run(amain())  # one event loop for the worker's whole life
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
