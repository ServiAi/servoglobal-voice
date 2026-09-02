from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.integrations import TenantChatwootConfig
from app.schemas.integrations import (
    ChatwootConfigRequest,
    ChatwootConfigResponse,
    ChatwootInboxSummary,
    ChatwootTeamSummary,
    ChatwootTestResponse,
)
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
            account_name=config.account_name,
            default_inbox_id=config.default_inbox_id,
            default_inbox_name=config.default_inbox_name,
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
            account_payload = ChatwootClient(client_config).get_account_profile()
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

        account_name = account_payload.get("name") if isinstance(account_payload, dict) else None
        if isinstance(account_name, str) and account_name:
            config.account_name = account_name
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
        """Crea una Account, un usuario administrator dedicado, un inbox 'api' y el
        webhook de cuenta en Chatwoot vía Platform API, dejando al tenant operativo
        sin que el operador pegue credenciales a mano. Requiere CHATWOOT_PLATFORM_API_TOKEN
        y BACKEND_PUBLIC_BASE_URL.

        No usa Agent Bots: verificado contra la instancia real que su access_token
        no tiene permiso ni para crear un contacto ("Access to this endpoint is not
        authorized for bots"). El usuario administrator es el mismo tipo de credencial
        que el operador crea a mano hoy en modo "external"."""
        existing = self.get_config(tenant_id)
        if existing is not None and existing.status == "active":
            raise ValueError("Chatwoot integration is already configured for this tenant")
        if (
            existing is not None
            and existing.mode == "managed"
            and existing.account_id
            and existing.api_token_encrypted
        ):
            # Ya se aprovisiono antes y se desconecto: reactivar en vez de crear
            # una Account/usuario/inbox duplicados en Chatwoot.
            existing.status = "active"
            existing.last_error_message = None
            existing.last_health_check_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(existing)
            self.events.record_event(
                tenant_id=tenant_id,
                provider=self.provider,
                event_type="chatwoot_managed_reactivated",
                status="success",
                resource_type="tenant_chatwoot_config",
                resource_id=existing.id,
            )
            return self.to_response(existing)
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
            user_password = secrets.token_urlsafe(24) + "Aa1!"
            user = platform.create_user(
                name=f"{account_name} (managed)",
                email=f"chatwoot-managed+{account_id}@serviglobal-ia.com",
                password=user_password,
            )
            user_id = int(user["id"])
            user_token = str(user["access_token"])
            platform.link_account_user(account_id=account_id, user_id=user_id, role="administrator")
            inbox_name = "Conversaciones"
            inbox = platform.create_api_inbox(
                account_id=account_id, user_token=user_token, name=inbox_name, webhook_url=webhook_url
            )
            inbox_id = int(inbox.get("id") or (inbox.get("inbox") or {}).get("id"))
            platform.create_account_webhook(account_id=account_id, user_token=user_token, url=webhook_url)
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
        config.account_name = account_name
        config.default_inbox_id = inbox_id
        config.default_inbox_name = inbox_name
        config.api_token_encrypted = self.secret_manager.encrypt_secret(user_token)
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

    def disconnect(self, tenant_id: str) -> ChatwootConfigResponse:
        """Desactiva la integracion sin borrar la configuracion (Account, token,
        webhook_key se conservan) para que reconectar despues sea inmediato."""
        config = self.get_config(tenant_id)
        if config is None:
            raise ValueError("Chatwoot integration is not configured for this tenant")
        config.status = "inactive"
        config.last_error_message = None
        self.db.commit()
        self.db.refresh(config)
        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="chatwoot_disconnected",
            status="success",
            resource_type="tenant_chatwoot_config",
            resource_id=config.id,
        )
        return self.to_response(config)

    async def list_inboxes(self, tenant_id: str) -> list[ChatwootInboxSummary]:
        """Usado para poblar el selector de inbox del handoff de voz->humano."""
        _, client_config = self.get_active_client_config(tenant_id)
        inboxes = await ChatwootClient(client_config).list_inboxes()
        return [
            ChatwootInboxSummary(
                id=inbox["id"], name=inbox.get("name") or f"Inbox {inbox['id']}", channel_type=inbox.get("channel_type")
            )
            for inbox in inboxes
        ]

    async def list_teams(self, tenant_id: str) -> list[ChatwootTeamSummary]:
        """Usado para poblar el selector de team del handoff de voz->humano."""
        _, client_config = self.get_active_client_config(tenant_id)
        teams = await ChatwootClient(client_config).list_teams()
        return [ChatwootTeamSummary(id=team["id"], name=team.get("name") or f"Team {team['id']}") for team in teams]
