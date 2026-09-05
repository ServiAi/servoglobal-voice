from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import (
    TenantBookingConfig,
    TenantIntegrationEvent,
    TenantSchedulingEventType,
    TenantSchedulingSchedule,
)
from app.services.booking_config_service import BookingConfigService
from app.services.calcom_client import CalComClient, CalComClientConfig
from app.services.calcom_sync_service import CalComSyncService
from app.services.scheduling_protocols import SchedulingAdminProvider, SchedulingProviderCapabilities

logger = logging.getLogger(__name__)


class CalComSchedulingAdminProvider(SchedulingAdminProvider):
    """Cal.com admin provider where Cal.com is the scheduling engine and ServiGlobal acts as Control Plane."""

    def __init__(
        self,
        db: Session,
        tenant_id: str,
        *,
        client: CalComClient | None = None,
        config_service: BookingConfigService | None = None,
        sync_service: CalComSyncService | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.client = client or CalComClient()
        self.config_service = config_service or BookingConfigService(db)
        self.sync_service = sync_service or CalComSyncService(db, calcom_client=self.client, config_service=self.config_service)

    def _client_config(self) -> CalComClientConfig:
        cfg = self.config_service.get_active_config(self.tenant_id, provider="calcom")
        api_key = self.config_service.secret_manager.decrypt_secret(cfg.cal_api_key_encrypted)
        if not api_key:
            raise ValueError("Cal.com API key is not configured or cannot be decrypted.")
        return CalComClientConfig(
            api_key=api_key,
            timezone=cfg.default_timezone,
            language=cfg.default_language,
        )

    def capabilities(self) -> SchedulingProviderCapabilities:
        return SchedulingProviderCapabilities(
            schedules=True,
            native_schedules=True,
            event_types=True,
            native_event_types=True,
            resources=True,
            teams=True,
            native_round_robin=True,
            exceptions=True,
            native_exceptions=True,
            external_calendars=False,
            booking=True,
            reschedule=True,
            cancel=True,
        )

    def discover(self) -> dict[str, Any]:
        cfg = self._client_config()
        return self.client.discover_account(cfg)

    def list_schedules(self) -> list[dict[str, Any]]:
        cfg = self._client_config()
        return self.client.list_schedules(cfg)

    def get_schedule(self, schedule_id: str) -> dict[str, Any]:
        cfg = self._client_config()
        return self.client.get_schedule(cfg, schedule_id)

    def create_schedule(self, payload: dict[str, Any]) -> dict[str, Any]:
        cfg = self._client_config()
        # 1. Write remote
        remote_res = self.client.create_schedule(cfg, payload)
        sched_data = remote_res.get("data", remote_res)
        sched_id = str(sched_data.get("id") or "")
        now = datetime.now(UTC)

        # 2. Remote success -> Update local projection
        local_sched = TenantSchedulingSchedule(
            tenant_id=self.tenant_id,
            provider="calcom",
            name=sched_data.get("name", payload.get("name", "Horario")),
            timezone=sched_data.get("timeZone", payload.get("timeZone", cfg.timezone)),
            working_hours_json=sched_data.get("availability") or payload.get("availability"),
            overrides_json=sched_data.get("overrides") or payload.get("overrides"),
            provider_schedule_id=sched_id,
            is_default=bool(sched_data.get("isDefault", False)),
            is_active=True,
            last_synced_at=now,
            sync_status="synced",
        )
        self.db.add(local_sched)

        # 3. Audit event
        self.db.add(
            TenantIntegrationEvent(
                tenant_id=self.tenant_id,
                provider="calcom",
                event_type="schedule_created",
                status="success",
                resource_type="schedule",
                resource_id=sched_id,
                metadata_json={"name": local_sched.name},
            )
        )
        self.db.commit()
        return sched_data

    def update_schedule(self, schedule_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        cfg = self._client_config()
        # 1. Write remote
        remote_res = self.client.update_schedule(cfg, schedule_id, payload)
        sched_data = remote_res.get("data", remote_res)
        now = datetime.now(UTC)

        # 2. Remote success -> Update local projection
        local_sched = self.db.scalar(
            select(TenantSchedulingSchedule).where(
                TenantSchedulingSchedule.tenant_id == self.tenant_id,
                TenantSchedulingSchedule.provider == "calcom",
                TenantSchedulingSchedule.provider_schedule_id == str(schedule_id),
            )
        )
        if local_sched:
            if "name" in sched_data:
                local_sched.name = sched_data["name"]
            if "timeZone" in sched_data:
                local_sched.timezone = sched_data["timeZone"]
            if "availability" in sched_data:
                local_sched.working_hours_json = sched_data["availability"]
            if "overrides" in sched_data:
                local_sched.overrides_json = sched_data["overrides"]
            local_sched.last_synced_at = now
            local_sched.sync_status = "synced"

        # 3. Audit event
        self.db.add(
            TenantIntegrationEvent(
                tenant_id=self.tenant_id,
                provider="calcom",
                event_type="schedule_updated",
                status="success",
                resource_type="schedule",
                resource_id=str(schedule_id),
                metadata_json={"name": sched_data.get("name")},
            )
        )
        self.db.commit()
        return sched_data

    def delete_schedule(self, schedule_id: str) -> bool:
        cfg = self._client_config()
        # 1. Write remote
        self.client.delete_schedule(cfg, schedule_id)
        now = datetime.now(UTC)

        # 2. Remote success -> Update local projection
        local_sched = self.db.scalar(
            select(TenantSchedulingSchedule).where(
                TenantSchedulingSchedule.tenant_id == self.tenant_id,
                TenantSchedulingSchedule.provider == "calcom",
                TenantSchedulingSchedule.provider_schedule_id == str(schedule_id),
            )
        )
        if local_sched:
            local_sched.sync_status = "remote_deleted"
            local_sched.last_synced_at = now

        # 3. Audit event
        self.db.add(
            TenantIntegrationEvent(
                tenant_id=self.tenant_id,
                provider="calcom",
                event_type="schedule_deleted",
                status="success",
                resource_type="schedule",
                resource_id=str(schedule_id),
                metadata_json={},
            )
        )
        self.db.commit()
        return True

    def list_event_types(self) -> list[dict[str, Any]]:
        cfg = self._client_config()
        return self.client.list_event_types(cfg)

    def get_event_type(self, event_type_id: str) -> dict[str, Any]:
        cfg = self._client_config()
        return self.client.get_event_type(cfg, event_type_id)

    def create_event_type(self, payload: dict[str, Any]) -> dict[str, Any]:
        cfg = self._client_config()
        # 1. Write remote
        remote_res = self.client.create_event_type(cfg, payload)
        et_data = remote_res.get("data", remote_res)
        et_id = str(et_data.get("id") or "")
        now = datetime.now(UTC)

        # 2. Remote success -> Update local projection
        local_et = TenantSchedulingEventType(
            tenant_id=self.tenant_id,
            provider="calcom",
            name=et_data.get("title") or et_data.get("name", payload.get("title", "Tipo de cita")),
            slug=et_data.get("slug", payload.get("slug", f"event-{et_id}")),
            description=et_data.get("description"),
            duration_minutes=int(et_data.get("length") or payload.get("length", 30)),
            slot_interval_minutes=int(et_data.get("slotInterval") or 30),
            buffer_before_minutes=int(et_data.get("beforeEventBuffer") or 0),
            buffer_after_minutes=int(et_data.get("afterEventBuffer") or 0),
            minimum_notice_minutes=int(et_data.get("minimumBookingNotice") or 60),
            timezone=cfg.timezone,
            provider_event_type_id=et_id,
            provider_event_type_slug=et_data.get("slug"),
            provider_config_json=et_data,
            is_active=not bool(et_data.get("hidden", False)),
            last_synced_at=now,
            sync_status="synced",
        )
        self.db.add(local_et)

        # 3. Audit event
        self.db.add(
            TenantIntegrationEvent(
                tenant_id=self.tenant_id,
                provider="calcom",
                event_type="event_type_created",
                status="success",
                resource_type="event_type",
                resource_id=et_id,
                metadata_json={"title": local_et.name, "slug": local_et.slug},
            )
        )
        self.db.commit()
        return et_data

    def update_event_type(self, event_type_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        cfg = self._client_config()
        # 1. Write remote
        remote_res = self.client.update_event_type(cfg, event_type_id, payload)
        et_data = remote_res.get("data", remote_res)
        now = datetime.now(UTC)

        # 2. Remote success -> Update local projection
        local_et = self.db.scalar(
            select(TenantSchedulingEventType).where(
                TenantSchedulingEventType.tenant_id == self.tenant_id,
                TenantSchedulingEventType.provider == "calcom",
                TenantSchedulingEventType.provider_event_type_id == str(event_type_id),
            )
        )
        if local_et:
            if "title" in et_data or "name" in et_data:
                local_et.name = et_data.get("title") or et_data.get("name")
            if "slug" in et_data:
                local_et.slug = et_data["slug"]
                local_et.provider_event_type_slug = et_data["slug"]
            if "description" in et_data:
                local_et.description = et_data["description"]
            if "length" in et_data:
                local_et.duration_minutes = int(et_data["length"])
            local_et.provider_config_json = et_data
            local_et.last_synced_at = now
            local_et.sync_status = "synced"

        # 3. Audit event
        self.db.add(
            TenantIntegrationEvent(
                tenant_id=self.tenant_id,
                provider="calcom",
                event_type="event_type_updated",
                status="success",
                resource_type="event_type",
                resource_id=str(event_type_id),
                metadata_json={"title": et_data.get("title") or et_data.get("name")},
            )
        )
        self.db.commit()
        return et_data

    def delete_event_type(self, event_type_id: str) -> bool:
        cfg = self._client_config()
        # 1. Write remote
        self.client.delete_event_type(cfg, event_type_id)
        now = datetime.now(UTC)

        # 2. Remote success -> Update local projection
        local_et = self.db.scalar(
            select(TenantSchedulingEventType).where(
                TenantSchedulingEventType.tenant_id == self.tenant_id,
                TenantSchedulingEventType.provider == "calcom",
                TenantSchedulingEventType.provider_event_type_id == str(event_type_id),
            )
        )
        if local_et:
            local_et.sync_status = "remote_deleted"
            local_et.last_synced_at = now

        # 3. Audit event
        self.db.add(
            TenantIntegrationEvent(
                tenant_id=self.tenant_id,
                provider="calcom",
                event_type="event_type_deleted",
                status="success",
                resource_type="event_type",
                resource_id=str(event_type_id),
                metadata_json={},
            )
        )
        self.db.commit()
        return True

    def list_resources(self) -> list[dict[str, Any]]:
        # Returns resources/users discovered in Cal.com
        discovery = self.discover()
        user = discovery.get("user", {})
        return [
            {
                "id": str(user.get("id", "calcom-owner")),
                "name": user.get("name") or user.get("username", "Usuario Cal.com"),
                "email": user.get("email"),
                "is_active": True,
            }
        ] if user else []

    def list_teams(self) -> list[dict[str, Any]]:
        cfg = self._client_config()
        return self.client.list_teams(cfg)

    def get_team(self, team_id: str) -> dict[str, Any]:
        cfg = self._client_config()
        return self.client.get_team(cfg, team_id)

    def list_team_members(self, team_id: str) -> list[dict[str, Any]]:
        cfg = self._client_config()
        return self.client.list_team_members(cfg, team_id)

    def sync(self) -> dict[str, Any]:
        return self.sync_service.sync(self.tenant_id)
