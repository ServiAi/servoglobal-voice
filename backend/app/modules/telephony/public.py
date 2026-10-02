"""Telephony -- public API (the telephone transport of the platform).

SIP routes (PBX + LiveKit trunk), phone-number rules, capacity policy,
Asterisk provisioning and SIP dialing. Telephony never owns a VoiceSession,
a CRM record or a voice provider: it asks Voice (voice.public), reads CRM
only through the caller's ledger / crm.public counts, and projects calls
through analytics.public.

Top-level imports are pure domain (phone rules, DTOs, errors); every use case
loads lazily, so importing this module is cheap and safe from any other
module (e.g. Voice's context resolution needs ``normalize_caller_id``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.modules.telephony.domain.capacity import (
    ACTIVE_CALLBACK_STATUSES,
    CAPACITY_EVENT_TYPES,
    VOICE_CALLBACK_FORCED_RELEASE,
    VOICE_CALLBACK_RECONCILED,
    VOICE_CAPACITY_REACHED,
)
from app.modules.telephony.domain.errors import SipDialError
from app.modules.telephony.domain.phone_numbers import (
    SUPPORTED_OUTBOUND_COUNTRIES,
    NormalizedVoicePhone,
    VoicePhoneValidationError,
    normalize_caller_id,
    normalize_outbound_phone,
)
from app.modules.telephony.domain.routes import sip_username_for_route
from app.modules.telephony.domain.views import (
    OutboundCallResult,
    PlaceOutboundCallCommand,
    SipRouteConnection,
    SipRouteSettings,
    SipRouteView,
)

if TYPE_CHECKING:
    from app.modules.telephony.application.ports import (
        OutboundCallLedger,
        TelephonyPorts,
    )
    from app.modules.voice_providers.public import ProviderConfigRef

__all__ = [
    "ACTIVE_CALLBACK_STATUSES",
    "CAPACITY_EVENT_TYPES",
    "SUPPORTED_OUTBOUND_COUNTRIES",
    "VOICE_CALLBACK_FORCED_RELEASE",
    "VOICE_CALLBACK_RECONCILED",
    "VOICE_CAPACITY_REACHED",
    "CapacityFacade",
    "NormalizedVoicePhone",
    "OutboundCallResult",
    "PlaceOutboundCallCommand",
    "SipDialError",
    "SipRouteConnection",
    "SipRouteFacade",
    "SipRouteSettings",
    "SipRouteView",
    "TelephonyFacade",
    "VoicePhoneValidationError",
    "normalize_caller_id",
    "normalize_outbound_phone",
    "run_asterisk_provisioner_agent",
    "sip_username_for_route",
]


class SipRouteFacade:
    """A tenant's SIP route, as DTOs. The SIP password never appears in a
    view; ``get_connection`` is the single, explicit exception, for the
    trusted legacy process that actually places the provider call."""

    def __init__(self, db: Session, secret_manager=None) -> None:
        self.db = db
        self._secret_manager = secret_manager

    def _routes(self):
        from app.modules.telephony.application.route_service import SipRouteService

        return SipRouteService(self.db, self._secret_manager)

    def get_route(self, tenant_id: str) -> SipRouteView | None:
        routes = self._routes()
        return routes.view(routes.get_route(tenant_id))

    def get_active_route(
        self, tenant_id: str, *, for_update: bool = False, require_livekit: bool = False
    ) -> SipRouteView:
        """Raises ValueError (user-facing messages) when the route is missing,
        inactive, without password or not yet provisioned."""
        routes = self._routes()
        return routes.view(routes.get_active_route(tenant_id, for_update=for_update, require_livekit=require_livekit))

    def lock_route(self, route_id: str) -> SipRouteView | None:
        """SELECT ... FOR UPDATE by id, for the caller's transaction."""
        routes = self._routes()
        return routes.view(routes.get_route_by_id(route_id, for_update=True))

    def get_connection(self, tenant_id: str) -> SipRouteConnection:
        """The tenant's active route with its decrypted SIP password. Same
        validations as get_active_route."""
        routes = self._routes()
        return routes.connection(routes.get_active_route(tenant_id))

    def upsert(
        self, tenant_id: str, provider_config: ProviderConfigRef, settings: SipRouteSettings
    ) -> SipRouteView:
        """Creates/updates the tenant's route (flush, no commit). Raises
        ValueError on invalid settings."""
        routes = self._routes()
        return routes.view(routes.upsert(tenant_id, provider_config, settings))

    async def sync_livekit_trunk(self, tenant_id: str, *, sip_service=None) -> None:
        """Provisions the LiveKit outbound trunk of an active route, or removes
        a stale one. Raises ValueError when LiveKit provisioning fails."""
        await self._routes().sync_livekit_trunk(tenant_id, sip_service)


