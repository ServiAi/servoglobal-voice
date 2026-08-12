# FastAPI dependencies are intentionally declared in parameter defaults.
# ruff: noqa: B008

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.schemas.public_voice_experiences import PublicVoiceExperienceResponse
from app.schemas.public_voice_submissions import (
    PublicSubmissionError,
    PublicVoiceExperienceSubmissionRequest,
    PublicVoiceExperienceSubmissionResponse,
)
from app.schemas.public_voice_calls import (
    PublicVoiceCallError,
    PublicVoiceCallRequest,
    PublicVoiceCallResponse,
)
from app.services.public_voice_call_service import PublicCallFailure, PublicVoiceCallService
from app.services.public_voice_experience_service import (
    PublicExperienceNotFound,
    PublicVoiceExperienceService,
)
from app.services.public_voice_submission_service import (
    ExperienceVersionChanged,
    HistoricalValidationConfigurationError,
    PublicVoiceSubmissionService,
    SubmissionValidationFailed,
)
from app.services.turnstile_verification_service import TurnstileVerificationService
from app.services.voice_public_rate_limiter import (
    VoicePublicRateLimiter,
    VoicePublicRateLimitConfigurationError,
    pseudonymize_ip,
    resolve_public_client_ip,
)


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/public/voice-experiences", tags=["Voice Public"]
)
NO_STORE_HEADERS = {"Cache-Control": "no-store"}


def get_public_rate_limiter() -> VoicePublicRateLimiter:
    return VoicePublicRateLimiter(session_factory=SessionLocal)


def get_public_turnstile_verifier() -> TurnstileVerificationService:
    return TurnstileVerificationService()


def get_public_submission_service() -> PublicVoiceSubmissionService:
    return PublicVoiceSubmissionService(
        session_factory=SessionLocal,
        ttl_seconds=settings.VOICE_CONTEXT_SESSION_TTL_SECONDS,
    )


def get_public_call_service() -> PublicVoiceCallService:
    return PublicVoiceCallService(
        session_factory=SessionLocal,
        provider_timeout_seconds=settings.VOICE_RUNTIME_PROVIDER_TIMEOUT_SECONDS,
        reserved_lease_seconds=settings.VOICE_RUNTIME_RESERVED_LEASE_SECONDS,
        starting_lease_seconds=settings.VOICE_RUNTIME_STARTING_LEASE_SECONDS,
    )


def _call_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=PublicVoiceCallError(code=code).model_dump(),
        headers=NO_STORE_HEADERS,
    )


def _public_error(status_code: int, code: str, fields: list | None = None) -> HTTPException:
    payload = PublicSubmissionError(code=code, fields=fields or [])
    return HTTPException(
        status_code=status_code,
        detail=payload.model_dump(),
        headers=NO_STORE_HEADERS,
    )


@router.get("/{slug}", response_model=PublicVoiceExperienceResponse)
def get_public_voice_experience(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
) -> PublicVoiceExperienceResponse:
    response.headers.update(NO_STORE_HEADERS)
    try:
        return PublicVoiceExperienceService(db).resolve(slug)
    except PublicExperienceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
            headers=NO_STORE_HEADERS,
        ) from exc
    except Exception as exc:
        logger.error(
            "Unexpected public voice experience resolution failure",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load the experience",
            headers=NO_STORE_HEADERS,
        ) from None


