from __future__ import annotations

from pathlib import Path

from app.core.config import settings


class StorageService:
    def __init__(self, base_path: str | None = None) -> None:
        self.base_path = Path(base_path or settings.EMAIL_ASSETS_STORAGE_PATH)

    def upload_bytes(self, storage_key: str, content: bytes) -> str:
        path = self._resolve(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return storage_key

    def read_bytes(self, storage_key: str) -> bytes:
        return self._resolve(storage_key).read_bytes()

    def delete(self, storage_key: str) -> None:
        path = self._resolve(storage_key)
        if path.exists():
            path.unlink()

    def _resolve(self, storage_key: str) -> Path:
        clean_key = storage_key.replace("\\", "/").lstrip("/")
        path = (self.base_path / clean_key).resolve()
        base = self.base_path.resolve()
        if not str(path).startswith(str(base)):
            raise ValueError("Invalid storage key.")
        return path
