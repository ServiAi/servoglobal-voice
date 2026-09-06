# FastAPI dependencies are intentionally declared in parameter defaults.
# ruff: noqa: B008

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.db.session import get_db
from app.schemas.agents import (
    AgentCreateRequest,
    AgentDraftUpdateRequest,
    AgentResponse,
    AgentUpdateRequest,
    AgentVersionResponse,
)
from app.services.agent_service import (
    AgentConflictError,
    AgentNotFoundError,
    AgentService,
    AgentValidationError,
)
from app.services.tenant_feature_service import TenantFeatureDisabledError

router = APIRouter(prefix="/api/v1/agents", tags=["Agent Builder"])
READ_ROLES = ["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"]
WRITE_ROLES = ["platform_admin", "tenant_admin"]

SERVICE_ERRORS = (
    TenantFeatureDisabledError,
    AgentNotFoundError,
    AgentConflictError,
    AgentValidationError,
)


def require_agent_read(
    context: AuthContext = Depends(require_roles(READ_ROLES)),
) -> AuthContext:
    return context


def require_agent_write(
    context: AuthContext = Depends(require_roles(WRITE_ROLES)),
) -> AuthContext:
    return context


def _raise_service_error(
    exc: TenantFeatureDisabledError
    | AgentNotFoundError
    | AgentConflictError
    | AgentValidationError,
) -> NoReturn:
    if isinstance(exc, TenantFeatureDisabledError):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, AgentNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, AgentConflictError):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("", response_model=list[AgentResponse])
def list_agents(
    context: AuthContext = Depends(require_agent_read),
    db: Session = Depends(get_db),
) -> Any:
    service = AgentService(db)
    try:
        return [service.response(agent) for agent in service.list_agents(context.tenant.id)]
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(
    body: AgentCreateRequest,
    context: AuthContext = Depends(require_agent_write),
    db: Session = Depends(get_db),
) -> Any:
    service = AgentService(db)
    try:
        return service.response(service.create_agent(context.tenant.id, body, context.user.id))
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(
    agent_id: str,
    context: AuthContext = Depends(require_agent_read),
    db: Session = Depends(get_db),
) -> Any:
    service = AgentService(db)
    try:
        return service.response(service.get_agent(context.tenant.id, agent_id))
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.patch("/{agent_id}", response_model=AgentResponse)
def update_agent(
    agent_id: str,
    body: AgentUpdateRequest,
    context: AuthContext = Depends(require_agent_write),
    db: Session = Depends(get_db),
) -> Any:
    service = AgentService(db)
    try:
        return service.response(service.update_agent(context.tenant.id, agent_id, body))
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.get("/{agent_id}/versions", response_model=list[AgentVersionResponse])
def list_agent_versions(
    agent_id: str,
    context: AuthContext = Depends(require_agent_read),
    db: Session = Depends(get_db),
) -> Any:
    service = AgentService(db)
    try:
        return [
            service.version_response(version)
            for version in service.list_versions(context.tenant.id, agent_id)
        ]
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.get("/{agent_id}/draft", response_model=AgentVersionResponse)
def get_agent_draft(
    agent_id: str,
    context: AuthContext = Depends(require_agent_read),
    db: Session = Depends(get_db),
) -> Any:
    service = AgentService(db)
    try:
        return service.version_response(service.get_draft(context.tenant.id, agent_id))
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.patch("/{agent_id}/draft", response_model=AgentVersionResponse)
def update_agent_draft(
    agent_id: str,
    body: AgentDraftUpdateRequest,
    context: AuthContext = Depends(require_agent_write),
    db: Session = Depends(get_db),
) -> Any:
    service = AgentService(db)
    try:
        return service.version_response(
            service.update_draft(context.tenant.id, agent_id, body)
        )
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.post("/{agent_id}/draft", response_model=AgentVersionResponse, status_code=status.HTTP_201_CREATED)
def create_agent_next_draft(
    agent_id: str,
    context: AuthContext = Depends(require_agent_write),
    db: Session = Depends(get_db),
) -> Any:
    """Branch a new editable draft from the currently published version."""
    service = AgentService(db)
    try:
        return service.version_response(
            service.create_next_draft(context.tenant.id, agent_id, context.user.id)
        )
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.post("/{agent_id}/publish", response_model=AgentResponse)
def publish_agent(
    agent_id: str,
    context: AuthContext = Depends(require_agent_write),
    db: Session = Depends(get_db),
) -> Any:
    service = AgentService(db)
    try:
        return service.response(service.publish(context.tenant.id, agent_id, context.user.id))
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)


@router.post("/{agent_id}/archive", response_model=AgentResponse)
def archive_agent(
    agent_id: str,
    context: AuthContext = Depends(require_agent_write),
    db: Session = Depends(get_db),
) -> Any:
    service = AgentService(db)
    try:
        return service.response(service.archive_agent(context.tenant.id, agent_id, context.user.id))
    except SERVICE_ERRORS as exc:
        _raise_service_error(exc)
