from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import TenantIntegration
from app.services.secret_manager_service import SecretManager


class IntegrationService:
    def __init__(self, db: Session, secret_manager: SecretManager | None = None) -> None:
        self.db = db
        self.secret_manager = secret_manager or SecretManager()

    def list_integrations(self, tenant_id: str) -> list[TenantIntegration]:
        return list(self.db.scalars(select(TenantIntegration).where(TenantIntegration.tenant_id == tenant_id)).all())

    def get_integration(self, tenant_id: str, provider: str) -> TenantIntegration | None:
        return self.db.scalar(
            select(TenantIntegration).where(
                TenantIntegration.tenant_id == tenant_id,
                TenantIntegration.provider == provider,
            )
        )

    def upsert_resend(
        self,
        *,
        tenant_id: str,
        display_name: str,
        config: dict,
        api_key: str | None,
    ) -> TenantIntegration:
        integration = self.get_integration(tenant_id, "resend")
        if integration is None:
            integration = TenantIntegration(
                tenant_id=tenant_id,
                provider="resend",
                display_name=display_name,
                status="inactive",
                config_json={},
            )
            self.db.add(integration)

        integration.display_name = display_name
        integration.config_json = config
        integration.status = "active"
        integration.last_error_message = None
        if api_key:
            integration.secrets_json_encrypted = self.secret_manager.encrypt_secret(json.dumps({"api_key": api_key}))
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def has_secret(self, integration: TenantIntegration | None) -> bool:
        return bool(integration and integration.secrets_json_encrypted)

    def get_secret_value(self, integration: TenantIntegration, key: str) -> str:
        if not integration.secrets_json_encrypted:
            raise ValueError("Integration secret is not configured.")
        decrypted = self.secret_manager.decrypt_secret(integration.secrets_json_encrypted)
        payload = json.loads(decrypted)
        value = payload.get(key)
        if not value:
            raise ValueError("Integration secret is not configured.")
        return value

    def mark_health(
        self,
        integration: TenantIntegration,
        *,
        status: str,
        error_message: str | None = None,
    ) -> None:
        integration.status = status
        integration.last_health_check_at = datetime.now(UTC)
        integration.last_error_message = error_message
        self.db.commit()
