"""Composition root for Voice Experiences adapters and legacy runtime paths."""

from app.modules.voice_experiences.domain.ports import DatabaseSession, SessionFactory


def create_context_schema_reader(session: DatabaseSession):
    from app.modules.voice_experiences.infrastructure.context_schema_reader import (
        SqlAlchemyVoiceContextSchemaReader,
    )

    return SqlAlchemyVoiceContextSchemaReader(session)


def create_agent_reference_reader(session: DatabaseSession):
    from app.modules.voice_experiences.infrastructure.agent_reference_reader import (
        SqlAlchemyAgentReferenceReader,
    )

    return SqlAlchemyAgentReferenceReader(session)


def get_public_call_service():
    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.modules.voice_experiences.infrastructure.legacy_runtime.public_call_compat import (
        PublicVoiceCallService,
    )

    return PublicVoiceCallService(
        session_factory=SessionLocal,
        provider_timeout_seconds=settings.VOICE_RUNTIME_PROVIDER_TIMEOUT_SECONDS,
        reserved_lease_seconds=settings.VOICE_RUNTIME_RESERVED_LEASE_SECONDS,
        starting_lease_seconds=settings.VOICE_RUNTIME_STARTING_LEASE_SECONDS,
    )


def get_public_callback_service():
    from app.db.session import SessionLocal
    from app.modules.voice_experiences.infrastructure.legacy_runtime.callback_compat import (
        PublicVoiceCallbackService,
    )

    return PublicVoiceCallbackService(session_factory=SessionLocal)


def get_public_submission_service():
    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.modules.voice_experiences.application.submission_service import PublicVoiceSubmissionService

    return PublicVoiceSubmissionService(
        session_factory=SessionLocal,
        ttl_seconds=settings.VOICE_CONTEXT_SESSION_TTL_SECONDS,
    )


def get_public_turnstile_verifier():
    from app.services.turnstile_verification_service import TurnstileVerificationService

    return TurnstileVerificationService()


def get_public_rate_limiter():
    from app.db.session import SessionLocal
    from app.modules.voice_experiences.application.rate_limiter import VoicePublicRateLimiter

    return VoicePublicRateLimiter(session_factory=SessionLocal)


def create_runtime_webhook_service(session: DatabaseSession):
    from app.modules.voice_experiences.infrastructure.legacy_runtime.webhook_compat import (
        VoiceRuntimeWebhookService,
    )

    return VoiceRuntimeWebhookService(session)


def create_callback_worker(
    session_factory: SessionFactory,
    *,
    starting_lease_seconds: int,
    reconcile_after_seconds: int,
    max_active_seconds: int,
):
    from app.modules.voice_experiences.infrastructure.legacy_runtime.callback_compat import (
        VoiceCallbackWorker,
    )

    return VoiceCallbackWorker(
        session_factory,
        starting_lease_seconds=starting_lease_seconds,
        reconcile_after_seconds=reconcile_after_seconds,
        max_active_seconds=max_active_seconds,
    )