class CapacityFacade:
    """Channel-capacity policy of a route, for the legacy callback flow and
    capacity reporting."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _service(self):
        from app.modules.crm.public import CrmFacade
        from app.modules.telephony.application.capacity_service import CapacityService

        return CapacityService(self.db, CrmFacade(self.db))

    def callbacks_in_flight(self, *, tenant_id: str, route_id: str) -> int:
        return self._service().callbacks_in_flight(tenant_id=tenant_id, route_id=route_id)

    def record_capacity_reached(
        self, *, tenant_id: str, route_id: str, active_calls: int, max_concurrent_calls: int
    ) -> None:
        self._service().record_capacity_reached(
            tenant_id=tenant_id,
            route_id=route_id,
            active_calls=active_calls,
            max_concurrent_calls=max_concurrent_calls,
        )

    def record_release(
        self, *, tenant_id: str, call_id: str, prior_status: str, resulting_status: str, forced: bool
    ) -> None:
        self._service().record_release(
            tenant_id=tenant_id,
            call_id=call_id,
            prior_status=prior_status,
            resulting_status=resulting_status,
            forced=forced,
        )


class TelephonyFacade:
    """Placing calls. ``ports`` are a test seam; by default Telephony binds
    Voice, CRM counts, the projection and LiveKit SIP itself."""

    def __init__(self, db: Session, ports: TelephonyPorts | None = None) -> None:
        self.db = db
        self._ports = ports

    def _bound(self):
        if self._ports is not None:
            return self._ports
        from app.modules.telephony.wiring import default_telephony_ports

        return default_telephony_ports(self.db)

    async def place_outbound_call(
        self, command: PlaceOutboundCallCommand, ledger: OutboundCallLedger
    ) -> OutboundCallResult:
        """Production outbound call: session, route, capacity, runtime and SIP
        dial, driving the caller's ledger for its own call record.
        Idempotent per (tenant, idempotency_key). Raises ValueError with the
        user-facing reason."""
        from app.modules.telephony.application.outbound_service import (
            OutboundCallService,
        )

        return await OutboundCallService(self.db, self._bound()).place_outbound_call(command, ledger)

    async def dial_qa_session(self, session_id: str, tenant_id: str, to_phone: str) -> None:
        """Dials an already-created SIP QA session through the tenant's route
        (capacity, dispatch, agent-ready wait and participant are Telephony's
        job; the session stays Voice's). Raises SipDialError."""
        from app.modules.telephony.application.dial_service import TelephonyDialService
        from app.modules.telephony.application.route_service import SipRouteService

        ports = self._bound()
        await TelephonyDialService(self.db, SipRouteService(self.db), ports.voice, ports.sip).dial(
            session_id, tenant_id, to_phone
        )


def run_asterisk_provisioner_agent() -> None:
    """Runs the PBX-side Asterisk provisioning agent (blocking). Process
    entrypoints may also import the agent module directly to stay free of
    this package's dependencies."""
    from app.modules.telephony.infrastructure.asterisk_agent import main

    main()