@router.post(
    "/{slug}/submissions",
    response_model=PublicVoiceExperienceSubmissionResponse,
)
async def submit_public_voice_experience(
    slug: str,
    request: Request,
    response: Response,
    limiter: VoicePublicRateLimiter = Depends(get_public_rate_limiter),
    verifier: TurnstileVerificationService = Depends(get_public_turnstile_verifier),
    service: PublicVoiceSubmissionService = Depends(get_public_submission_service),
) -> PublicVoiceExperienceSubmissionResponse:
    response.headers.update(NO_STORE_HEADERS)
    normalized_ip = resolve_public_client_ip(
        request, settings.TRUST_CLOUDFLARE_CONNECTING_IP
    )
    try:
        ip_hash = pseudonymize_ip(
            settings.VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET, normalized_ip
        )
        if not limiter.consume(
            f"global:{ip_hash}",
            settings.VOICE_PUBLIC_SUBMISSION_RATE_LIMIT_GLOBAL_IP_PER_MINUTE,
        ):
            raise _public_error(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited")
    except HTTPException:
        raise
    except VoicePublicRateLimitConfigurationError:
        raise _public_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error") from None


    except Exception as exc:
        logger.error(
            "Public voice global rate limiter failed closed",
            extra={"error_type": type(exc).__name__},
        )
        raise _public_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error") from None


    try:
        limiter.cleanup(retention_hours=24, batch_size=500)
    except Exception as exc:
        logger.warning(
            "Public voice rate limit cleanup deferred",
            extra={"error_type": type(exc).__name__},
        )

    try:
        raw = await request.json()
        payload = PublicVoiceExperienceSubmissionRequest.model_validate(raw)
    except (ValueError, ValidationError):
        raise _public_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "validation_error") from None

    if payload.hp:
        raise _public_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "validation_error")

    try:
        snapshot = service.pre_resolve(slug)
    except PublicExperienceNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
            headers=NO_STORE_HEADERS,
        ) from None
    except Exception as exc:
        logger.error(
            "Unexpected public voice submission pre-resolution failure",
            extra={"error_type": type(exc).__name__},
        )
        raise _public_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error") from None

    try:
        if not limiter.consume(
            f"tenant:{snapshot.experience.tenant_id}:{ip_hash}",
            settings.VOICE_PUBLIC_SUBMISSION_RATE_LIMIT_TENANT_IP_PER_MINUTE,
        ):
            raise _public_error(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Public voice tenant rate limiter failed closed",
            extra={"error_type": type(exc).__name__},
        )
        raise _public_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error") from None

    try:
        verified = await verifier.verify(payload.turnstile_token, normalized_ip)
    except Exception:
        verified = False
    if not verified:
        raise _public_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "verification_failed")

    try:
        return service.persist(slug, payload).response
    except ExperienceVersionChanged:
        raise _public_error(status.HTTP_409_CONFLICT, "experience_version_changed") from None
    except SubmissionValidationFailed as exc:
        raise _public_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "validation_error",
            exc.fields,
        ) from None
    except HistoricalValidationConfigurationError:
        logger.error(
            "Invalid historical voice validation configuration",
            extra={"error_type": "HistoricalValidationConfigurationError"},
        )
        raise _public_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error") from None
    except PublicExperienceNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
            headers=NO_STORE_HEADERS,
        ) from None
    except Exception as exc:
        logger.error(
            "Unexpected public voice submission persistence failure",
            extra={"error_type": type(exc).__name__},
        )
        raise _public_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error") from None


@router.post("/{slug}/calls", response_model=PublicVoiceCallResponse)
async def launch_public_voice_call(
    slug: str,
    request: Request,
    response: Response,
    limiter: VoicePublicRateLimiter = Depends(get_public_rate_limiter),
    service: PublicVoiceCallService = Depends(get_public_call_service),
) -> PublicVoiceCallResponse:
    response.headers.update(NO_STORE_HEADERS)
    normalized_ip = resolve_public_client_ip(request, settings.TRUST_CLOUDFLARE_CONNECTING_IP)
    try:
        ip_hash = pseudonymize_ip(settings.VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET, normalized_ip)
        if not limiter.consume(
            f"call:global:{ip_hash}",
            settings.VOICE_PUBLIC_CALL_LAUNCH_RATE_LIMIT_GLOBAL_IP_PER_MINUTE,
        ):
            raise _call_error(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Public voice call limiter failed closed", extra={"error_type": type(exc).__name__})
        raise _call_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error") from None

    try:
        payload = PublicVoiceCallRequest.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise _call_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "validation_error") from None

    try:
        tenant_id = service.resolve_tenant(slug, payload.context_token)
        if not limiter.consume(
            f"call:tenant:{tenant_id}:{ip_hash}",
            settings.VOICE_PUBLIC_CALL_LAUNCH_RATE_LIMIT_TENANT_IP_PER_MINUTE,
        ):
            raise _call_error(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited")
        return service.launch(slug, payload.context_token)
    except HTTPException:
        raise
    except PublicCallFailure as exc:
        raise _call_error(exc.status_code, exc.code) from None
    except Exception as exc:
        logger.error("Unexpected public voice call failure", extra={"error_type": type(exc).__name__})
        raise _call_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error") from None
