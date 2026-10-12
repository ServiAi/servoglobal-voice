"""Contracts for other bounded contexts. Framework-free: no ORM, FastAPI or Pydantic."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from app.modules.voice_experiences.domain.errors import HistoricalSettlementOwnershipError
from app.modules.voice_experiences.domain.ports import DatabaseSession, SessionFactory
from app.modules.voice_experiences.domain.views import (
    VoiceContextFieldSnapshot,
    VoiceContextOptionSnapshot,
    VoiceContextSchemaSnapshot,
)


class VoiceContextSchemaReader(Protocol):
    def get_schema_snapshot(
        self, tenant_id: str, schema_id: str
    ) -> VoiceContextSchemaSnapshot | None: ...


class VoiceAgentReferenceReader(Protocol):
    def is_agent_referenced(self, tenant_id: str, agent_id: str) -> bool:
        """True while any Experience or Experience version points at the Agent."""
        ...


class HistoricalCallSettlementPort(Protocol):
    """Late billing of calls that a provider-originated runtime placed before PR #135."""

    def owns(self, crm_call_id: str) -> bool: ...

    def settle_billed(
        self,
        *,
        crm_call_id: str,
        provider: str,
        provider_call_id: str,
        billed_minutes: Decimal | None,
        provider_status: str | None = None,
        provider_agent_id: str | None = None,
    ) -> dict[str, object]: ...


class VoiceCallbackWorkerPort(Protocol):
    async def process_once(self) -> bool: ...


def create_context_schema_reader(session: DatabaseSession) -> VoiceContextSchemaReader:
    """Resolve the DB adapter lazily so importing this module stays lightweight."""
    from app.modules.voice_experiences.wiring import create_context_schema_reader as create

    return create(session)


def create_agent_reference_reader(session: DatabaseSession) -> VoiceAgentReferenceReader:
    from app.modules.voice_experiences.wiring import create_agent_reference_reader as create

    return create(session)


def register_models() -> None:
    """Register ORM mappings from the application composition root."""
    from app.modules.voice_experiences.infrastructure import models  # noqa: F401


def create_historical_call_settlement(session: DatabaseSession) -> HistoricalCallSettlementPort:
    from app.modules.voice_experiences.wiring import create_historical_call_settlement as create

    return create(session)


async def run_callback_worker(worker: VoiceCallbackWorkerPort) -> None:
    """Runs the worker until cancelled, on the caller's event loop."""
    from app.modules.voice_experiences.application.callback_worker import run_forever

    await run_forever(worker)


def create_callback_worker(
    session_factory: SessionFactory,
    *,
    starting_lease_seconds: int,
) -> VoiceCallbackWorkerPort:
    from app.modules.voice_experiences.wiring import create_callback_worker as create

    return create(session_factory, starting_lease_seconds=starting_lease_seconds)


__all__ = [
    "DatabaseSession",
    "HistoricalCallSettlementPort",
    "HistoricalSettlementOwnershipError",
    "SessionFactory",
    "VoiceAgentReferenceReader",
    "VoiceCallbackWorkerPort",
    "VoiceContextFieldSnapshot",
    "VoiceContextOptionSnapshot",
    "VoiceContextSchemaReader",
    "VoiceContextSchemaSnapshot",
    "create_agent_reference_reader",
    "create_callback_worker",
    "create_context_schema_reader",
    "create_historical_call_settlement",
    "register_models",
    "run_callback_worker",
]
