from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.asterisk_provisioning import (
    AsteriskApplyResultsRequest,
    AsteriskApplyResultsResponse,
    AsteriskDesiredStateResponse,
)
from app.services.asterisk_provisioning_service import AsteriskProvisioningService

router = APIRouter(prefix="/api/v1/internal/asterisk", tags=["Asterisk Provisioning"])


def require_asterisk_provisioner_secret(
    x_asterisk_provisioner_secret: str | None = Header(None),
) -> None:
    configured = settings.ASTERISK_PROVISIONER_SHARED_SECRET
    if not configured or not x_asterisk_provisioner_secret or not hmac.compare_digest(
        x_asterisk_provisioner_secret, configured
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Asterisk provisioner secret.",
        )


@router.get("/desired-state", response_model=AsteriskDesiredStateResponse)
def desired_state(
    response: Response,
    _: None = Depends(require_asterisk_provisioner_secret),
    db: Session = Depends(get_db),
) -> AsteriskDesiredStateResponse:
    response.headers["Cache-Control"] = "no-store"
    return AsteriskProvisioningService(db).desired_state()


@router.post("/apply-results", response_model=AsteriskApplyResultsResponse)
def apply_results(
    body: AsteriskApplyResultsRequest,
    response: Response,
    _: None = Depends(require_asterisk_provisioner_secret),
    db: Session = Depends(get_db),
) -> AsteriskApplyResultsResponse:
    response.headers["Cache-Control"] = "no-store"
    return AsteriskProvisioningService(db).apply_results(body.results)

