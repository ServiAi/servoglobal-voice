from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet

from app.core.config import settings


class SecretManagerError(RuntimeError):
    pass


class SecretManager:
    def __init__(self, encryption_key: str | None = None) -> None:
        self._encryption_key = encryption_key

    def encrypt_secret(self, value: str) -> str:
        if not value:
            raise SecretManagerError("Secret value is required.")
        return self._fernet().encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt_secret(self, value: str) -> str:
        if not value:
            raise SecretManagerError("Encrypted secret is required.")
        return self._fernet().decrypt(value.encode("utf-8")).decode("utf-8")

    def mask_secret(self, value: str) -> str:
        if not value:
            return ""
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}...{value[-4:]}"

    def _fernet(self) -> Fernet:
        raw_key = self._resolve_key()
        digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def _resolve_key(self) -> str:
        raw_key = self._encryption_key or os.getenv("INTEGRATIONS_ENCRYPTION_KEY") or settings.INTEGRATIONS_ENCRYPTION_KEY
        if raw_key:
            return raw_key
        if os.getenv("SERVIAI_TEST_SECRET_FALLBACK") == "1" or settings.DATABASE_URL.startswith("sqlite"):
            return "serviai-test-integrations-secret-key"
        raise SecretManagerError("INTEGRATIONS_ENCRYPTION_KEY is required for tenant integrations.")
