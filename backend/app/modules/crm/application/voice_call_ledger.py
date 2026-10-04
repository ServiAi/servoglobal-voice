"""CRM's ledger of voice calls (``crm_voice_calls`` / ``crm_voice_call_events``).

CRM is the only writer of these tables. Other modules (Voice Legacy webhooks and
workers, Telephony, public experience calls) drive them through this class via
``crm.public``. Every operation runs on the *caller's* session and NEVER commits:
the caller owns the transaction (several callers claim an event, update the call,
project Analytics and update their own state atomically).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.modules.crm.domain.views import VoiceCallView
from app.modules.crm.infrastructure.models import CrmVoiceCall, CrmVoiceCallEvent

# Columns a caller may change on a call (identity, tenant and links are not).
_UPDATABLE = frozenset(
    {
        "lead_id", "contact_id", "sip_route_id", "provider", "provider_call_id", "provider_session_id",
        "provider_agent_id", "to_phone", "from_number", "status", "error_message", "recording_url",
        "transcript_url", "summary", "started_at", "provider_attempt_started_at", "answered_at",
        "ended_at", "duration_seconds", "updated_at",
    }
)
_CREATABLE = _UPDATABLE | {"id", "tenant_id", "source_submission_id", "direction"}


def view_of(row: CrmVoiceCall) -> VoiceCallView:
    return VoiceCallView(
        id=row.id,
        tenant_id=row.tenant_id,
        lead_id=row.lead_id,
        contact_id=row.contact_id,
        source_submission_id=row.source_submission_id,
        sip_route_id=row.sip_route_id,
        provider=row.provider,
        provider_call_id=row.provider_call_id,
        provider_session_id=row.provider_session_id,
        provider_agent_id=row.provider_agent_id,
        direction=row.direction,
        to_phone=row.to_phone,
        from_number=row.from_number,
        status=row.status,
        error_message=row.error_message,
        recording_url=row.recording_url,
        transcript_url=row.transcript_url,
        summary=row.summary,
        started_at=row.started_at,
        provider_attempt_started_at=row.provider_attempt_started_at,
        answered_at=row.answered_at,
        ended_at=row.ended_at,
        duration_seconds=row.duration_seconds,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _opt(row: CrmVoiceCall | None) -> VoiceCallView | None:
    return view_of(row) if row is not None else None


class VoiceCallLedger:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- reads -----------------------------------------------------------------
    def get(self, call_id: str, *, for_update: bool = False) -> VoiceCallView | None:
        if for_update:
            row = self.db.scalar(select(CrmVoiceCall).where(CrmVoiceCall.id == call_id).with_for_update())
        else:
            row = self.db.get(CrmVoiceCall, call_id)
        return _opt(row)

    def find_by_provider_call_id(self, provider_call_id: str) -> VoiceCallView | None:
        return _opt(self.db.scalar(select(CrmVoiceCall).where(CrmVoiceCall.provider_call_id == provider_call_id)))

    def find_by_provider_session_id(self, provider_session_id: str) -> VoiceCallView | None:
        return _opt(self.db.scalar(select(CrmVoiceCall).where(CrmVoiceCall.provider_session_id == provider_session_id)))

    def find_by_source_submission(self, submission_id: str, *, for_update: bool = False) -> VoiceCallView | None:
        stmt = select(CrmVoiceCall).where(CrmVoiceCall.source_submission_id == submission_id)
        return _opt(self.db.scalar(stmt.with_for_update() if for_update else stmt))

    def list_for_lead(self, tenant_id: str, lead_id: str) -> list[VoiceCallView]:
        rows = self.db.scalars(
            select(CrmVoiceCall)
            .where(CrmVoiceCall.tenant_id == tenant_id, CrmVoiceCall.lead_id == lead_id)
            .order_by(CrmVoiceCall.created_at.desc())
        ).all()
        return [view_of(row) for row in rows]

    def count_in_statuses(self, tenant_id: str, route_id: str, statuses: Sequence[str]) -> int:
        from sqlalchemy import func

        return int(
            self.db.scalar(
                select(func.count(CrmVoiceCall.id)).where(
                    CrmVoiceCall.tenant_id == tenant_id,
                    CrmVoiceCall.sip_route_id == route_id,
                    CrmVoiceCall.status.in_(tuple(statuses)),
                )
            )
            or 0
        )

    # -- writes (no commit) ------------------------------------------------------------
    def create(self, *, flush: bool = False, **fields: Any) -> VoiceCallView:
        unknown = set(fields) - _CREATABLE
        if unknown:
            raise ValueError(f"Unsupported voice call fields: {sorted(unknown)}")
        row = CrmVoiceCall(**fields)
        self.db.add(row)
        if flush or "id" not in fields:
            self.db.flush()
        return view_of(row)

    def update(self, call_id: str, **changes: Any) -> VoiceCallView:
        unknown = set(changes) - _UPDATABLE
        if unknown:
            raise ValueError(f"Unsupported voice call fields: {sorted(unknown)}")
        row = self.db.get(CrmVoiceCall, call_id)
        if row is None:
            raise ValueError("Voice call not found.")
        for key, value in changes.items():
            setattr(row, key, value)
        return view_of(row)

    def refresh(self, call_id: str) -> VoiceCallView:
        row = self.db.get(CrmVoiceCall, call_id)
        if row is None:
            raise ValueError("Voice call not found.")
        self.db.refresh(row)
        return view_of(row)

    # -- worker claims -------------------------------------------------------------
    def lock_stale_active(self, statuses: Sequence[str], updated_before: datetime) -> VoiceCallView | None:
        """The oldest call with a provider id whose state has not moved since
        ``updated_before`` (``FOR UPDATE SKIP LOCKED``): a reconciliation candidate."""
        row = self.db.scalar(
            select(CrmVoiceCall)
            .where(
                CrmVoiceCall.status.in_(tuple(statuses)),
                CrmVoiceCall.provider_call_id.is_not(None),
                CrmVoiceCall.updated_at < updated_before,
            )
            .order_by(CrmVoiceCall.updated_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        return _opt(row)

    def recover_stale_starting(self, attempt_started_before: datetime) -> int:
        """``starting`` calls whose provider attempt lease expired go back to ``requested``."""
        result = self.db.execute(
            update(CrmVoiceCall)
            .where(
                CrmVoiceCall.status == "starting",
                CrmVoiceCall.provider_attempt_started_at.is_not(None),
                CrmVoiceCall.provider_attempt_started_at < attempt_started_before,
            )
            .values(status="requested", provider_attempt_started_at=None)
        )
        return int(result.rowcount or 0)

    def lock_requested_callbacks(self, limit: int) -> list[VoiceCallView]:
        """Oldest ``requested`` outbound callbacks with a route, locked
        (``FOR UPDATE SKIP LOCKED``) for the claiming transaction."""
        rows = self.db.scalars(
            select(CrmVoiceCall)
            .where(
                CrmVoiceCall.status == "requested",
                CrmVoiceCall.direction == "outbound",
                CrmVoiceCall.source_submission_id.is_not(None),
                CrmVoiceCall.sip_route_id.is_not(None),
            )
            .order_by(CrmVoiceCall.created_at)
            .with_for_update(skip_locked=True)
            .limit(limit)
        ).all()
        return [view_of(row) for row in rows]

    # -- events ------------------------------------------------------------------
    def add_event(
        self, *, tenant_id: str, voice_call_id: str, provider: str, event_type: str, status: str,
        payload_summary: dict[str, Any],
    ) -> None:
        self.db.add(
            CrmVoiceCallEvent(
                tenant_id=tenant_id,
                voice_call_id=voice_call_id,
                provider=provider,
                event_type=event_type,
                status=status,
                payload_summary_json=payload_summary,
            )
        )
        self.db.flush()

    def claim_event(
        self, *, tenant_id: str, voice_call_id: str, provider: str, event_type: str, status: str,
        dedup_key: str, payload_summary: dict[str, Any], created_at: datetime,
    ) -> bool:
        """Insert the event once per ``dedup_key`` (``ON CONFLICT DO NOTHING``).
        True when this caller won the claim, False for a repeated event."""
        insert = sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
        claimed = self.db.execute(
            insert(CrmVoiceCallEvent)
            .values(
                tenant_id=tenant_id,
                voice_call_id=voice_call_id,
                provider=provider,
                event_type=event_type,
                status=status,
                dedup_key=dedup_key,
                payload_summary_json=payload_summary,
                created_at=created_at,
            )
            .on_conflict_do_nothing(index_elements=["dedup_key"])
            .returning(CrmVoiceCallEvent.id)
        ).scalar_one_or_none()
        return claimed is not None
