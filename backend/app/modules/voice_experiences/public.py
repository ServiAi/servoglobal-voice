"""Lightweight contracts for other bounded contexts."""

from typing import Protocol

from app.modules.voice_experiences.domain.views import (
    VoiceContextFieldSnapshot,
    VoiceContextSchemaSnapshot,
)


class VoiceContextSchemaReader(Protocol):
    def get_schema_snapshot(
        self, tenant_id: str, schema_id: str
    ) -> VoiceContextSchemaSnapshot | None: ...


def create_context_schema_reader(session: object) -> VoiceContextSchemaReader:
    """Resolve the DB adapter lazily so importing this module stays lightweight."""
    from app.modules.voice_experiences.wiring import create_context_schema_reader as create

    return create(session)


def register_models() -> None:
    """Register ORM mappings from the application composition root."""
    from app.modules.voice_experiences.infrastructure import models  # noqa: F401


def create_runtime_webhook_service(session: object) -> object:
    from app.modules.voice_experiences.wiring import create_runtime_webhook_service as create

    return create(session)


def create_callback_worker(
    session_factory: object,
    *,
    starting_lease_seconds: int,
    reconcile_after_seconds: int,
    max_active_seconds: int,
) -> object:
    from app.modules.voice_experiences.wiring import create_callback_worker as create

    return create(
        session_factory,
        starting_lease_seconds=starting_lease_seconds,
        reconcile_after_seconds=reconcile_after_seconds,
        max_active_seconds=max_active_seconds,
    )


__all__ = [
    "VoiceContextFieldSnapshot",
    "VoiceContextSchemaReader",
    "VoiceContextSchemaSnapshot",
    "create_callback_worker",
    "create_context_schema_reader",
    "create_runtime_webhook_service",
    "register_models",
]
