from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, get_current_auth_context, require_roles
from app.db.session import get_db
from app.models.integrations import TenantEmailAsset
from app.models.identity import User
from app.schemas.integrations import EmailAssetItem
from app.services.email_asset_service import EmailAssetService
from app.services.onboarding_service import OnboardingService


router = APIRouter(tags=["Email Assets"])


def _safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename or "").name)
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("Attachment filename is required.")
    return cleaned


def _asset_response(asset: TenantEmailAsset) -> EmailAssetItem:
    return EmailAssetItem(
        id=asset.id,
        original_filename=asset.original_filename,
        mime_type=asset.mime_type,
        file_size_bytes=asset.file_size_bytes,
        status=asset.status,
    )


def _internal_user(context: AuthContext = Depends(get_current_auth_context)) -> User:
    if not context.user.is_internal:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Internal platform access required")
    return context.user


def _store_asset(db: Session, tenant_id: str, user_id: str | None, file: UploadFile) -> TenantEmailAsset:
    content = file.file.read()
    safe_filename = _safe_filename(file.filename or "")
    mime_type = file.content_type or "application/octet-stream"
    EmailAssetService(db)._validate_file_metadata(safe_filename, mime_type, len(content))
    checksum = hashlib.sha256(content).hexdigest()
    asset_id = str(uuid.uuid4())
    storage_key = f"tenants/{tenant_id}/email-assets/{asset_id}/{safe_filename}"
    service = EmailAssetService(db)
    service.storage.upload_bytes(storage_key, content)
    asset = TenantEmailAsset(
        id=asset_id,
        tenant_id=tenant_id,
        uploaded_by_user_id=user_id,
        original_filename=safe_filename,
        storage_key=storage_key,
        mime_type=mime_type,
        file_size_bytes=len(content),
        checksum_sha256=checksum,
        visibility="private",
        status="uploaded",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _list_assets(db: Session, tenant_id: str) -> list[TenantEmailAsset]:
    return list(
        db.scalars(
            select(TenantEmailAsset)
            .where(TenantEmailAsset.tenant_id == tenant_id, TenantEmailAsset.status.in_(["uploaded", "approved"]))
            .order_by(TenantEmailAsset.created_at.desc())
        ).all()
    )


def _delete_asset(db: Session, tenant_id: str, asset_id: str) -> None:
    asset = db.scalar(
        select(TenantEmailAsset).where(TenantEmailAsset.tenant_id == tenant_id, TenantEmailAsset.id == asset_id)
    )
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    asset.status = "deleted"
    EmailAssetService(db).storage.delete(asset.storage_key)
    db.commit()


@router.post("/api/v1/integrations/resend/assets", response_model=EmailAssetItem)
def upload_email_asset(
    file: UploadFile = File(...),
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
) -> Any:
    try:
        return _asset_response(_store_asset(db, context.tenant.id, context.user.id, file))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/api/v1/integrations/resend/assets", response_model=list[EmailAssetItem])
def list_email_assets(
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    return [_asset_response(asset) for asset in _list_assets(db, context.tenant.id)]


@router.delete("/api/v1/integrations/resend/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_email_asset(
    asset_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
) -> None:
    _delete_asset(db, context.tenant.id, asset_id)


@router.post("/api/v1/admin/tenants/{tenant_id}/integrations/resend/assets", response_model=EmailAssetItem)
def upload_admin_email_asset(
    tenant_id: str,
    file: UploadFile = File(...),
    user: User = Depends(_internal_user),
    db: Session = Depends(get_db),
) -> Any:
    try:
        OnboardingService(db).get_tenant(tenant_id)
        return _asset_response(_store_asset(db, tenant_id, user.id, file))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/api/v1/admin/tenants/{tenant_id}/integrations/resend/assets", response_model=list[EmailAssetItem])
def list_admin_email_assets(
    tenant_id: str,
    user: User = Depends(_internal_user),
    db: Session = Depends(get_db),
) -> Any:
    del user
    try:
        OnboardingService(db).get_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [_asset_response(asset) for asset in _list_assets(db, tenant_id)]


@router.delete("/api/v1/admin/tenants/{tenant_id}/integrations/resend/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_email_asset(
    tenant_id: str,
    asset_id: str,
    user: User = Depends(_internal_user),
    db: Session = Depends(get_db),
) -> None:
    del user
    _delete_asset(db, tenant_id, asset_id)
