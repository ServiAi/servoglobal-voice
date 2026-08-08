# FastAPI dependencies are intentionally declared in parameter defaults.
# ruff: noqa: B008

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.public_voice_experiences import PublicVoiceExperienceResponse
from app.services.public_voice_experience_service import (
    PublicExperienceNotFound,
    PublicVoiceExperienceService,
)


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/public/voice-experiences", tags=["Voice Public"]
)
NO_STORE_HEADERS = {"Cache-Control": "no-store"}


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
