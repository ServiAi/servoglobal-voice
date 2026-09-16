"""Reconcile existing SIP/WebRTC runtime sessions without automatic writes.

Usage: python -m scripts.backfill_voice_session_calls [--tenant-id ID] [--apply]
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.analytics import Call
from app.models.crm import CrmVoiceCall
from app.models.voice_sessions import VoiceSession, VoiceSessionEvent
from app.services.voice_call_projection_service import REAL_EVENTS, VoiceCallProjectionService


def run(*, tenant_id: str | None, batch_size: int, apply: bool) -> int:
    counts = {"eligible": 0, "existing": 0, "created": 0, "reconciled": 0, "skipped": 0, "errors": 0}
    cursor = ""
    with SessionLocal() as db:
        while True:
            query = select(VoiceSession.id).where(
                VoiceSession.id > cursor,
                VoiceSession.channel.in_(("sip", "webrtc")),
            ).order_by(VoiceSession.id).limit(batch_size)
            if tenant_id:
                query = query.where(VoiceSession.tenant_id == tenant_id)
            ids = list(db.scalars(query).all())
            if not ids:
                break
            for session_id in ids:
                cursor = session_id
                session = db.get(VoiceSession, session_id)
                crm_call = db.scalar(select(CrmVoiceCall).where(
                    CrmVoiceCall.id == session.crm_voice_call_id,
                    CrmVoiceCall.tenant_id == session.tenant_id,
                )) if session.crm_voice_call_id else None
                real = bool(crm_call and (crm_call.started_at or crm_call.provider_attempt_started_at
                                          or crm_call.answered_at or session.sip_call_id)) or db.scalar(select(VoiceSessionEvent.id).where(
                    VoiceSessionEvent.voice_session_id == session.id,
                    VoiceSessionEvent.tenant_id == session.tenant_id,
                    VoiceSessionEvent.event_type.in_(REAL_EVENTS),
                ).limit(1)) is not None
                if not real:
                    counts["skipped"] += 1
                    continue
                counts["eligible"] += 1
                existing = db.scalar(select(Call.id).where(
                    Call.tenant_id == session.tenant_id,
                    Call.external_call_id == f"voice-session:{session.id}",
                )) is not None
                counts["existing"] += int(existing)
                if not apply:
                    continue
                try:
                    VoiceCallProjectionService(db).reconcile_session(session.id, tenant_id=session.tenant_id)
                    counts["reconciled" if existing else "created"] += 1
                except Exception as exc:
                    db.rollback()
                    counts["errors"] += 1
                    print(f"Projection failed for voice_session_id={session.id}: {type(exc).__name__}", file=sys.stderr)
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
