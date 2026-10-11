"""Callback worker: places accepted public callbacks through Telephony.

For a canonical call (CRM provider ``livekit_sip``) the worker:

  claim (short transaction, committed)  ->  re-validate the EXACT AgentVersion of the call's
  ExperienceVersion  ->  TelephonyFacade.place_outbound_call (VoiceSession + realtime room +
  runtime-ready wait + SIP participant) driving the SAME CrmVoiceCall.

No row lock is held across any network operation, a failed canonical call is never retried on the
legacy provider runtime, and once a SIP attempt started it is never repeated (Telephony enforces it
from the session's persisted ``voice.sip.dial.started`` evidence).

Calls of the temporary legacy runtime (provider-originated) are handed, untouched, to the injected
legacy worker; they disappear with PR #137.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.orm import Session

from app.modules.crm.public import (
    VOICE_EXPERIENCE_CALLBACK_ORIGIN,
    CrmVoiceCalls,
    UpdateVoiceCallCommand,
    VoiceCallView,
)
from app.modules.telephony.public import (
    CANONICAL_SIP_PROVIDER,
    CapacityDeferred,
    CapacityFacade,
    PlaceOutboundCallCommand,
    SipRouteFacade,
    TelephonyFacade,
)
from app.modules.voice_experiences.application.callback_ledger import VoiceExperienceCallbackLedger
from app.modules.voice_experiences.application.launch_context import trusted_variables
from app.modules.voice_experiences.application.ports import VoiceRuntimePort
from app.modules.voice_experiences.domain.errors import VoiceRuntimeUnavailable
from app.modules.voice_experiences.infrastructure.experience_models import TenantVoiceExperienceVersion
from app.modules.voice_experiences.infrastructure.submission_models import TenantVoiceExperienceSubmission

logger = logging.getLogger(__name__)

CLAIM_BATCH_SIZE = 25
_SAFE_CODE = re.compile(r"^[a-z0-9_]{1,80}$")


class LegacyCallbackWorker(Protocol):
    """The temporary provider-originated runtime (synchronous)."""

    def process_once(self) -> bool: ...


class CallbackWorker:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        runtime_factory: Callable[[Session], VoiceRuntimePort],
        legacy: LegacyCallbackWorker,
        telephony_factory: Callable[[Session], TelephonyFacade] = TelephonyFacade,
        starting_lease_seconds: int = 120,
    ) -> None:
        self.session_factory = session_factory
        self.runtime_factory = runtime_factory
        self.legacy = legacy
        self.telephony_factory = telephony_factory
        self.starting_lease_seconds = starting_lease_seconds

    async def process_once(self) -> bool:
        self._recover_stale_starting()
        call_id = self._claim()
        if call_id is not None:
            return await self._place(call_id)
        # Nothing canonical to place: let the legacy runtime reconcile/claim its own calls.
        return await asyncio.to_thread(self.legacy.process_once)

    # -- claim / lease ----------------------------------------------------------------------------

    def _recover_stale_starting(self) -> None:
        """``starting`` = a worker owns the request but no SIP attempt is known. Returning it to
        ``requested`` is safe: Telephony resumes the same session and never repeats a dial that
        already started."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self.starting_lease_seconds)
        with self.session_factory() as db:
            with db.begin():
                recovered = CrmVoiceCalls(db).recover_stale_starting(
                    cutoff, provider=CANONICAL_SIP_PROVIDER, origin=VOICE_EXPERIENCE_CALLBACK_ORIGIN
                )
        if recovered:
            logger.warning("Recovered canonical callbacks stuck in starting", extra={"recovered_count": recovered})

    def _claim(self) -> str | None:
        with self.session_factory() as db:
            with db.begin():
                calls = CrmVoiceCalls(db)
                for call in calls.lock_requested_callbacks(
                    CLAIM_BATCH_SIZE, provider=CANONICAL_SIP_PROVIDER, origin=VOICE_EXPERIENCE_CALLBACK_ORIGIN
                ):
                    route = SipRouteFacade(db).lock_route(call.sip_route_id)
                    if route is None or route.status != "active":
                        calls.update(
                            call.id,
                            UpdateVoiceCallCommand(status="failed", error_message="Outbound SIP route is unavailable."),
                        )
                        return call.id
                    load = CapacityFacade(db).route_load(
                        tenant_id=call.tenant_id, route_id=route.id, exclude_call_id=call.id
                    )
                    if load >= route.max_concurrent_calls:
                        # Temporarily full: stays requested (an accepted callback is not lost) and
                        # must not starve other tenants' calls behind it.
                        continue
                    calls.update(
                        call.id,
                        UpdateVoiceCallCommand(status="starting", provider_attempt_started_at=datetime.now(UTC)),
                    )
                    return call.id
        return None

    # -- placement --------------------------------------------------------------------------------

    async def _place(self, call_id: str) -> bool:
        with self.session_factory() as db:
            call = CrmVoiceCalls(db).get(call_id)
            if call is None:
                return True
            if call.status != "starting":
                return True  # failed at claim (route unavailable) or moved on
            try:
                command = self._command(db, call)
            except VoiceRuntimeUnavailable:
                self._fail(db, call, "agent_unavailable")
                return True
            except LookupError:
                self._fail(db, call, "callback_provenance_unavailable")
                return True
            ledger = VoiceExperienceCallbackLedger(db, call.tenant_id, call.id)
            try:
                await self.telephony_factory(db).place_outbound_call(command, ledger)
            except CapacityDeferred:
                self._defer(call.id)
                return False
            except Exception as exc:  # noqa: BLE001 - boundary: any failure must leave the call terminal
                self._fail(db, call, self._code_of(exc))
                return True
        return True

    def _command(self, db: Session, call: VoiceCallView) -> PlaceOutboundCallCommand:
        """The call's exact target comes from its provenance (submission -> ExperienceVersion), never
        from the CRM provider fields and never from today's published agent. Missing provenance fails
        closed."""
        submission = (
            db.get(TenantVoiceExperienceSubmission, call.source_submission_id) if call.source_submission_id else None
        )
        if submission is None or submission.tenant_id != call.tenant_id:
            raise LookupError("submission")
        version = db.get(TenantVoiceExperienceVersion, submission.experience_version_id)
        if version is None or version.tenant_id != call.tenant_id:
            raise LookupError("experience_version")
        runtime = self.runtime_factory(db)
        # The agent may have changed since the request was accepted: re-check the exact version.
        runtime.require_runnable_agent(call.tenant_id, version.agent_id, version.agent_version_id)
        variables = trusted_variables(db, version, submission)
        runtime.validate_session_variables(dict(variables))
        return PlaceOutboundCallCommand(
            tenant_id=call.tenant_id,
            agent_id=version.agent_id,
            agent_version_id=version.agent_version_id,
            idempotency_key=f"voice-experience-callback:{submission.id}",
            to_phone=call.to_phone,
            variables=variables,
            defer_on_capacity=True,
        )

    # -- outcomes ---------------------------------------------------------------------------------

    @staticmethod
    def _code_of(exc: Exception) -> str:
        text = str(exc)
        return text if _SAFE_CODE.fullmatch(text) else "callback_failed"

    def _defer(self, call_id: str) -> None:
        with self.session_factory() as db:
            calls = CrmVoiceCalls(db)
            call = calls.get(call_id)
            if call is not None and call.status == "starting":
                calls.update(call_id, UpdateVoiceCallCommand(status="requested", provider_attempt_started_at=None))
                db.commit()

    def _fail(self, db: Session, call: VoiceCallView, code: str) -> None:
        db.rollback()
        calls = CrmVoiceCalls(db)
        current = calls.get(call.id)
        # Telephony already finalizes the call when the dial itself fails; only a call still open
        # here (failed before or outside the dial) needs closing.
        if current is not None and current.status in {"requested", "starting"}:
            calls.update(
                call.id,
                UpdateVoiceCallCommand(status="failed", error_message=code[:255], ended_at=datetime.now(UTC)),
            )
            db.commit()
        logger.warning(
            "Canonical callback failed",
            extra={"voice_call_id": call.id, "tenant_id": call.tenant_id, "error_code": code},
        )


async def run_forever(worker: CallbackWorker, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
    while True:
        try:
            if not await worker.process_once():
                await sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Voice callback worker iteration failed", extra={"error_type": type(exc).__name__})
            await sleep(2)
