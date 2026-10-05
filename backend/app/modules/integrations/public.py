"""Integrations / Messaging -- public API.

The only door into the module: DTOs are frozen dataclasses (no ORM, no provider
objects) and every implementation import is lazy, so importing this module loads
neither SQLAlchemy models, FastAPI, ``httpx`` nor any provider client.

Facades: ``IntegrationsFacade`` (catalog on/off), ``IntegrationEvents`` (audit trail),
``WhatsAppFacade``, ``EmailFacade``, ``ChatwootFacade``. Module-level helpers serve
Notifications (template contract, delivery evidence, error sanitizer).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session

__all__ = [
    "ChatwootFacade",
    "ChatwootGateway",
    "EmailAssetRef",
    "EmailFacade",
    "IntegrationAvailability",
    "IntegrationEventRecord",
    "IntegrationEventSummary",
    "IntegrationEvents",
    "IntegrationsFacade",
    "LeadEmailResult",
    "LeadWhatsAppResult",
    "WhatsAppDeliveryEvidence",
    "WhatsAppFacade",
    "WhatsAppMessageReceipt",
    "WhatsAppMessageView",
    "WhatsAppSendOutcome",
    "WhatsAppTemplateContract",
    "WhatsAppTransportPort",
    "find_whatsapp_delivery_evidence",
    "get_whatsapp_template",
    "sanitize_whatsapp_error",
]


# --- DTOs -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class WhatsAppTemplateContract:
    """What a caller may rely on about a tenant's template. Parameter keys
    are only resolved for approved templates (empty otherwise)."""

    template_key: str
    status: str
    approved_parameter_keys: tuple[str, ...]
    body: str = ""

    @property
    def is_approved(self) -> bool:
        return self.status == "approved"

    @property
    def required_variables(self) -> tuple[str, ...]:
        return self.approved_parameter_keys


@dataclass(frozen=True)
class WhatsAppMessageReceipt:
    id: str
    tenant_id: str
    template_id: str | None
    status: str
    metadata_json: Mapping[str, Any]
    lead_id: str | None
    contact_id: str | None
    error_message: str | None
    notification_delivery_id: str | None
    delivered_at: datetime | None
    read_at: datetime | None


@dataclass(frozen=True)
class WhatsAppSendOutcome:
    status: str
    provider_message_id: str | None
    message_id: str | None = None
    message: WhatsAppMessageReceipt | None = None


@dataclass(frozen=True)
class WhatsAppDeliveryEvidence:
    id: str
    status: str
    provider_message_id: str | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class LeadWhatsAppResult:
    status: str
    whatsapp_message_id: str | None = None
    provider_message_id: str | None = None
    preview: Mapping[str, Any] | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class WhatsAppMessageView:
    id: str
    direction: str
    status: str
    created_at: datetime
    lead_id: str | None = None
    contact_id: str | None = None
    template_key: str | None = None
    provider_message_id: str | None = None
    to_phone: str | None = None
    from_phone: str | None = None
    message_preview: str | None = None
    error_message: str | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    failed_at: datetime | None = None


@dataclass(frozen=True)
class LeadEmailResult:
    status: str
    email_send_id: str | None = None
    provider_email_id: str | None = None
    preview: Mapping[str, Any] | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class EmailAssetRef:
    id: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    status: str


@dataclass(frozen=True)
class IntegrationAvailability:
    provider: str
    enabled: bool


@dataclass(frozen=True)
class IntegrationEventRecord:
    event_type: str
    provider: str
    status: str
    created_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IntegrationEventSummary:
    counts: Mapping[str, int]
    recent: tuple[IntegrationEventRecord, ...]


class WhatsAppTransportPort(Protocol):
    def send_template_message(
        self, config: object, *, to_phone: str, template_name: str, language: str, components: list[dict[str, Any]]
    ) -> dict[str, Any]: ...


# --- Facades --------------------------------------------------------------------------------------


class IntegrationsFacade:
    """Which integrations a tenant has enabled (the on/off switch only)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def is_enabled(self, tenant_id: str, provider: str) -> bool:
        from app.modules.integrations.application.integration_service import (
            IntegrationService,
        )

        return IntegrationService(self.db).is_enabled(tenant_id, provider)

    def list_availability(self, tenant_id: str) -> tuple[IntegrationAvailability, ...]:
        from app.modules.integrations.application.integration_service import (
            IntegrationService,
        )

        return tuple(
            IntegrationAvailability(provider=item["provider"], enabled=bool(item["enabled"]))
            for item in IntegrationService(self.db).list_availability(tenant_id)
        )

    def detach_lead_references(
        self, *, tenant_id: str, lead_ids: Sequence[str], contact_ids: Sequence[str]
    ) -> None:
        """Null the lead/contact references of WhatsApp messages and email sends (CRM deletes the rows).
        Part of the caller's transaction: nothing is committed here."""
        from app.modules.integrations.application.lead_references import (
            detach_lead_references,
        )

        detach_lead_references(self.db, tenant_id=tenant_id, lead_ids=lead_ids, contact_ids=contact_ids)


