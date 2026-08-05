from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.db.session import get_db
from app.schemas.voice_context import (
    VoiceContextFieldRequest,
    VoiceContextFieldResponse,
    VoiceContextSchemaCreateRequest,
    VoiceContextSchemaMetaUpdateRequest,
    VoiceContextSchemaResponse,
    VoiceContextSchemaSummaryResponse,
)
from app.services.tenant_feature_service import TenantFeatureDisabledError
from app.services.voice_context_service import (
    VoiceContextConflictError,
    VoiceContextNotFoundError,
    VoiceContextService,
    VoiceContextValidationError,
)


router = APIRouter(prefix="/api/v1/voice", tags=["Voice Context Schemas"])
READ_ROLES = ["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"]
WRITE_ROLES = ["platform_admin", "tenant_admin"]


def require_context_read(
    context: AuthContext = Depends(require_roles(READ_ROLES)),
) -> AuthContext:
    return _require_internal_platform_admin(context)


def require_context_write(
    context: AuthContext = Depends(require_roles(WRITE_ROLES)),
) -> AuthContext:
    return _require_internal_platform_admin(context)


def _require_internal_platform_admin(context: AuthContext) -> AuthContext:
    if context.role == "platform_admin" and not context.user.is_internal:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administration requires an internal user.",
        )
    return context


def _raise_service_error(exc: Exception) -> NoReturn:
    if isinstance(exc, TenantFeatureDisabledError):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, VoiceContextNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, VoiceContextConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, VoiceContextValidationError):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        raise exc
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get(
    "/agents/{agent_config_id}/context-schemas",
    response_model=list[VoiceContextSchemaSummaryResponse],
)
def list_context_schemas(
    agent_config_id: str,
    context: AuthContext = Depends(require_context_read),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return VoiceContextService(db).list_schemas(context.tenant.id, agent_config_id)
    except Exception as exc:
        _raise_service_error(exc)


@router.post(
    "/agents/{agent_config_id}/context-schemas",
    response_model=VoiceContextSchemaResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_context_schema(
    agent_config_id: str,
    body: VoiceContextSchemaCreateRequest,
    context: AuthContext = Depends(require_context_write),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceContextService(db)
    try:
        schema = service.create_schema(
            context.tenant.id, agent_config_id, body, context.user.id
        )
        return service.schema_response(schema)
    except Exception as exc:
        _raise_service_error(exc)


@router.get(
    "/agents/{agent_config_id}/context-schemas/{schema_key}/versions",
    response_model=list[VoiceContextSchemaSummaryResponse],
)
def list_context_schema_versions(
    agent_config_id: str,
    schema_key: str,
    context: AuthContext = Depends(require_context_read),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return VoiceContextService(db).list_versions(
            context.tenant.id, agent_config_id, schema_key
        )
    except Exception as exc:
        _raise_service_error(exc)


@router.get("/context-schemas/{schema_id}", response_model=VoiceContextSchemaResponse)
def get_context_schema(
    schema_id: str,
    context: AuthContext = Depends(require_context_read),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceContextService(db)
    try:
        return service.schema_response(service.get_schema(context.tenant.id, schema_id))
    except Exception as exc:
        _raise_service_error(exc)


@router.put("/context-schemas/{schema_id}", response_model=VoiceContextSchemaResponse)
def update_context_schema(
    schema_id: str,
    body: VoiceContextSchemaMetaUpdateRequest,
    context: AuthContext = Depends(require_context_write),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceContextService(db)
    try:
        return service.schema_response(
            service.update_schema_meta(context.tenant.id, schema_id, body)
        )
    except Exception as exc:
        _raise_service_error(exc)


@router.post(
    "/context-schemas/{schema_id}/fields",
    response_model=VoiceContextFieldResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_context_field(
    schema_id: str,
    body: VoiceContextFieldRequest,
    context: AuthContext = Depends(require_context_write),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceContextService(db)
    try:
        return service.field_response(service.add_field(context.tenant.id, schema_id, body))
    except Exception as exc:
        _raise_service_error(exc)


@router.put(
    "/context-schemas/{schema_id}/fields/{field_id}",
    response_model=VoiceContextFieldResponse,
)
def update_context_field(
    schema_id: str,
    field_id: str,
    body: VoiceContextFieldRequest,
    context: AuthContext = Depends(require_context_write),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceContextService(db)
    try:
        return service.field_response(
            service.update_field(context.tenant.id, schema_id, field_id, body)
        )
    except Exception as exc:
        _raise_service_error(exc)


@router.delete(
    "/context-schemas/{schema_id}/fields/{field_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_context_field(
    schema_id: str,
    field_id: str,
    context: AuthContext = Depends(require_context_write),
    db: Session = Depends(get_db),
) -> Response:
    try:
        VoiceContextService(db).delete_field(context.tenant.id, schema_id, field_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        _raise_service_error(exc)


@router.post("/context-schemas/{schema_id}/activate", response_model=VoiceContextSchemaResponse)
def activate_context_schema(
    schema_id: str,
    context: AuthContext = Depends(require_context_write),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceContextService(db)
    try:
        schema = service.activate_schema(context.tenant.id, schema_id, context.user.id)
        return service.schema_response(schema)
    except Exception as exc:
        _raise_service_error(exc)


@router.post("/context-schemas/{schema_id}/archive", response_model=VoiceContextSchemaResponse)
def archive_context_schema(
    schema_id: str,
    context: AuthContext = Depends(require_context_write),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceContextService(db)
    try:
        schema = service.archive_schema(context.tenant.id, schema_id, context.user.id)
        return service.schema_response(schema)
    except Exception as exc:
        _raise_service_error(exc)


@router.post(
    "/context-schemas/{schema_id}/new-version",
    response_model=VoiceContextSchemaResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_context_schema_version(
    schema_id: str,
    context: AuthContext = Depends(require_context_write),
    db: Session = Depends(get_db),
) -> Any:
    service = VoiceContextService(db)
    try:
        schema = service.fork_new_version(context.tenant.id, schema_id, context.user.id)
        return service.schema_response(schema)
    except Exception as exc:
        _raise_service_error(exc)
