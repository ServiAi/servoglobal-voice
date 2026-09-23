# FastAPI dependencies are intentionally declared in parameter defaults.
# ruff: noqa: B008

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.db.session import get_db
from app.schemas.tools_custom import (
    CustomToolCreateRequest,
    CustomToolResponse,
    CustomToolTestRequest,
    CustomToolTestResponse,
    CustomToolUpdateRequest,
)
from app.services.tenant_feature_service import TenantFeatureDisabledError
from app.services.tenant_tool_credential_service import TenantToolCredentialError, TenantToolNotFoundError
from app.services.tenant_tool_service import DuplicateToolKeyError, TenantToolError, TenantToolService, ToolInUseError

router = APIRouter(prefix="/api/v1/tools/custom", tags=["Custom Tools"])
READ_ROLES = ["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"]
WRITE_ROLES = ["platform_admin", "tenant_admin"]

SERVICE_ERRORS = (
    TenantFeatureDisabledError,
    TenantToolNotFoundError,
    DuplicateToolKeyError,
    ToolInUseError,
    TenantToolError,
    TenantToolCredentialError,
)


def require_tools_read(context: AuthContext = Depends(require_roles(READ_ROLES))) -> AuthContext:
    return context


def require_tools_write(context: AuthContext = Depends(require_roles(WRITE_ROLES))) -> AuthContext:
    return context


def _raise_service_error(
    exc: TenantFeatureDisabledError | TenantToolNotFoundError | DuplicateToolKeyError | ToolInUseError | TenantToolError | TenantToolCredentialError,
) -> NoReturn:
    if isinstance(exc, TenantFeatureDisabledError):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, TenantToolNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (DuplicateToolKeyError, ToolInUseError)):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("", response_model=list[CustomToolResponse])
def list_custom_tools(
    context: AuthContext = Depends(require_tools_read),
    db: Session = Depends(get_db),
) -> Any:
    service = TenantToolService(db)
    try:
        return service.list_tools(context.tenant.id)
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.post("", response_model=CustomToolResponse, status_code=status.HTTP_201_CREATED)
def create_custom_tool(
    body: CustomToolCreateRequest,
    context: AuthContext = Depends(require_tools_write),
    db: Session = Depends(get_db),
) -> Any:
    service = TenantToolService(db)
    try:
        return service.create_tool(context.tenant.id, context.user.id, body)
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.get("/{tool_id}", response_model=CustomToolResponse)
def get_custom_tool(
    tool_id: str,
    context: AuthContext = Depends(require_tools_read),
    db: Session = Depends(get_db),
) -> Any:
    service = TenantToolService(db)
    try:
        return service.get_tool(context.tenant.id, tool_id)
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.patch("/{tool_id}", response_model=CustomToolResponse)
def update_custom_tool(
    tool_id: str,
    body: CustomToolUpdateRequest,
    context: AuthContext = Depends(require_tools_write),
    db: Session = Depends(get_db),
) -> Any:
    service = TenantToolService(db)
    try:
        return service.update_tool(context.tenant.id, tool_id, body, actor_user_id=context.user.id)
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_tool(
    tool_id: str,
    context: AuthContext = Depends(require_tools_write),
    db: Session = Depends(get_db),
) -> None:
    service = TenantToolService(db)
    try:
        service.delete_tool(context.tenant.id, tool_id)
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.post("/{tool_id}/test", response_model=CustomToolTestResponse)
def test_custom_tool(
    tool_id: str,
    body: CustomToolTestRequest,
    context: AuthContext = Depends(require_tools_write),
    db: Session = Depends(get_db),
) -> Any:
    service = TenantToolService(db)
    try:
        return service.test_tool(context.tenant.id, tool_id, body.arguments)
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.post("/{tool_id}/activate", response_model=CustomToolResponse)
def activate_custom_tool(
    tool_id: str,
    context: AuthContext = Depends(require_tools_write),
    db: Session = Depends(get_db),
) -> Any:
    service = TenantToolService(db)
    try:
        return service.activate_tool(context.tenant.id, tool_id)
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.post("/{tool_id}/disable", response_model=CustomToolResponse)
def disable_custom_tool(
    tool_id: str,
    context: AuthContext = Depends(require_tools_write),
    db: Session = Depends(get_db),
) -> Any:
    service = TenantToolService(db)
    try:
        return service.disable_tool(context.tenant.id, tool_id)
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)