class IntegrationEvents:
    """The audit trail (``tenant_integration_events``). Metadata is sanitized before persisting:
    secrets, payloads, HTML/text bodies, phones and emails are never stored."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        tenant_id: str,
        provider: str,
        event_type: str,
        status: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        message: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Persist the event in its own commit."""
        from app.modules.integrations.application.event_service import (
            IntegrationEventService,
        )

        IntegrationEventService(self.db).record_event(
            tenant_id=tenant_id,
            provider=provider,
            event_type=event_type,
            status=status,
            resource_type=resource_type,
            resource_id=resource_id,
            message=message,
            metadata=dict(metadata) if metadata else None,
        )

    def add(
        self,
        *,
        tenant_id: str,
        provider: str,
        event_type: str,
        status: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        message: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Add the event to the caller's transaction (not committed)."""
        from app.modules.integrations.application.event_service import (
            IntegrationEventService,
        )

        IntegrationEventService(self.db).add_event(
            tenant_id=tenant_id,
            provider=provider,
            event_type=event_type,
            status=status,
            resource_type=resource_type,
            resource_id=resource_id,
            message=message,
            metadata=dict(metadata) if metadata else None,
        )

    def summarize(
        self,
        *,
        tenant_id: str,
        providers: Sequence[str],
        event_types: Sequence[str],
        date_from: datetime,
        date_to: datetime,
        recent_limit: int = 10,
    ) -> IntegrationEventSummary:
        from app.modules.integrations.application.event_service import (
            IntegrationEventService,
        )

        counts, rows = IntegrationEventService(self.db).summarize(
            tenant_id=tenant_id,
            providers=providers,
            event_types=event_types,
            date_from=date_from,
            date_to=date_to,
            recent_limit=recent_limit,
        )
        return IntegrationEventSummary(
            counts=counts,
            recent=tuple(
                IntegrationEventRecord(
                    event_type=row.event_type,
                    provider=row.provider,
                    status=row.status,
                    created_at=row.created_at,
                    metadata=dict(row.metadata_json or {}),
                )
                for row in rows
            ),
        )


def _receipt(message: Any) -> WhatsAppMessageReceipt:
    return WhatsAppMessageReceipt(
        id=message.id,
        tenant_id=message.tenant_id,
        template_id=message.template_id,
        status=message.status,
        metadata_json=dict(message.metadata_json or {}),
        lead_id=message.lead_id,
        contact_id=message.contact_id,
        error_message=message.error_message,
        notification_delivery_id=message.notification_delivery_id,
        delivered_at=message.delivered_at,
        read_at=message.read_at,
    )


def _message_view(message: Any) -> WhatsAppMessageView:
    return WhatsAppMessageView(
        id=message.id,
        direction=message.direction,
        status=message.status,
        created_at=message.created_at,
        lead_id=message.lead_id,
        contact_id=message.contact_id,
        template_key=message.template_key,
        provider_message_id=message.provider_message_id,
        to_phone=message.to_phone,
        from_phone=message.from_phone,
        message_preview=message.message_preview,
        error_message=message.error_message,
        sent_at=message.sent_at,
        delivered_at=message.delivered_at,
        read_at=message.read_at,
        failed_at=message.failed_at,
    )


class WhatsAppFacade:
    def __init__(self, db: Session, *, transport: WhatsAppTransportPort | None = None) -> None:
        self.db = db
        self._transport = transport

    def _messages(self):
        from app.modules.integrations.application.whatsapp.message_service import (
            WhatsAppMessageService,
        )

        return WhatsAppMessageService(self.db, client=self._transport)

    def is_configured(self, tenant_id: str) -> bool:
        """Same resolution WhatsApp sends use at call time."""
        from app.modules.integrations.application.whatsapp.config_service import (
            WhatsAppConfigService,
        )

        try:
            WhatsAppConfigService(self.db).get_active_client_config(tenant_id)
            return True
        except ValueError:
            return False

    def get_approved_template_contract(self, tenant_id: str, template_key: str) -> WhatsAppTemplateContract | None:
        """None if the tenant has no such template. Raises ValueError if an
        approved template's parameters are malformed."""
        from app.modules.integrations.application.whatsapp.template_service import (
            WhatsAppTemplateService,
        )

        service = WhatsAppTemplateService(self.db)
        row = service.find_by_key(tenant_id, template_key)
        if row is None:
            return None
        keys = service.get_approved_parameter_keys(row) if row.status == "approved" else []
        return WhatsAppTemplateContract(
            template_key=row.template_key,
            status=row.status,
            approved_parameter_keys=tuple(keys),
            body=row.body or "",
        )

    def send_template(
        self,
        *,
        tenant_id: str,
        to_phone: str,
        template_key: str,
        variables: dict[str, str],
        metadata: dict[str, Any],
        lead_id: str | None,
        contact_id: str | None,
        notification_delivery_id: str | None = None,
    ) -> WhatsAppSendOutcome:
        """Raises ValueError on configuration/provider failures."""
        result = self._messages().send_template_notification(
            tenant_id=tenant_id,
            to_phone=to_phone,
            template_key=template_key,
            variables=variables,
            metadata=metadata,
            notification_delivery_id=notification_delivery_id,
            lead_id=lead_id,
            contact_id=contact_id,
        )
        return WhatsAppSendOutcome(
            status=result.status,
            provider_message_id=result.provider_message_id,
            message_id=result.message.id if result.message else None,
            message=_receipt(result.message) if result.message else None,
        )

    def preview_lead_message(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        template_key: str,
        message: str | None = None,
        variables: Mapping[str, Any] | None = None,
    ) -> LeadWhatsAppResult:
        """Raises ValueError ("Lead not found", missing phone, unknown template...)."""
        result = self._messages().preview_lead_whatsapp(
            tenant_id, lead_id, template_key=template_key, message_text=message, variables=dict(variables or {})
        )
        return LeadWhatsAppResult(status=result.status, preview=result.preview, error_message=result.error_message)

    def send_lead_message(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        template_key: str,
        message: str | None = None,
        variables: Mapping[str, Any] | None = None,
    ) -> LeadWhatsAppResult:
        """Raises ValueError on configuration/validation failures; provider failures come back as ``failed``."""
        result = self._messages().send_lead_whatsapp(
            tenant_id, lead_id, template_key=template_key, message_text=message, variables=dict(variables or {})
        )
        return LeadWhatsAppResult(
            status=result.status,
            whatsapp_message_id=result.message.id if result.message else None,
            provider_message_id=result.provider_message_id,
            preview=result.preview,
            error_message=result.error_message,
        )

    def list_lead_messages(self, tenant_id: str, lead_id: str) -> tuple[WhatsAppMessageView, ...]:
        """Raises ValueError("Lead not found")."""
        return tuple(_message_view(message) for message in self._messages().list_lead_messages(tenant_id, lead_id))


def _email_result(result: Any) -> LeadEmailResult:
    return LeadEmailResult(
        status=result.status,
        email_send_id=result.email_send_id,
        provider_email_id=result.provider_email_id,
        preview=result.preview,
        error_message=result.error_message,
    )


class EmailFacade:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _sends(self):
        from app.modules.integrations.application.email.send_service import (
            EmailSendService,
        )

        return EmailSendService(self.db)

    def preview_lead_email(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        template_key: str,
        subject: str | None = None,
        message: str | None = None,
        content_format: str | None = None,
        content: str | None = None,
        asset_ids: Sequence[str] | None = None,
        form_token_ids: Sequence[str] | None = None,
    ) -> LeadEmailResult:
        """Render without sending or persisting. Raises ValueError."""
        result = self._sends().preview_lead_email(
            tenant_id=tenant_id,
            lead_id=lead_id,
            template_key=template_key,
            subject=subject,
            message=message,
            content_format=content_format,
            content=content,
            asset_ids=list(asset_ids) if asset_ids else None,
            form_token_ids=list(form_token_ids) if form_token_ids else None,
        )
        return _email_result(result)

    def send_lead_email(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        template_key: str,
        subject: str | None = None,
        message: str | None = None,
        content_format: str | None = None,
        content: str | None = None,
        asset_ids: Sequence[str] | None = None,
        form_token_ids: Sequence[str] | None = None,
    ) -> LeadEmailResult:
        """Raises ValueError ("Lead not found", missing email/config...); provider failures come back as ``failed``."""
        result = self._sends().send_lead_email(
            tenant_id=tenant_id,
            lead_id=lead_id,
            template_key=template_key,
            subject=subject,
            message=message,
            content_format=content_format,
            content=content,
            asset_ids=list(asset_ids) if asset_ids else None,
            form_token_ids=list(form_token_ids) if form_token_ids else None,
        )
        return _email_result(result)

    def create_asset(
        self,
        *,
        tenant_id: str,
        uploaded_by_user_id: str | None,
        filename: str,
        mime_type: str,
        content: bytes,
        folder: str = "assets",
    ) -> EmailAssetRef:
        from app.modules.integrations.application.email.asset_service import (
            EmailAssetService,
        )

        asset = EmailAssetService(self.db).create_asset(
            tenant_id=tenant_id,
            uploaded_by_user_id=uploaded_by_user_id,
            filename=filename,
            mime_type=mime_type,
            content=content,
            folder=folder,
        )
        return EmailAssetRef(
            id=asset.id,
            original_filename=asset.original_filename,
            mime_type=asset.mime_type,
            file_size_bytes=asset.file_size_bytes,
            status=asset.status,
        )


class ChatwootGateway:
    """A tenant's Chatwoot Account, ready to use. Only the operations other modules need;
    credentials and the HTTP client stay inside the module."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def get_or_create_contact(self, phone: str, name: str = "", email: str = "") -> int | None:
        return await self._client.get_or_create_contact(phone, name, email)

    async def get_or_create_conversation(self, contact_id: int, inbox_id: int | None = None) -> int | None:
        return await self._client.get_or_create_conversation(contact_id, inbox_id=inbox_id)

    async def assign_team(self, conversation_id: int, team_id: int) -> bool:
        return await self._client.assign_team(conversation_id, team_id)

    async def send_message(self, conversation_id: int, content: str, private: bool = False) -> bool:
        return await self._client.send_message(conversation_id, content, private=private)

    async def add_label(self, conversation_id: int, labels: list[str]) -> bool:
        return await self._client.add_label(conversation_id, labels)


class ChatwootFacade:
    def __init__(self, db: Session) -> None:
        self.db = db

    def gateway_for(self, tenant_id: str) -> ChatwootGateway:
        """Raises ValueError if the tenant has no active Chatwoot configuration."""
        from app.modules.integrations import wiring
        from app.modules.integrations.application.chatwoot.config_service import (
            ChatwootConfigService,
        )

        _, client_config = ChatwootConfigService(self.db).get_active_client_config(tenant_id)
        return ChatwootGateway(wiring.default_chatwoot_client_factory()(client_config))


# --- Helpers used by Notifications ----------------------------------------------------------------


def get_whatsapp_template(*, tenant_id: str, template_key: str | None) -> WhatsAppTemplateContract:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        if not template_key:
            raise ValueError("template_key_required")
        contract = WhatsAppFacade(db).get_approved_template_contract(tenant_id, template_key)
        if contract is None or not contract.is_approved:
            raise ValueError("approved_template_not_found")
        return contract
    finally:
        db.close()


def find_whatsapp_delivery_evidence(
    *, tenant_id: str, delivery_id: str, fallback_message_id: str | None = None
) -> WhatsAppDeliveryEvidence | None:
    from app.db.session import SessionLocal
    from app.modules.integrations.application.whatsapp.evidence import (
        find_delivery_message,
    )

    db = SessionLocal()
    try:
        message = find_delivery_message(
            db, tenant_id=tenant_id, delivery_id=delivery_id, fallback_message_id=fallback_message_id
        )
        if message is None:
            return None
        return WhatsAppDeliveryEvidence(
            id=message.id,
            status=message.status,
            provider_message_id=message.provider_message_id,
            sent_at=message.sent_at,
            delivered_at=message.delivered_at,
            read_at=message.read_at,
            created_at=message.created_at,
        )
    finally:
        db.close()


def sanitize_whatsapp_error(value: str | None) -> str | None:
    from app.modules.integrations.domain.whatsapp import (
        sanitize_whatsapp_error as sanitize,
    )

    return sanitize(value)
