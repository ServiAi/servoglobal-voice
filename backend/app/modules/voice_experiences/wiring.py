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
    from app.db.session import SessionLocal
    from app.modules.voice_experiences.application.public_webrtc_service import PublicWebRTCService
    from app.modules.voice_experiences.infrastructure.voice_runtime_adapter import VoiceRuntimeAdapter

    return PublicWebRTCService(session_factory=SessionLocal, runtime_factory=VoiceRuntimeAdapter)


def get_public_callback_service():
    from app.db.session import SessionLocal
    from app.modules.voice_experiences.application.public_callback_service import PublicCallbackService
    from app.modules.voice_experiences.infrastructure.legacy_runtime.callback_compat import (
        PublicVoiceCallbackService,
    )
    from app.modules.voice_experiences.infrastructure.voice_runtime_adapter import VoiceRuntimeAdapter

    return PublicCallbackService(
        session_factory=SessionLocal,
        runtime_factory=VoiceRuntimeAdapter,
        legacy=PublicVoiceCallbackService(session_factory=SessionLocal),  # rollback path, removed in PR #137
    )


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
    from app.modules.voice_experiences.application.callback_worker import CallbackWorker
    from app.modules.voice_experiences.infrastructure.legacy_runtime.callback_compat import (
        VoiceCallbackWorker as LegacyCallbackWorker,
    )
    from app.modules.voice_experiences.infrastructure.voice_runtime_adapter import VoiceRuntimeAdapter

    return CallbackWorker(
        session_factory,
        runtime_factory=VoiceRuntimeAdapter,
        # Provider-originated calls still in flight / flags off: legacy runtime, removed in PR #137.
        legacy=LegacyCallbackWorker(
            session_factory,
            starting_lease_seconds=starting_lease_seconds,
            reconcile_after_seconds=reconcile_after_seconds,
            max_active_seconds=max_active_seconds,
        ),
        starting_lease_seconds=starting_lease_seconds,
    )
