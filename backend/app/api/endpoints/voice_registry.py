# FastAPI dependencies are intentionally declared in parameter defaults.
# ruff: noqa: B008

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth.deps import AuthContext, require_roles
from app.domain import voice_registry
from app.schemas.voice_registry import VoiceModelResponse, VoiceProviderResponse

router = APIRouter(prefix="/api/v1/voice", tags=["Voice Registry"])
READ_ROLES = ["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"]


def require_registry_read(
    context: AuthContext = Depends(require_roles(READ_ROLES)),
) -> AuthContext:
    return context


@router.get("/providers", response_model=list[VoiceProviderResponse])
def list_providers(context: AuthContext = Depends(require_registry_read)) -> Any:
    return [asdict(provider) for provider in voice_registry.list_providers()]


@router.get("/models", response_model=list[VoiceModelResponse])
def list_models(
    type: str | None = None,
    provider: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    context: AuthContext = Depends(require_registry_read),
) -> Any:
    models = voice_registry.list_models(
        model_type=type, provider_key=provider, status=status_filter
    )
    return [asdict(model) for model in models]


@router.get("/models/{model_id}", response_model=VoiceModelResponse)
def get_model(model_id: str, context: AuthContext = Depends(require_registry_read)) -> Any:
    model = voice_registry.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found.")
    return asdict(model)


@router.get("/models/{model_id}/capabilities", response_model=dict[str, bool])
def get_model_capabilities(
    model_id: str, context: AuthContext = Depends(require_registry_read)
) -> Any:
    model = voice_registry.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found.")
    return model.capabilities
