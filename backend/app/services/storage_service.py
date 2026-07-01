from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.core.config import settings


class StorageService:
    def __init__(
        self,
        base_path: str | None = None,
        *,
        driver: str | None = None,
        bucket: str | None = None,
        s3_client: Any | None = None,
    ) -> None:
        self.driver = (driver or settings.EMAIL_ASSETS_STORAGE_DRIVER or "local").lower()
        self.base_path = Path(base_path or settings.EMAIL_ASSETS_STORAGE_PATH)
        self.bucket = bucket or settings.EMAIL_ASSETS_BUCKET
        self._s3_client = s3_client

    def upload_bytes(self, storage_key: str, content: bytes) -> str:
        clean_key = self._clean_key(storage_key)
        if self.driver == "s3":
            self._require_bucket()
            self._client().put_object(Bucket=self.bucket, Key=clean_key, Body=content)
            return clean_key
        path = self._resolve(clean_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return clean_key

    def read_bytes(self, storage_key: str) -> bytes:
        clean_key = self._clean_key(storage_key)
        if self.driver == "s3":
            self._require_bucket()
            response = self._client().get_object(Bucket=self.bucket, Key=clean_key)
            return response["Body"].read()
        return self._resolve(clean_key).read_bytes()

    def delete(self, storage_key: str) -> None:
        clean_key = self._clean_key(storage_key)
        if self.driver == "s3":
            self._require_bucket()
            self._client().delete_object(Bucket=self.bucket, Key=clean_key)
            return
        path = self._resolve(clean_key)
        if path.exists():
            path.unlink()

    @staticmethod
    def tenant_object_key(tenant_name: str, folder: str, asset_id: str, filename: str) -> str:
        return "/".join(
            [
                "tenants",
                StorageService._safe_segment(tenant_name),
                StorageService._safe_segment(folder),
                StorageService._safe_segment(asset_id),
                StorageService._safe_segment(filename),
            ]
        )

    def _client(self):
        if self._s3_client is None:
            import boto3
            from botocore.config import Config

            addressing_style = "path" if settings.EMAIL_ASSETS_S3_FORCE_PATH_STYLE else "auto"
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=settings.EMAIL_ASSETS_S3_ENDPOINT or None,
                region_name=settings.EMAIL_ASSETS_S3_REGION,
                aws_access_key_id=settings.EMAIL_ASSETS_S3_ACCESS_KEY or None,
                aws_secret_access_key=settings.EMAIL_ASSETS_S3_SECRET_KEY or None,
                config=Config(s3={"addressing_style": addressing_style}),
            )
        return self._s3_client

    def _require_bucket(self) -> None:
        if not self.bucket:
            raise ValueError("EMAIL_ASSETS_BUCKET is required for s3 storage.")

    def _clean_key(self, storage_key: str) -> str:
        clean_key = storage_key.replace("\\", "/").lstrip("/")
        if not clean_key or ".." in clean_key.split("/"):
            raise ValueError("Invalid storage key.")
        return clean_key

    @staticmethod
    def _safe_segment(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip()).strip("._-")
        if not cleaned:
            raise ValueError("Invalid storage key segment.")
        return cleaned

    def _resolve(self, storage_key: str) -> Path:
        path = (self.base_path / self._clean_key(storage_key)).resolve()
        base = self.base_path.resolve()
        try:
            path.relative_to(base)
        except ValueError as exc:
            raise ValueError("Invalid storage key.") from exc
        return path
