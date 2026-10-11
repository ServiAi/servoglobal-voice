"""Late billing of HISTORICAL provider-originated public calls.

Before PR #135 a public WebRTC call was started against the AI provider directly and the provider
reported its billing later (``call.billed``). Those calls are over -- the runtime that placed them is
gone and the drain gate treats a terminal one as drained -- but the provider may still deliver the
billing event afterwards. This component only *settles* that event into Analytics:

  receive (already signature-verified) -> prove the call is a historical provider launch -> dedup ->
  persist ``billed_minutes`` partially.

It is not a runtime: it never creates a call record, a session or a room, never places a call,
never contacts the provider, never retries, and never changes the lifecycle of the CRM call or of the
runtime ledger row. A call that has a session is never historical.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.analytics.public import AnalyticsCallLedger, PersistCallCommand, PersistCallEventCommand
from app.modules.crm.public import CrmVoiceCalls
from app.modules.voice_experiences.domain.limits import LAUNCH_RUNTIME_LEGACY
from app.modules.voice_experiences.infrastructure.submission_models import TenantVoiceRuntimeCall

BILLED_EVENT = "call.billed"


class HistoricalProviderCallSettlement:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _legacy_runtime(self, crm_call_id: str) -> TenantVoiceRuntimeCall | None:
        runtime = self.db.scalar(
            select(TenantVoiceRuntimeCall).where(TenantVoiceRuntimeCall.crm_voice_call_id == crm_call_id)
        )
        if runtime is None or runtime.launch_runtime != LAUNCH_RUNTIME_LEGACY or runtime.voice_session_id is not None:
            return None
        return runtime

    def owns(self, crm_call_id: str) -> bool:
        """True only for a persisted historical provider launch (never inferred from provider/status)."""
        return self._legacy_runtime(crm_call_id) is not None

    def settle_billed(
        self,
        *,
        crm_call_id: str,
        provider: str,
        provider_call_id: str,
        billed_minutes: Decimal | None,
        provider_status: str | None = None,
        provider_agent_id: str | None = None,
    ) -> dict[str, object]:
        dedup_key = f"{provider}:{provider_call_id}:{BILLED_EVENT}"
        now = datetime.now(UTC)
        self.db.rollback()
        with self.db.begin():
            calls = CrmVoiceCalls(self.db)
            call = calls.get(crm_call_id)
            runtime = self._legacy_runtime(crm_call_id)
            if call is None or runtime is None or call.tenant_id != runtime.tenant_id:
                return {"status": "ignored", "processed": False}
            claimed = calls.claim_event(
                tenant_id=runtime.tenant_id,
                voice_call_id=call.id,
                provider=provider,
                event_type=BILLED_EVENT,
                status="success",
                dedup_key=dedup_key,
                payload_summary={"event_type": BILLED_EVENT},
                created_at=now,
            )
            if not claimed:
                return {"status": "processed", "processed": False, "voice_call_id": call.id, "call_status": call.status}
            ledger = AnalyticsCallLedger(self.db)
            analytics = ledger.persist_call(
                PersistCallCommand(
                    tenant_id=runtime.tenant_id,
                    external_provider=provider,
                    external_call_id=provider_call_id,
                    provider_status=provider_status or BILLED_EVENT,
                    provider_agent_id=provider_agent_id,
                    billed_minutes=billed_minutes,
                    normalized_status="answered" if runtime.connected_at else "unanswered",
                    partial_update=True,
                    status_policy="settle_open",
                ),
                commit=False,
            )
            ledger.claim_event(
                PersistCallEventCommand(
                    tenant_id=runtime.tenant_id,
                    call_id=analytics.id,
                    event_type=BILLED_EVENT,
                    payload_json={"event_type": BILLED_EVENT},
                    dedup_key=dedup_key,
                    received_at=now,
                ),
                commit=False,
            )
            return {"status": "processed", "processed": True, "voice_call_id": call.id, "call_status": call.status}
