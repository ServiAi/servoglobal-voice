from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import (
    TenantAgentSchedulingConfig,
    TenantBookingConfig,
    TenantGoogleCalendarConnection,
    TenantSchedulingEventType,
)
from app.services.booking_config_service import BookingConfigService
from app.services.calcom_client import CalComClient, CalComClientConfig
from app.services.calcom_scheduling_admin_provider import CalComSchedulingAdminProvider
from app.services.google_scheduling_admin_provider import GoogleSchedulingAdminProvider
from app.services.scheduling_protocols import SchedulingAdminProvider, SchedulingProvider
from app.services.scheduling_provider import CalComProvider, GoogleCalendarProvider

logger = logging.getLogger(__name__)


class SchedulingProviderResolver:
    """Central resolver for runtime and admin scheduling providers across ServiGlobal."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.config_service = BookingConfigService(db)

    def resolve_admin_provider(self, tenant_id: str, provider: str | None = None) -> SchedulingAdminProvider:
        resolved_provider = provider or self._detect_active_provider(tenant_id)
        if resolved_provider == "calcom":
            return CalComSchedulingAdminProvider(self.db, tenant_id)
        return GoogleSchedulingAdminProvider(self.db, tenant_id)

    def resolve_runtime_provider(
        self,
        tenant_id: str,
        *,
        agent_id: str | None = None,
        event_type_id: str | None = None,
        provider: str | None = None,
    ) -> tuple[SchedulingProvider, str]:
        resolved_provider = provider

        # 1. Resolve from Event Type if specified
        if not resolved_provider and event_type_id:
            et = self.db.scalar(
                select(TenantSchedulingEventType).where(
                    TenantSchedulingEventType.tenant_id == tenant_id,
                    TenantSchedulingEventType.id == event_type_id,
                )
            )
            if et:
                resolved_provider = et.provider

        # 2. Resolve from Agent Config if specified
        if not resolved_provider and agent_id:
            agent_cfg = self.db.scalar(
                select(TenantAgentSchedulingConfig).where(
                    TenantAgentSchedulingConfig.tenant_id == tenant_id,
                    TenantAgentSchedulingConfig.agent_id == agent_id,
                )
            )
            if agent_cfg:
                if agent_cfg.event_type_id:
                    et = self.db.scalar(
                        select(TenantSchedulingEventType).where(
                            TenantSchedulingEventType.tenant_id == tenant_id,
                            TenantSchedulingEventType.id == agent_cfg.event_type_id,
                        )
                    )
                    if et:
                        resolved_provider = et.provider
                if not resolved_provider:
                    resolved_provider = agent_cfg.provider

        # 3. Fallback to tenant's active provider
        if not resolved_provider:
            resolved_provider = self._detect_active_provider(tenant_id)

        # 4. Instantiate provider
        if resolved_provider == "calcom":
            cal_cfg = self.config_service.get_config(tenant_id, provider="calcom")
            api_key = ""
            if cal_cfg and cal_cfg.cal_api_key_encrypted:
                api_key = self.config_service.secret_manager.decrypt_secret(cal_cfg.cal_api_key_encrypted) or ""
            client_config = CalComClientConfig(
                api_key=api_key,
                event_type_id=cal_cfg.default_event_type_id if cal_cfg else None,
                event_type_slug=cal_cfg.default_event_type_slug if cal_cfg else None,
                username=cal_cfg.default_username if cal_cfg else None,
                team_slug=cal_cfg.default_team_slug if cal_cfg else None,
                organization_slug=cal_cfg.organization_slug if cal_cfg else None,
                timezone=cal_cfg.default_timezone if cal_cfg else "America/Bogota",
                language=cal_cfg.default_language if cal_cfg else "es",
            )
            return CalComProvider(self.db, CalComClient(), client_config), "calcom"

        # Default: Google Calendar
        bcfg = self.config_service.get_config(tenant_id, provider="google_calendar")
        return GoogleCalendarProvider(self.db, tenant_id=tenant_id, booking_config=bcfg), "google_calendar"

    def _detect_active_provider(self, tenant_id: str) -> str:
        # Check Cal.com active config first
        cal_cfg = self.config_service.get_config(tenant_id, provider="calcom")
        if cal_cfg and cal_cfg.status == "active" and cal_cfg.cal_api_key_encrypted:
            return "calcom"

        # Check Google Calendar connection
        google_conn = self.db.scalar(
            select(TenantGoogleCalendarConnection).where(
                TenantGoogleCalendarConnection.tenant_id == tenant_id,
                TenantGoogleCalendarConnection.status == "connected",
            )
        )
        if google_conn:
            return "google_calendar"

        return "google_calendar"
