"""Composition root of Telephony: binds its ports to other modules' public
APIs and to the LiveKit SIP transport. The only file in app.modules.telephony
allowed to know which concrete module serves each port."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.analytics.public import VoiceCallProjectionFacade
from app.modules.crm.public import CrmFacade
from app.modules.telephony.application.ports import SipTransportPort, TelephonyPorts
from app.modules.telephony.infrastructure.livekit_sip import LiveKitSipService
from app.modules.voice.public import VoiceTelephonyFacade


def default_telephony_ports(
    db: Session,
    *,
    sip_transport: SipTransportPort | None = None,
    runtime_backend=None,
) -> TelephonyPorts:
    """``sip_transport`` / ``runtime_backend`` are test seams for the two
    external transports (LiveKit SIP and the voice runtime's LiveKit room)."""
    return TelephonyPorts(
        voice=VoiceTelephonyFacade(db, runtime_backend=runtime_backend),
        sip=sip_transport or LiveKitSipService(),
        call_load=CrmFacade(db),
        projection=VoiceCallProjectionFacade(db),
    )
