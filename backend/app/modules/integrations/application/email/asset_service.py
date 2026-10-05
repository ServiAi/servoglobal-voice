from __future__ import annotations

import base64
import hashlib
import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.integrations.application.ports import AssetStoragePort
from app.modules.integrations.infrastructure.models import TenantEmailAsset

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".png", ".jpg", ".jpeg", ".md", ".txt"}
BLOCKED_EXTENSIONS = {".exe", ".js", ".html", ".php", ".bat", ".cmd", ".ps1", ".zip"}
ALLOWED_MIME_PREFIXES = (
    "application/pdf",
    "application/vnd.",
    "text/csv",
    "text/markdown",
    "text/plain",
    "image/png",
    "image/jpeg",
)


def _safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename or "").name)
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("Attachment filename is required.")
    return cleaned


class EmailAssetService:
    def __init__(self, db: Session, storage: AssetStoragePort | None = None) -> None:
        from app.modules.integrations.wiring import default_asset_storage

        self.db = db
        self.storage = storage or default_asset_storage()

    def create_asset(
        self,
        *,
        tenant_id: str,
        uploaded_by_user_id: str | None,
        filename: str,
        mime_type: str,
        content: bytes,
        folder: str = "assets",
    ) -> TenantEmailAsset:
        from app.modules.integrations.wiring import require_tenant

        tenant = require_tenant(self.db, tenant_id)
        safe_filename = _safe_filename(filename)
        self._validate_file_metadata(safe_filename, mime_type, len(content))
        asset_id = str(uuid.uuid4())
        storage_key = self.storage.tenant_object_key(tenant.slug, folder, asset_id, safe_filename)
        self.storage.upload_bytes(storage_key, content)
        asset = TenantEmailAsset(
            id=asset_id,
            tenant_id=tenant_id,
            uploaded_by_user_id=uploaded_by_user_id,
            original_filename=safe_filename,
            storage_key=storage_key,
            mime_type=mime_type,
            file_size_bytes=len(content),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
            visibility="private",
            status="uploaded",
        )
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def list_assets(self, tenant_id: str) -> list[TenantEmailAsset]:
        return list(
            self.db.scalars(
                select(TenantEmailAsset)
                .where(TenantEmailAsset.tenant_id == tenant_id, TenantEmailAsset.status.in_(["uploaded", "approved"]))
                .order_by(TenantEmailAsset.created_at.desc())
            ).all()
        )

    def delete_asset(self, tenant_id: str, asset_id: str) -> bool:
        """Soft-delete the asset and its stored object. False if the tenant has no such asset."""
        asset = self.db.scalar(
            select(TenantEmailAsset).where(TenantEmailAsset.tenant_id == tenant_id, TenantEmailAsset.id == asset_id)
        )
        if asset is None:
            return False
        asset.status = "deleted"
        self.storage.delete(asset.storage_key)
        self.db.commit()
        return True

    def validate_assets(self, tenant_id: str, asset_ids: list[str] | None) -> list[TenantEmailAsset]:
        if not asset_ids:
            return []
        assets = list(
            self.db.scalars(
                select(TenantEmailAsset).where(
                    TenantEmailAsset.tenant_id == tenant_id,
                    TenantEmailAsset.id.in_(asset_ids),
                    TenantEmailAsset.status.in_(["uploaded", "approved"]),
                )
            ).all()
        )
        if len(assets) != len(set(asset_ids)):
            raise ValueError("One or more attachments are not available for this tenant.")
        total = sum(asset.file_size_bytes for asset in assets)
        if total > settings.EMAIL_MAX_TOTAL_ATTACHMENTS_BYTES:
            raise ValueError("Total attachment size exceeds the allowed limit.")
        for asset in assets:
            self._validate_file_metadata(asset.original_filename, asset.mime_type, asset.file_size_bytes)
        return assets

    def build_resend_attachments(self, assets: list[TenantEmailAsset]) -> list[dict]:
        attachments = []
        for asset in assets:
            content = self.storage.read_bytes(asset.storage_key)
            attachments.append(
                {
                    "filename": asset.original_filename,
                    "content": base64.b64encode(content).decode("ascii"),
                }
            )
        return attachments

    def _validate_file_metadata(self, filename: str, mime_type: str, size: int) -> None:
        suffix = Path(filename).suffix.lower()
        if suffix in BLOCKED_EXTENSIONS or suffix not in ALLOWED_EXTENSIONS:
            raise ValueError("Attachment type is not allowed.")
        if not mime_type.startswith(ALLOWED_MIME_PREFIXES):
            raise ValueError("Attachment MIME type is not allowed.")
        if size > settings.EMAIL_MAX_ATTACHMENT_BYTES:
            raise ValueError("Attachment size exceeds the allowed limit.")
