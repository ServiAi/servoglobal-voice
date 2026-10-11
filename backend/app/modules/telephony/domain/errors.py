from __future__ import annotations

from app.modules.telephony.domain.phone_numbers import VoicePhoneValidationError

__all__ = ["CapacityDeferred", "SipDialError", "VoicePhoneValidationError"]


class SipDialError(ValueError):
    """A SIP dial that could not complete. ``code`` is stable and safe to
    show (e.g. ``telephony_capacity_exceeded``, ``runtime_not_ready``,
    ``livekit_sip_busy``); ``call_status`` is the telephony outcome the
    caller maps onto its own call record (busy/rejected/no_answer/failed/
    cancelled)."""

    def __init__(self, code: str, call_status: str = "failed") -> None:
        super().__init__(code)
        self.code = code
        self.call_status = call_status


class CapacityDeferred(ValueError):
    """The route is temporarily full and the caller asked to be told instead of failing the
    call (``PlaceOutboundCallCommand.defer_on_capacity``): nothing was dialed and the session,
    if any, stays ``requested`` so the same request can be retried later."""

    code = "telephony_capacity_deferred"

    def __init__(self) -> None:
        super().__init__(self.code)
