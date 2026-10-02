"""Reconcile existing SIP/WebRTC runtime sessions without automatic writes.

Usage: python -m scripts.backfill_voice_session_calls [--tenant-id ID] [--apply]

Works through public module APIs only: Voice lists the candidate sessions and
Analytics decides whether a session is a real call and projects it.
"""

from __future__ import annotations

import argparse
import sys

from app.db.session import SessionLocal
from app.modules.analytics.public import VoiceCallProjectionFacade
from app.modules.voice.public import VoiceSessionFacade


def run(*, tenant_id: str | None, batch_size: int, apply: bool) -> int:
    counts = {"eligible": 0, "existing": 0, "created": 0, "reconciled": 0, "skipped": 0, "errors": 0}
    cursor = ""
    with SessionLocal() as db:
        voice = VoiceSessionFacade(db)
        projection = VoiceCallProjectionFacade(db)
        while True:
            page = voice.list_projection_candidates(after_id=cursor, limit=batch_size, tenant_id=tenant_id)
            if not page:
                break
            for session_id, session_tenant_id in page:
                cursor = session_id
                if not projection.is_real_call(session_id, session_tenant_id):
                    counts["skipped"] += 1
                    continue
                counts["eligible"] += 1
                existing = projection.projection_exists(session_id, session_tenant_id)
                counts["existing"] += int(existing)
                if not apply:
                    continue
                try:
                    projection.reconcile(session_id, session_tenant_id)
                    counts["reconciled" if existing else "created"] += 1
                except Exception as exc:
                    db.rollback()
                    counts["errors"] += 1
                    print(f"Projection failed for voice_session_id={session_id}: {type(exc).__name__}", file=sys.stderr)
            db.expire_all()
    print(f"mode={'apply' if apply else 'dry-run'} " + " ".join(f"{key}={value}" for key, value in counts.items()))
    return 1 if counts["errors"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", help="Restrict processing to one tenant")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--apply", action="store_true", help="Write projections; otherwise preview only")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 1000:
        parser.error("--batch-size must be between 1 and 1000")
    return run(tenant_id=args.tenant_id, batch_size=args.batch_size, apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
