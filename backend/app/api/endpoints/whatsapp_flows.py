from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext
from app.api.endpoints.integrations import require_enabled_integration
from app.db.session import get_db
from app.schemas.whatsapp_flows import (
    WhatsAppFlowCompileResponse,
    WhatsAppFlowCreateRequest,
    WhatsAppFlowResponse,
    WhatsAppFlowUpdateRequest,
)
from app.services.whatsapp_flow_service import (
    WhatsAppFlowConflictError,
    WhatsAppFlowNotFoundError,
    WhatsAppFlowProviderError,
    WhatsAppFlowService,
    WhatsAppFlowValidationError,
)


router = APIRouter(prefix="/api/v1/integrations/whatsapp/flows", tags=["WhatsApp Flows"])
READ_ROLES = ["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"]
WRITE_ROLES = ["platform_admin", "tenant_admin"]


def _raise_service_error(exc: Exception) -> NoReturn:
    if isinstance(exc, WhatsAppFlowNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, WhatsAppFlowConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, WhatsAppFlowValidationError) or isinstance(exc, ValueError):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(exc, WhatsAppFlowProviderError):
        code = status.HTTP_502_BAD_GATEWAY
    else:
        raise exc
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("", response_model=list[WhatsAppFlowResponse])
def list_flows(
    context: AuthContext = Depends(require_enabled_integration("whatsapp", READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return WhatsAppFlowService(db).list_flows(context.tenant.id)


@router.post("", response_model=WhatsAppFlowResponse, status_code=status.HTTP_201_CREATED)
def create_flow(
    body: WhatsAppFlowCreateRequest,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return WhatsAppFlowService(db).create_draft(context.tenant.id, body, context.user.id)
    except Exception as exc:
        _raise_service_error(exc)


@router.get("/{flow_id}", response_model=WhatsAppFlowResponse)
def get_flow(
    flow_id: str,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = WhatsAppFlowService(db)
    try:
        return service.response(service.get_owned(context.tenant.id, flow_id))
    except Exception as exc:
        _raise_service_error(exc)


@router.patch("/{flow_id}", response_model=WhatsAppFlowResponse)
def update_flow(
    flow_id: str,
    body: WhatsAppFlowUpdateRequest,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return WhatsAppFlowService(db).update_draft(context.tenant.id, flow_id, body)
    except Exception as exc:
        _raise_service_error(exc)


@router.delete("/{flow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_flow(
    flow_id: str,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Response:
    try:
        WhatsAppFlowService(db).delete_draft(context.tenant.id, flow_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        _raise_service_error(exc)


@router.post("/{flow_id}/compile", response_model=WhatsAppFlowCompileResponse)
def compile_flow(
    flow_id: str,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return WhatsAppFlowService(db).compile(context.tenant.id, flow_id)
    except Exception as exc:
        _raise_service_error(exc)


@router.post("/{flow_id}/sync-meta", response_model=WhatsAppFlowResponse)
def sync_flow_meta(
    flow_id: str,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return WhatsAppFlowService(db).sync_meta(context.tenant.id, flow_id)
    except Exception as exc:
        _raise_service_error(exc)


@router.post("/{flow_id}/sync-status", response_model=WhatsAppFlowResponse)
def sync_flow_status(
    flow_id: str,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return WhatsAppFlowService(db).sync_status(context.tenant.id, flow_id)
    except Exception as exc:
        _raise_service_error(exc)


@router.post("/{flow_id}/publish", response_model=WhatsAppFlowResponse)
def publish_flow(
    flow_id: str,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return WhatsAppFlowService(db).publish(context.tenant.id, flow_id)
    except Exception as exc:
        _raise_service_error(exc)


@router.post("/{flow_id}/clone", response_model=WhatsAppFlowResponse, status_code=status.HTTP_201_CREATED)
def clone_flow(
    flow_id: str,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return WhatsAppFlowService(db).clone_published(context.tenant.id, flow_id, context.user.id)
    except Exception as exc:
        _raise_service_error(exc)


@router.post("/{flow_id}/deprecate", response_model=WhatsAppFlowResponse)
def deprecate_flow(
    flow_id: str,
    context: AuthContext = Depends(require_enabled_integration("whatsapp", WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return WhatsAppFlowService(db).deprecate(context.tenant.id, flow_id)
    except Exception as exc:
        _raise_service_error(exc)
