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


def require_tenant(db: Session, tenant_id: str) -> TenantRef:
    """Identity legacy lookup. Raises ``ValueError`` (same message as before) if missing."""
    from app.services.onboarding_service import OnboardingService

    tenant = OnboardingService(db).get_tenant(tenant_id)
    return TenantRef(id=tenant.id, name=tenant.name)


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
