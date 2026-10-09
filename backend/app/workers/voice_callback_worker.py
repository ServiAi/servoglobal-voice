from __future__ import annotations

import logging
import time

from app.core.config import settings
from app.db.session import SessionLocal
from app.modules.voice_experiences.public import create_callback_worker


logger = logging.getLogger(__name__)


def main() -> None:
    worker = create_callback_worker(
        SessionLocal,
        starting_lease_seconds=settings.VOICE_CALLBACK_STARTING_LEASE_SECONDS, 
        reconcile_after_seconds=settings.VOICE_CALLBACK_RECONCILE_AFTER_SECONDS,
        max_active_seconds=settings.VOICE_CALLBACK_MAX_ACTIVE_SECONDS,
    )
    logger.info("Voice callback worker started")
    while True:
        try:
            if not worker.process_once():
                time.sleep(2)
        except KeyboardInterrupt:
            return
        except Exception as exc:
            logger.error(
                "Voice callback worker iteration failed",
                extra={"error_type": type(exc).__name__},
            )
            time.sleep(2)


if __name__ == "__main__":
    main()
