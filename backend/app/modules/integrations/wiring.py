"""Composition root of Integrations / Messaging: binds its ports to the rest of the platform.

The only place that knows how to answer "does this tenant exist?", "what is the Voice /
Scheduling catalog status?", where files are stored, how secrets are decrypted and which
legacy services still back Forms, voice-context schemas and call summaries.
Application code depends on the Protocols in ``application/ports.py`` only.

Temporary legacy exceptions (allowlisted in ``test_integrations_boundaries``):
Identity (``OnboardingService``), Voice Legacy (``VoiceConfigService``), Forms
(``TenantFormToken``), Voice Context (``TenantVoiceContextSchema``), the shared
``SecretManager`` / ``StorageService`` / ``TenantFeatureService`` / ``CallSummaryService``.
Each disappears behind that module's ``public.py`` when it is migrated.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.modules.integrations.domain.catalog import CatalogFacts


@dataclass(frozen=True)
class TenantRef:
    id: str
    name: str
    slug: str


def require_tenant(db: Session, tenant_id: str) -> TenantRef:
    """Identity legacy lookup. Raises ``ValueError`` (same message as before) if missing."""
    from app.services.onboarding_service import OnboardingService

    tenant = OnboardingService(db).get_tenant(tenant_id)
    return TenantRef(id=tenant.id, name=tenant.name, slug=tenant.slug)


def foreign_catalog_inputs(db: Session, tenant_id: str, selected: set[str]) -> dict[str, CatalogFacts]:
    """Catalog facts for providers whose configuration is owned by Voice or Scheduling."""
    facts: dict[str, CatalogFacts] = {}
    if "voice" in selected:
        from app.services.voice_config_service import VoiceConfigService

        config = VoiceConfigService(db).get_provider_config(tenant_id)
        facts["voice"] = CatalogFacts(
            configured=config is not None,
            provider_status=config.status if config else None,
            has_error=bool(config and config.last_error_message),
        )
    if "calcom" in selected or "google_calendar" in selected:
        from app.modules.scheduling.public import SchedulingFacade

        scheduling = SchedulingFacade(db).catalog_status_inputs(tenant_id)
        if "calcom" in selected:
            item = scheduling["calcom"]
            facts["calcom"] = CatalogFacts(item["configured"], item["status"], item["has_error"])
        if "google_calendar" in selected:
            item = scheduling["google_calendar"]
            facts["google_calendar"] = CatalogFacts(
                item["configured"], "connected" if item["connected"] else None, item["has_error"]
            )
    return facts


# --- provider / platform ports ----------------------------------------------------------------


def default_secrets():
    from app.services.secret_manager_service import SecretManager

    return SecretManager()


def default_features(db: Session):
    from app.services.tenant_feature_service import TenantFeatureService

    return TenantFeatureService(db)


def default_whatsapp_provider():
    from app.modules.integrations.infrastructure.whatsapp.meta_client import WhatsAppCloudClient

    return WhatsAppCloudClient()


def default_email_provider():
    from app.modules.integrations.infrastructure.email.resend import ResendService

    return ResendService()


def default_chatwoot_client_factory():
    def build(config):
        from app.modules.integrations.infrastructure.chatwoot.client import ChatwootClient

        return ChatwootClient(config)

    return build


def default_chatwoot_platform_factory():
    def build(base_url: str, platform_token: str):
        from app.modules.integrations.infrastructure.chatwoot.platform_client import ChatwootPlatformClient

        return ChatwootPlatformClient(base_url, platform_token)

    return build


def default_asset_storage():
    from app.services.storage_service import StorageService

    return StorageService()


# --- legacy adapters (Forms, Voice context, call summaries) --------------------------------------


class LegacyFormLinks:
    """FormLinkPort over the not-yet-migrated Forms tables."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def validate_active_links(self, tenant_id: str, lead_id: str, link_ids) -> list[str]:
        from sqlalchemy import select

        from app.models.integrations import TenantFormToken

        if not link_ids:
            return []
        tokens = list(
            self.db.scalars(
                select(TenantFormToken).where(
                    TenantFormToken.tenant_id == tenant_id,
                    TenantFormToken.lead_id == lead_id,
                    TenantFormToken.id.in_(list(link_ids)),
                    TenantFormToken.status == "active",
                )
            ).all()
        )
        if len(tokens) != len(set(link_ids)):
            raise ValueError("One or more form links are not available for this lead.")
        return [token.id for token in tokens]


class LegacyVoiceContextSchemas:
    """VoiceContextSchemaPort over the not-yet-public Voice context schema tables."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_schema_snapshot(self, tenant_id: str, schema_id: str):
        from sqlalchemy import select

        from app.models.voice_context import TenantVoiceContextSchema
        from app.modules.integrations.domain.whatsapp_flow_context import (
            ContextFieldSnapshot,
            ContextSchemaSnapshot,
        )

        schema = self.db.scalar(
            select(TenantVoiceContextSchema).where(
                TenantVoiceContextSchema.id == schema_id,
                TenantVoiceContextSchema.tenant_id == tenant_id,
            )
        )
        if schema is None:
            return None
        return ContextSchemaSnapshot(
            id=schema.id,
            schema_key=schema.schema_key,
            version=schema.version,
            name=schema.name,
            description=schema.description,
            fields=tuple(
                ContextFieldSnapshot(
                    key=field.key,
                    label=field.label,
                    description=field.description,
                    field_type=field.field_type,
                    collection_mode=field.collection_mode,
                    required=field.required,
                    position=field.position,
                    options=tuple(field.options_json or ()),
                )
                for field in schema.fields
            ),
        )


def default_form_links(db: Session):
    return LegacyFormLinks(db)


def default_voice_context(db: Session):
    return LegacyVoiceContextSchemas(db)


def default_call_summary(db: Session):
    from app.services.call_summary_service import CallSummaryService

    return CallSummaryService(db)


class PublicNotifications:
    """NotificationsPort over ``notifications.public`` (resolved at call time)."""

    def delivery_exists(self, *, tenant_id: str, delivery_id: str) -> bool:
        from app.modules.notifications import public

        return public.delivery_exists(tenant_id=tenant_id, delivery_id=delivery_id)

    def report_delivery_status(self, *, tenant_id, provider_message_id, status, occurred_at, error_message) -> None:
        from app.modules.notifications import public

        public.report_delivery_status(
            tenant_id=tenant_id,
            provider_message_id=provider_message_id,
            status=status,
            occurred_at=occurred_at,
            error_message=error_message,
        )


def default_notifications():
    return PublicNotifications()
