from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tools import TenantTool, TenantToolCredential
from app.services.integration_event_service import IntegrationEventService
from app.services.secret_manager_service import SecretManager, SecretManagerError

_REQUIRED_SECRET_KEYS: dict[str, frozenset[str]] = {
    "none": frozenset(),
    "bearer": frozenset({"token"}),
    "api_key": frozenset({"api_key"}),
    "basic": frozenset({"username", "password"}),
}


class TenantToolCredentialError(ValueError):
    pass


class TenantToolNotFoundError(TenantToolCredentialError):
    pass


@dataclass(frozen=True)
class CredentialMaskedView:
    auth_type: str
    configured: bool
    api_key_header_name: str | None
    masked_fields: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedCredential:
    auth_type: str
    api_key_header_name: str | None
    secrets: dict[str, str]


class TenantToolCredentialService:
    """Owns encryption/decryption/masking for a TenantTool's auth material.

    `resolve_for_execution` is the only method that ever returns a
    decrypted secret -- it exists solely for CustomHttpToolExecutor to call
    at invoke/test time, never from an HTTP-facing endpoint. Every query
    filters explicitly by tenant_id even though tenant_tool_id is already
    globally unique: relying on the FK alone is exactly the kind of
    shortcut that causes cross-tenant secret leaks.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._secrets = SecretManager()

    @staticmethod
    def validate_credential(
        *,
        auth_type: str,
        secrets: dict[str, str] | None,
        api_key_header_name: str | None,
        allow_missing_secrets: bool = False,
    ) -> None:
        if auth_type not in _REQUIRED_SECRET_KEYS:
            raise TenantToolCredentialError(f"Unknown auth_type '{auth_type}'.")
        if auth_type == "api_key" and not api_key_header_name:
            raise TenantToolCredentialError("api_key_header_name is required for auth_type=api_key.")
        if allow_missing_secrets and not secrets:
            return
        required = _REQUIRED_SECRET_KEYS[auth_type]
        if set((secrets or {}).keys()) != required:
            raise TenantToolCredentialError(
                f"auth_type '{auth_type}' requires exactly the secret keys {sorted(required)}."
            )

    def set_credential(
        self,
        tenant_id: str,
        tenant_tool_id: str,
        *,
        auth_type: str,
        secrets: dict[str, str] | None = None,
        api_key_header_name: str | None = None,
        actor_user_id: str | None = None,
    ) -> TenantToolCredential:
        secrets = secrets or {}
        self.validate_credential(
            auth_type=auth_type,
            secrets=secrets,
            api_key_header_name=api_key_header_name,
        )

        self._get_tenant_tool_or_raise(tenant_id, tenant_tool_id)
        credential = self._get_credential_row(tenant_id, tenant_tool_id)
        is_rotation = credential is not None
        if credential is None:
            credential = TenantToolCredential(tenant_id=tenant_id, tenant_tool_id=tenant_tool_id)
            self.db.add(credential)

        encrypted = {key: self._secrets.encrypt_secret(value) for key, value in secrets.items()}
        credential.auth_type = auth_type
        credential.api_key_header_name = api_key_header_name if auth_type == "api_key" else None
        credential.secrets_json_encrypted = json.dumps(encrypted) if encrypted else None
        credential.rotated_at = datetime.now(UTC)
        credential.rotated_by_user_id = actor_user_id
        self.db.commit()
        self.db.refresh(credential)

        IntegrationEventService(self.db).record_event(
            tenant_id=tenant_id,
            provider="custom_tool",
            event_type="tool_credential_rotated" if is_rotation else "tool_credential_set",
            status="success",
            resource_type="tenant_tool",
            resource_id=tenant_tool_id,
            metadata={"auth_type": auth_type},
        )
        return credential

    def declare_auth_type(
        self,
        tenant_id: str,
        tenant_tool_id: str,
        *,
        auth_type: str,
        api_key_header_name: str | None = None,
        actor_user_id: str | None = None,
    ) -> TenantToolCredential:
        """Sets/creates the credential row's auth_type without requiring a
        secret yet -- lets a tenant pick "this tool needs a bearer token"
        now and supply the actual value later via set_credential, instead
        of set_credential's strict "must supply exactly the required keys"
        rejecting an intentionally-incomplete declaration outright."""
        if auth_type not in _REQUIRED_SECRET_KEYS:
            raise TenantToolCredentialError(f"Unknown auth_type '{auth_type}'.")
        if auth_type == "api_key" and not api_key_header_name:
            raise TenantToolCredentialError("api_key_header_name is required for auth_type=api_key.")

        self._get_tenant_tool_or_raise(tenant_id, tenant_tool_id)
        credential = self._get_credential_row(tenant_id, tenant_tool_id)
        if credential is None:
            credential = TenantToolCredential(tenant_id=tenant_id, tenant_tool_id=tenant_tool_id)
            self.db.add(credential)
        credential.auth_type = auth_type
        credential.api_key_header_name = api_key_header_name if auth_type == "api_key" else None
        credential.secrets_json_encrypted = None
        credential.rotated_by_user_id = actor_user_id
        self.db.commit()
        self.db.refresh(credential)
        return credential

    def update_api_key_header_name(
        self,
        tenant_id: str,
        tenant_tool_id: str,
        api_key_header_name: str,
    ) -> TenantToolCredential:
        self._get_tenant_tool_or_raise(tenant_id, tenant_tool_id)
        credential = self._get_credential_row(tenant_id, tenant_tool_id)
        if credential is None or credential.auth_type != "api_key":
            raise TenantToolCredentialError("api_key credential is not configured.")
        if not api_key_header_name:
            raise TenantToolCredentialError("api_key_header_name is required for auth_type=api_key.")
        credential.api_key_header_name = api_key_header_name
        self.db.commit()
        self.db.refresh(credential)
        return credential

    def get_masked(self, tenant_id: str, tenant_tool_id: str) -> CredentialMaskedView:
        self._get_tenant_tool_or_raise(tenant_id, tenant_tool_id)
        credential = self._get_credential_row(tenant_id, tenant_tool_id)
        if credential is None:
            return CredentialMaskedView(auth_type="none", configured=True, api_key_header_name=None)

        masked_fields: dict[str, str] = {}
        if credential.secrets_json_encrypted:
            for key, encrypted_value in json.loads(credential.secrets_json_encrypted).items():
                try:
                    masked_fields[key] = self._secrets.mask_secret(
                        self._secrets.decrypt_secret(encrypted_value)
                    )
                except SecretManagerError:
                    masked_fields[key] = "****"

        configured = credential.auth_type == "none" or bool(credential.secrets_json_encrypted)
        return CredentialMaskedView(
            auth_type=credential.auth_type,
            configured=configured,
            api_key_header_name=credential.api_key_header_name,
            masked_fields=masked_fields,
        )

    def resolve_for_execution(self, tenant_id: str, tenant_tool_id: str) -> ResolvedCredential:
        """Decrypts and returns raw secrets. Only CustomHttpToolExecutor may
        call this -- never import it from an API endpoint module."""
        self._get_tenant_tool_or_raise(tenant_id, tenant_tool_id)
        credential = self._get_credential_row(tenant_id, tenant_tool_id)
        if credential is None:
            return ResolvedCredential(auth_type="none", api_key_header_name=None, secrets={})

        secrets: dict[str, str] = {}
        if credential.secrets_json_encrypted:
            for key, encrypted_value in json.loads(credential.secrets_json_encrypted).items():
                secrets[key] = self._secrets.decrypt_secret(encrypted_value)
        return ResolvedCredential(
            auth_type=credential.auth_type,
            api_key_header_name=credential.api_key_header_name,
            secrets=secrets,
        )

    def is_configured_or_not_required(self, tenant_id: str, tenant_tool_id: str) -> bool:
        credential = self._get_credential_row(tenant_id, tenant_tool_id)
        if credential is None or credential.auth_type == "none":
            return True
        return bool(credential.secrets_json_encrypted)

    def delete_credential(self, tenant_id: str, tenant_tool_id: str, *, actor_user_id: str | None = None) -> None:
        self._get_tenant_tool_or_raise(tenant_id, tenant_tool_id)
        credential = self._get_credential_row(tenant_id, tenant_tool_id)
        if credential is None:
            return
        self.db.delete(credential)
        self.db.commit()
        IntegrationEventService(self.db).record_event(
            tenant_id=tenant_id,
            provider="custom_tool",
            event_type="tool_credential_deleted",
            status="success",
            resource_type="tenant_tool",
            resource_id=tenant_tool_id,
            metadata={"actor_user_id": actor_user_id},
        )

    def _get_tenant_tool_or_raise(self, tenant_id: str, tenant_tool_id: str) -> TenantTool:
        tool = self.db.scalar(
            select(TenantTool).where(
                TenantTool.id == tenant_tool_id, TenantTool.tenant_id == tenant_id
            )
        )
        if tool is None:
            raise TenantToolNotFoundError(tenant_tool_id)
        return tool

    def _get_credential_row(self, tenant_id: str, tenant_tool_id: str) -> TenantToolCredential | None:
        return self.db.scalar(
            select(TenantToolCredential).where(
                TenantToolCredential.tenant_id == tenant_id,
                TenantToolCredential.tenant_tool_id == tenant_tool_id,
            )
        )
