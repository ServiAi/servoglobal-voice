from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.integrations import TenantChatwootConfig
from app.schemas.integrations import ChatwootConfigRequest, ChatwootConfigResponse, ChatwootTestResponse
from app.services.chatwoot_client import ChatwootClient, ChatwootClientConfig, ChatwootClientError, sanitize_chatwoot_error
from app.services.chatwoot_platform_client import ChatwootPlatformClient, ChatwootPlatformError
from app.services.integration_event_service import IntegrationEventService
from app.services.secret_manager_service import SecretManager

_WEBHOOK_PATH = "/api/v1/webhooks/chatwoot"
_DEFAULT_PLATFORM_BASE_URL = "https://crm.serviglobal-ia.com"


class ChatwootConfigService:
    provider = "chatwoot"

    def __init__(self, db: Session, secret_manager: SecretManager | None = None) -> None:
        self.db = db
        self.secret_manager = secret_manager or SecretManager()
        self.events = IntegrationEventService(db)

    def get_config(self, tenant_id: str) -> TenantChatwootConfig | None:
        return self.db.scalar(
            select(TenantChatwootConfig).where(
                TenantChatwootConfig.tenant_id == tenant_id,
                TenantChatwootConfig.provider == self.provider,
            )
        )

    def get_config_by_account_id(self, account_id: int) -> TenantChatwootConfig | None:
        return self.db.scalar(select(TenantChatwootConfig).where(TenantChatwootConfig.account_id == account_id))

    def get_config_by_webhook_key(self, webhook_key: str) -> TenantChatwootConfig | None:
        if not webhook_key:
            return None
        return self.db.scalar(select(TenantChatwootConfig).where(TenantChatwootConfig.webhook_key == webhook_key))

    def get_response(self, tenant_id: str) -> ChatwootConfigResponse:
        config = self.get_config(tenant_id)
        if config is None:
            return ChatwootConfigResponse(status="inactive", has_secret=False)
        return self.to_response(config)

    def to_response(self, config: TenantChatwootConfig) -> ChatwootConfigResponse:
        return ChatwootConfigResponse(
            mode=config.mode,
            status=config.status,
            base_url=config.base_url,
            account_id=config.account_id,
            default_inbox_id=config.default_inbox_id,
            has_secret=bool(config.api_token_encrypted),
            webhook_url=f"{_WEBHOOK_PATH}/{config.webhook_key}",
            last_health_check_at=config.last_health_check_at,
            last_error_message=config.last_error_message,
        )

    def upsert_config(self, tenant_id: str, request: ChatwootConfigRequest) -> ChatwootConfigResponse:
        config = self.get_config(tenant_id)
        if config is None and not request.api_token:
            raise ValueError("Chatwoot api_token is required for first configuration")

        if config is None:
            config = TenantChatwootConfig(
                tenant_id=tenant_id,
                provider=self.provider,
                webhook_key=secrets.token_urlsafe(32),
            )
            self.db.add(config)

        config.status = request.status
        config.base_url = request.base_url.strip().rstrip("/")
        config.account_id = request.account_id
        config.default_inbox_id = request.default_inbox_id
        config.last_error_message = None
        if request.api_token:
            config.api_token_encrypted = self.secret_manager.encrypt_secret(request.api_token)

        self.db.commit()
        self.db.refresh(config)
        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="chatwoot_config_updated",
            status="success",
            resource_type="tenant_chatwoot_config",
            resource_id=config.id,
        )
        return self.to_response(config)

    def get_active_client_config(self, tenant_id: str) -> tuple[TenantChatwootConfig, ChatwootClientConfig]:
        config = self.get_config(tenant_id)
        if config is None or config.status != "active" or not config.api_token_encrypted:
            raise ValueError("Chatwoot integration is not configured")
        token = self.secret_manager.decrypt_secret(config.api_token_encrypted)
        return config, ChatwootClientConfig(
            base_url=config.base_url,
            account_id=config.account_id,
            api_token=token,
            default_inbox_id=config.default_inbox_id,
        )

    def test_connection(self, tenant_id: str) -> ChatwootTestResponse:
        config = self.get_config(tenant_id)
        if config is None or not config.api_token_encrypted:
            return ChatwootTestResponse(status="failed", error_message="Chatwoot integration is not configured")

        try:
            _, client_config = self.get_active_client_config(tenant_id)
            ChatwootClient(client_config).get_account_profile()
        except (ValueError, ChatwootClientError) as exc:
            message = sanitize_chatwoot_error(str(exc)) or "Chatwoot test failed"
            config.last_health_check_at = datetime.now(UTC)
            config.last_error_message = message
            self.db.commit()
            self.events.record_event(
                tenant_id=tenant_id,
                provider=self.provider,
                event_type="chatwoot_test_connection",
                status="failed",
                resource_type="tenant_chatwoot_config",
                resource_id=config.id,
                message=message,
            )
            return ChatwootTestResponse(status="failed", error_message=message)

        config.last_health_check_at = datetime.now(UTC)
        config.last_error_message = None
        self.db.commit()
        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="chatwoot_test_connection",
            status="success",
            resource_type="tenant_chatwoot_config",
            resource_id=config.id,
        )
        return ChatwootTestResponse(status="success")

    def provision_managed_account(self, tenant_id: str, *, account_name: str) -> ChatwootConfigResponse:
        """Crea una Account, Agent Bot e inbox 'api' en Chatwoot vía Platform API
        y deja el tenant listo para operar sin que el operador pegue credenciales
        a mano. Requiere CHATWOOT_PLATFORM_API_TOKEN y BACKEND_PUBLIC_BASE_URL."""
        existing = self.get_config(tenant_id)
        if existing is not None and existing.status == "active":
            raise ValueError("Chatwoot integration is already configured for this tenant")
        if not settings.CHATWOOT_PLATFORM_API_TOKEN:
            raise ValueError("CHATWOOT_PLATFORM_API_TOKEN is not configured")
        if not settings.BACKEND_PUBLIC_BASE_URL:
            raise ValueError("BACKEND_PUBLIC_BASE_URL is not configured")

        is_new = existing is None
        webhook_key = existing.webhook_key if existing else secrets.token_urlsafe(32)
        config = existing or TenantChatwootConfig(tenant_id=tenant_id, provider=self.provider, webhook_key=webhook_key)

        webhook_url = f"{settings.BACKEND_PUBLIC_BASE_URL.rstrip('/')}{_WEBHOOK_PATH}/{webhook_key}"
        platform = ChatwootPlatformClient(_DEFAULT_PLATFORM_BASE_URL, settings.CHATWOOT_PLATFORM_API_TOKEN)

        account_id: int | None = None
        try:
            account = platform.create_account(name=account_name)
            account_id = int(account["id"])
            bot = platform.create_agent_bot(
                name=f"{account_name} Bot", account_id=account_id, outgoing_url=webhook_url
            )
            agent_bot_id = int(bot["id"])
            agent_bot_token = str(bot["access_token"])
            inbox = platform.create_api_inbox(
                account_id=account_id, agent_bot_token=agent_bot_token, name=account_name, webhook_url=webhook_url
            )
            inbox_id = int(inbox.get("id") or (inbox.get("inbox") or {}).get("id"))
            platform.set_inbox_agent_bot(
                account_id=account_id, agent_bot_token=agent_bot_token, inbox_id=inbox_id, agent_bot_id=agent_bot_id
            )
        except (ChatwootPlatformError, KeyError, TypeError, ValueError) as exc:
            message = sanitize_chatwoot_error(str(exc)) or "Chatwoot auto-provisioning failed"
            if is_new and account_id is None:
                # Nada se llego a crear en Chatwoot (fallo en create_account): no hay
                # account_id valido que persistir (columna NOT NULL), y no tiene sentido
                # dejar un registro "error" sin ninguna Account real detras.
                raise ValueError(message) from exc
            if is_new:
                self.db.add(config)
            config.mode = "managed"
            config.status = "error"
            config.base_url = _DEFAULT_PLATFORM_BASE_URL
            if account_id is not None:
                config.account_id = account_id
            config.last_error_message = message
            config.last_health_check_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(config)
            self.events.record_event(
                tenant_id=tenant_id,
                provider=self.provider,
                event_type="chatwoot_managed_provision",
                status="failed",
                resource_type="tenant_chatwoot_config",
                resource_id=config.id,
                message=message,
            )
            raise ValueError(message) from exc

        if is_new:
            self.db.add(config)
        config.mode = "managed"
        config.status = "active"
        config.base_url = _DEFAULT_PLATFORM_BASE_URL
        config.account_id = account_id
        config.default_inbox_id = inbox_id
        config.platform_agent_bot_id = agent_bot_id
        config.api_token_encrypted = self.secret_manager.encrypt_secret(agent_bot_token)
        config.last_error_message = None
        config.last_health_check_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(config)
        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="chatwoot_managed_provision",
            status="success",
            resource_type="tenant_chatwoot_config",
            resource_id=config.id,
        )
        return self.to_response(config)
