"""Ports of Integrations / Messaging. ``wiring.py`` binds them; application code depends on these only."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol

from app.modules.integrations.domain.chatwoot import ChatwootClientConfig
from app.modules.integrations.domain.whatsapp import WhatsAppClientConfig
from app.modules.integrations.domain.whatsapp_flow_context import ContextSchemaSnapshot


class SecretsPort(Protocol):
    def encrypt_secret(self, value: str) -> str: ...

    def decrypt_secret(self, value: str) -> str: ...


class FeatureGatePort(Protocol):
    def is_enabled(self, tenant_id: str, feature_key: str) -> bool: ...


class WhatsAppProviderPort(Protocol):
    """Meta WhatsApp Cloud API. Another BSP would implement the same surface."""

    def get_phone_number_info(self, config: WhatsAppClientConfig) -> dict[str, Any]: ...

    def get_message_templates(
        self, config: WhatsAppClientConfig, *, business_account_id: str, limit: int = 100
    ) -> dict[str, Any]: ...

    def send_template_message(
        self,
        config: WhatsAppClientConfig,
        *,
        to_phone: str,
        template_name: str,
        language: str,
        components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...

    def send_text_message(self, config: WhatsAppClientConfig, *, to_phone: str, message: str) -> dict[str, Any]: ...

    def create_message_template(
        self,
        config: WhatsAppClientConfig,
        *,
        waba_id: str,
        name: str,
        category: str,
        language: str,
        components: list[dict[str, Any]],
        parameter_format: str = "NAMED",
    ) -> dict[str, Any]: ...

    def update_message_template(
        self, config: WhatsAppClientConfig, *, provider_template_id: str, components: list[dict[str, Any]]
    ) -> dict[str, Any]: ...

    def delete_message_template(self, config: WhatsAppClientConfig, *, waba_id: str, name: str) -> dict[str, Any]: ...

    def get_message_template_status(
        self, config: WhatsAppClientConfig, *, provider_template_id: str
    ) -> dict[str, Any]: ...

    def create_flow(
        self,
        config: WhatsAppClientConfig,
        *,
        waba_id: str,
        name: str,
        categories: list[str],
        clone_flow_id: str | None = None,
    ) -> dict[str, Any]: ...

    def get_flow(self, config: WhatsAppClientConfig, *, flow_id: str) -> dict[str, Any]: ...

    def update_flow_metadata(
        self, config: WhatsAppClientConfig, *, flow_id: str, name: str, categories: list[str]
    ) -> dict[str, Any]: ...

    def upload_flow_json(
        self, config: WhatsAppClientConfig, *, flow_id: str, flow_json: dict[str, Any]
    ) -> dict[str, Any]: ...

    def list_flow_assets(self, config: WhatsAppClientConfig, *, flow_id: str) -> dict[str, Any]: ...

    def publish_flow(self, config: WhatsAppClientConfig, *, flow_id: str) -> dict[str, Any]: ...

    def deprecate_flow(self, config: WhatsAppClientConfig, *, flow_id: str) -> dict[str, Any]: ...

    def delete_flow(self, config: WhatsAppClientConfig, *, flow_id: str) -> dict[str, Any]: ...


class EmailProviderPort(Protocol):
    """Transactional email provider (Resend today). Returns the provider's email id."""

    def send_email(
        self,
        *,
        api_key: str,
        from_email: str,
        to_email: str,
        subject: str,
        html: str,
        text: str | None = None,
        reply_to: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        idempotency_key: str | None = None,
        tenant_id: str | None = None,
        lead_id: str | None = None,
        template_key: str | None = None,
    ) -> str: ...

    def send_test_email(
        self,
        *,
        api_key: str,
        from_email: str,
        to_email: str,
        reply_to: str | None = None,
        tenant_id: str | None = None,
    ) -> str: ...


class ChatwootProviderPort(Protocol):
    """Per-Account Chatwoot API. Built per tenant from a ``ChatwootClientConfig``."""

    def get_account_profile(self) -> dict: ...

    async def list_inboxes(self) -> list[dict]: ...

    async def list_teams(self) -> list[dict]: ...

    async def list_agents(self) -> list[dict]: ...

    async def create_inbox(self, *, name: str, webhook_url: str) -> dict: ...

    async def create_team(self, *, name: str, description: str | None = None) -> dict: ...

    async def invite_agent(self, *, name: str, email: str, role: str = "agent") -> dict: ...

    async def update_inbox(self, inbox_id: int, *, name: str) -> dict: ...

    async def update_team(
        self, team_id: int, *, name: str | None = None, description: str | None = None
    ) -> dict: ...

    async def delete_team(self, team_id: int) -> None: ...

    async def update_agent(self, agent_id: int, *, name: str | None = None, role: str | None = None) -> dict: ...

    async def delete_agent(self, agent_id: int) -> None: ...


ChatwootClientFactory = Callable[[ChatwootClientConfig], ChatwootProviderPort]


class ChatwootPlatformPort(Protocol):
    """Chatwoot Super-Admin Platform API used to provision managed accounts."""

    def create_account(self, *, name: str) -> dict: ...

    def create_user(self, *, name: str, email: str, password: str) -> dict: ...

    def link_account_user(self, *, account_id: int, user_id: int, role: str = "administrator") -> dict: ...

    def create_api_inbox(self, *, account_id: int, user_token: str, name: str, webhook_url: str) -> dict: ...

    def create_account_webhook(self, *, account_id: int, user_token: str, url: str) -> dict: ...


ChatwootPlatformFactory = Callable[[str, str], ChatwootPlatformPort]


class AssetStoragePort(Protocol):
    def read_bytes(self, storage_key: str) -> bytes: ...

    def tenant_object_key(self, tenant_slug: str, folder: str, object_id: str, filename: str) -> str: ...

    def upload_bytes(self, storage_key: str, content: bytes) -> Any: ...

    def delete(self, storage_key: str) -> Any: ...


class FormLinkPort(Protocol):
    def validate_active_links(self, tenant_id: str, lead_id: str, link_ids: Sequence[str]) -> list[str]:
        """Ids of the active form links of the lead. Raises ``ValueError`` if any is unavailable."""


class VoiceContextSchemaPort(Protocol):
    def get_schema_snapshot(self, tenant_id: str, schema_id: str) -> ContextSchemaSnapshot | None: ...


class CallSummaryPort(Protocol):
    def variables_for_lead(self, tenant_id: str, lead_id: str) -> dict[str, Any]: ...


class NotificationsPort(Protocol):
    """What Messaging needs from Notifications (bound to ``notifications.public`` in wiring)."""

    def delivery_exists(self, *, tenant_id: str, delivery_id: str) -> bool: ...

    def report_delivery_status(
        self,
        *,
        tenant_id: str,
        provider_message_id: str,
        status: str,
        occurred_at: Any,
        error_message: str | None,
    ) -> None: ...
