from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, get_current_auth_context, require_roles
from app.db.session import get_db
from app.models.identity import User
from app.schemas.forms import (
    FormCreateRequest,
    FormResponse,
    FormTokenCreateRequest,
    FormTokenResponse,
    PublicFormResponse,
    PublicFormSubmitRequest,
    PublicFormSubmitResponse,
)
from app.services.form_service import FormService
from app.services.onboarding_service import OnboardingService


router = APIRouter(tags=["Forms"])


def _internal_user(context: AuthContext = Depends(get_current_auth_context)) -> User:
    if not context.user.is_internal:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Internal platform access required")
    return context.user


def _form_response(form) -> FormResponse:
    return FormResponse(
        id=form.id,
        name=form.name,
        description=form.description,
        status=form.status,
        fields=[
            {
                "id": field.id,
                "key": field.key,
                "label": field.label,
                "field_type": field.field_type,
                "required": field.required,
                "options": field.options_json or [],
                "position": field.position,
            }
            for field in form.fields
        ],
    )


@router.get("/api/v1/forms", response_model=list[FormResponse])
def list_forms(
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    return [_form_response(form) for form in FormService(db).list_forms(context.tenant.id)]


@router.post("/api/v1/forms", response_model=FormResponse, status_code=status.HTTP_201_CREATED)
def create_form(
    body: FormCreateRequest,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return _form_response(FormService(db).create_form(context.tenant.id, body))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/api/v1/forms/{form_id}", response_model=FormResponse)
def get_form(
    form_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return _form_response(FormService(db).get_form(context.tenant.id, form_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/api/v1/forms/{form_id}/tokens", response_model=FormTokenResponse)
def create_form_token(
    form_id: str,
    body: FormTokenCreateRequest,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    try:
        token, link = FormService(db).create_token(context.tenant.id, form_id, body.lead_id, body.expires_in_days)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return FormTokenResponse(id=token.id, form_link=link, expires_at=token.expires_at)


@router.get("/api/v1/admin/tenants/{tenant_id}/forms", response_model=list[FormResponse])
def list_admin_forms(
    tenant_id: str,
    user: User = Depends(_internal_user),
    db: Session = Depends(get_db),
) -> Any:
    del user
    try:
        OnboardingService(db).get_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [_form_response(form) for form in FormService(db).list_forms(tenant_id)]


@router.post("/api/v1/admin/tenants/{tenant_id}/forms", response_model=FormResponse, status_code=status.HTTP_201_CREATED)
def create_admin_form(
    tenant_id: str,
    body: FormCreateRequest,
    user: User = Depends(_internal_user),
    db: Session = Depends(get_db),
) -> Any:
    del user
    try:
        OnboardingService(db).get_tenant(tenant_id)
        return _form_response(FormService(db).create_form(tenant_id, body))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/api/v1/admin/tenants/{tenant_id}/forms/{form_id}", response_model=FormResponse)
def get_admin_form(
    tenant_id: str,
    form_id: str,
    user: User = Depends(_internal_user),
    db: Session = Depends(get_db),
) -> Any:
    del user
    try:
        OnboardingService(db).get_tenant(tenant_id)
        return _form_response(FormService(db).get_form(tenant_id, form_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/api/v1/admin/tenants/{tenant_id}/forms/{form_id}/tokens", response_model=FormTokenResponse)
def create_admin_form_token(
    tenant_id: str,
    form_id: str,
    body: FormTokenCreateRequest,
    user: User = Depends(_internal_user),
    db: Session = Depends(get_db),
) -> Any:
    del user
    try:
        OnboardingService(db).get_tenant(tenant_id)
        token, link = FormService(db).create_token(tenant_id, form_id, body.lead_id, body.expires_in_days)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return FormTokenResponse(id=token.id, form_link=link, expires_at=token.expires_at)


@router.get("/api/v1/public/forms/{token}", response_model=PublicFormResponse)
def get_public_form(token: str, db: Session = Depends(get_db)) -> Any:
    try:
        form_token, form = FormService(db).load_public_form(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PublicFormResponse(
        form=_form_response(form),
        lead_preview={"contact_name": form_token.contact.name if form_token.contact else None},
    )


@router.post("/api/v1/public/forms/{token}/submit", response_model=PublicFormSubmitResponse)
def submit_public_form(token: str, body: PublicFormSubmitRequest, db: Session = Depends(get_db)) -> Any:
    try:
        submission = FormService(db).submit_public_form(token, body.answers, body.hp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return PublicFormSubmitResponse(status="success", submission_id=submission.id)
