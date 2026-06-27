from __future__ import annotations

import base64
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.integrations import TenantEmailAsset
from app.services.storage_service import StorageService

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".png", ".jpg", ".jpeg"}
BLOCKED_EXTENSIONS = {".exe", ".js", ".html", ".php", ".bat", ".cmd", ".ps1", ".zip"}
ALLOWED_MIME_PREFIXES = ("application/pdf", "application/vnd.", "text/csv", "image/png", "image/jpeg")


class EmailAssetService:
    def __init__(self, db: Session, storage: StorageService | None = None) -> None:
        self.db = db
        self.storage = storage or StorageService()

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
