from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.modules.identity.public import AuthContext
from app.modules.identity.api.deps import get_current_auth_context, require_roles
from app.db.session import get_db
from app.modules.integrations.api.schemas import EmailAssetItem
from app.modules.integrations.application.email.asset_service import EmailAssetService
from app.modules.integrations.wiring import require_tenant

router = APIRouter(tags=["Email Assets"])


def _asset_response(asset: Any) -> EmailAssetItem:
    return EmailAssetItem(
        id=asset.id,
        original_filename=asset.original_filename,
        mime_type=asset.mime_type,
        file_size_bytes=asset.file_size_bytes,
        status=asset.status,
    )


def _internal_user_id(context: AuthContext = Depends(get_current_auth_context)) -> str:
    if not context.user.is_internal:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Internal platform access required")
    return context.user.id


def _store_asset(db: Session, tenant_id: str, user_id: str | None, file: UploadFile) -> Any:
    return EmailAssetService(db).create_asset(
        tenant_id=tenant_id,
        uploaded_by_user_id=user_id,
        filename=file.filename or "",
        mime_type=file.content_type or "application/octet-stream",
        content=file.file.read(),
    )


def _delete_asset(db: Session, tenant_id: str, asset_id: str) -> None:
    if not EmailAssetService(db).delete_asset(tenant_id, asset_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")


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
    return [_asset_response(asset) for asset in EmailAssetService(db).list_assets(context.tenant.id)]


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
    user_id: str = Depends(_internal_user_id),
    db: Session = Depends(get_db),
) -> Any:
    try:
        require_tenant(db, tenant_id)
        return _asset_response(_store_asset(db, tenant_id, user_id, file))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/api/v1/admin/tenants/{tenant_id}/integrations/resend/assets", response_model=list[EmailAssetItem])
def list_admin_email_assets(
    tenant_id: str,
    user_id: str = Depends(_internal_user_id),
    db: Session = Depends(get_db),
) -> Any:
    del user_id
    try:
        require_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [_asset_response(asset) for asset in EmailAssetService(db).list_assets(tenant_id)]


@router.delete("/api/v1/admin/tenants/{tenant_id}/integrations/resend/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_email_asset(
    tenant_id: str,
    asset_id: str,
    user_id: str = Depends(_internal_user_id),
    db: Session = Depends(get_db),
) -> None:
    del user_id
    _delete_asset(db, tenant_id, asset_id)
