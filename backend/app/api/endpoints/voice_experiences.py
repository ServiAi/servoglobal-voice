# FastAPI dependencies are intentionally declared in parameter defaults.
# ruff: noqa: B008

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext
from app.api.endpoints.voice_context_schemas import (
    require_context_read,
    require_context_write,
)
from app.db.session import get_db
from app.schemas.voice_experiences import (
    VoiceExperienceResponse,
    VoiceExperienceVersionResponse,
    VoiceExperienceWriteRequest,
)
from app.services.tenant_feature_service import TenantFeatureDisabledError
from app.services.voice_experience_service import (
    VoiceExperienceConflictError,
    VoiceExperienceNotFoundError,
    VoiceExperienceService,
    VoiceExperienceValidationError,
)

router = APIRouter(prefix="/api/v1/voice/experiences", tags=["Voice Experiences"])
SERVICE_ERRORS = (
    TenantFeatureDisabledError,
    VoiceExperienceNotFoundError,
    VoiceExperienceConflictError,
    VoiceExperienceValidationError,
)


def _raise_service_error(
    exc: TenantFeatureDisabledError
    | VoiceExperienceNotFoundError
    | VoiceExperienceConflictError
    | VoiceExperienceValidationError,
) -> NoReturn:
    if isinstance(exc, TenantFeatureDisabledError):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, VoiceExperienceNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, VoiceExperienceConflictError):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("", response_model=list[VoiceExperienceResponse])
def list_voice_experiences(
    context: AuthContext = Depends(require_context_read),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return VoiceExperienceService(db).list_experiences(context.tenant.id)
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.post("", response_model=VoiceExperienceResponse, status_code=status.HTTP_201_CREATED)
def create_voice_experience(
    body: VoiceExperienceWriteRequest,
    context: AuthContext = Depends(require_context_write),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceExperienceService(db)
    try:
        return service.response(
            service.create_experience(context.tenant.id, body, context.user.id)
        )
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.get("/{experience_id}", response_model=VoiceExperienceResponse)
def get_voice_experience(
    experience_id: str,
    context: AuthContext = Depends(require_context_read),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceExperienceService(db)
    try:
        return service.response(service.get_experience(context.tenant.id, experience_id))
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.put("/{experience_id}", response_model=VoiceExperienceResponse)
def update_voice_experience(
    experience_id: str,
    body: VoiceExperienceWriteRequest,
    context: AuthContext = Depends(require_context_write),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceExperienceService(db)
    try:
        return service.response(
            service.update_experience(context.tenant.id, experience_id, body)
        )
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.post("/{experience_id}/publish", response_model=VoiceExperienceResponse)
def publish_voice_experience(
    experience_id: str,
    context: AuthContext = Depends(require_context_write),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceExperienceService(db)
    try:
        return service.response(
            service.publish_experience(context.tenant.id, experience_id, context.user.id)
        )
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.post("/{experience_id}/unpublish", response_model=VoiceExperienceResponse)
def unpublish_voice_experience(
    experience_id: str,
    context: AuthContext = Depends(require_context_write),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceExperienceService(db)
    try:
        return service.response(
            service.unpublish_experience(context.tenant.id, experience_id)
        )
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.post("/{experience_id}/archive", response_model=VoiceExperienceResponse)
def archive_voice_experience(
    experience_id: str,
    context: AuthContext = Depends(require_context_write),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceExperienceService(db)
    try:
        return service.response(service.archive_experience(context.tenant.id, experience_id))
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.get(
    "/{experience_id}/versions", response_model=list[VoiceExperienceVersionResponse]
)
def list_voice_experience_versions(
    experience_id: str,
    context: AuthContext = Depends(require_context_read),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return VoiceExperienceService(db).list_versions(context.tenant.id, experience_id)
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)
