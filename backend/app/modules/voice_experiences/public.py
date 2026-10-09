"""Contracts for other bounded contexts. Framework-free: no ORM, FastAPI or Pydantic."""

from __future__ import annotations

from typing import Protocol

from app.modules.voice_experiences.domain.ports import DatabaseSession, SessionFactory
from app.modules.voice_experiences.domain.views import (
    VoiceContextFieldSnapshot,
    VoiceContextOptionSnapshot,
    VoiceContextSchemaSnapshot,
    VoiceRuntimeWebhookTarget,
)


class VoiceContextSchemaReader(Protocol):
    def get_schema_snapshot(
        self, tenant_id: str, schema_id: str
    ) -> VoiceContextSchemaSnapshot | None: ...


class VoiceRuntimeWebhookServicePort(Protocol):
    def resolve_target(
        self, provider: str, payload: dict[str, object]
    ) -> VoiceRuntimeWebhookTarget | None: ...

    def runtime_secret(self, target: VoiceRuntimeWebhookTarget) -> str: ...

    def process(
        self, provider: str, payload: dict[str, object], target: VoiceRuntimeWebhookTarget
    ) -> dict[str, object]: ...


class VoiceCallbackWorkerPort(Protocol):
    def process_once(self) -> bool: ...


def create_context_schema_reader(session: DatabaseSession) -> VoiceContextSchemaReader:
    """Resolve the DB adapter lazily so importing this module stays lightweight."""
    from app.modules.voice_experiences.wiring import create_context_schema_reader as create

    return create(session)


def register_models() -> None:
    """Register ORM mappings from the application composition root."""
    from app.modules.voice_experiences.infrastructure import models  # noqa: F401


def create_runtime_webhook_service(session: DatabaseSession) -> VoiceRuntimeWebhookServicePort:
    from app.modules.voice_experiences.wiring import create_runtime_webhook_service as create

    return create(session)


def create_callback_worker(
    session_factory: SessionFactory,
    *,
    starting_lease_seconds: int,
    reconcile_after_seconds: int,
    max_active_seconds: int,
) -> VoiceCallbackWorkerPort:
    from app.modules.voice_experiences.wiring import create_callback_worker as create

    return create(
        session_factory,
        starting_lease_seconds=starting_lease_seconds,
        reconcile_after_seconds=reconcile_after_seconds,
        max_active_seconds=max_active_seconds,
    )


__all__ = [
    "DatabaseSession",
    "SessionFactory",
    "VoiceCallbackWorkerPort",
    "VoiceContextFieldSnapshot",
    "VoiceContextOptionSnapshot",
    "VoiceContextSchemaReader",
    "VoiceContextSchemaSnapshot",
    "VoiceRuntimeWebhookServicePort",
    "VoiceRuntimeWebhookTarget",
    "create_callback_worker",
    "create_context_schema_reader",
    "create_runtime_webhook_service",
    "register_models",
]
