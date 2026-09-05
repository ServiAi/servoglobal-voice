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
    TenantSchedulingProviderObject,
    TenantSchedulingSchedule,
    TenantSchedulingTeam,
)
from app.services.booking_config_service import BookingConfigService
from app.services.calcom_client import CalComClient, CalComClientConfig, sanitize_calcom_error

logger = logging.getLogger(__name__)


class CalComSyncService:
    def __init__(
        self,
        db: Session,
        *,
        calcom_client: CalComClient | None = None,
        config_service: BookingConfigService | None = None,
    ) -> None:
        self.db = db
        self.client = calcom_client or CalComClient()
        self.config_service = config_service or BookingConfigService(db)

    def sync(self, tenant_id: str) -> dict[str, Any]:
        """Performs automated discovery from Cal.com API v2 and reconciles local projections."""
        booking_config = self.config_service.get_active_config(tenant_id, provider="calcom")
        api_key = self.config_service.secret_manager.decrypt_secret(booking_config.cal_api_key_encrypted)
        if not api_key:
            raise ValueError("No se pudo descifrar la API Key de Cal.com.")

        client_config = CalComClientConfig(
            api_key=api_key,
            timezone=booking_config.default_timezone,
            language=booking_config.default_language,
        )

        now = datetime.now(UTC)
        try:
            discovery = self.client.discover_account(client_config)
        except Exception as exc:
            error_msg = sanitize_calcom_error(str(exc))
            booking_config.last_error_message = error_msg
            self.db.add(
                TenantIntegrationEvent(
                    tenant_id=tenant_id,
                    provider="calcom",
                    event_type="calcom_sync",
                    status="error",
                    message=f"Sync failed: {error_msg}",
                    metadata_json={"error": error_msg},
                )
            )
            self.db.commit()
            raise

        remote_schedules = discovery.get("schedules", [])
        remote_event_types = discovery.get("event_types", [])
        remote_teams = discovery.get("teams", [])
        user_info = discovery.get("user", {})

        # 1. Sync Schedules
        synced_schedule_ext_ids: set[str] = set()
        for sched in remote_schedules:
            sched_id_raw = sched.get("id")
            if sched_id_raw is None:
                continue
            sched_id = str(sched_id_raw)
            synced_schedule_ext_ids.add(sched_id)

            local_sched = self.db.scalar(
                select(TenantSchedulingSchedule).where(
                    TenantSchedulingSchedule.tenant_id == tenant_id,
                    TenantSchedulingSchedule.provider == "calcom",
                    TenantSchedulingSchedule.provider_schedule_id == sched_id,
                )
            )
            name = sched.get("name") or f"Horario Cal.com #{sched_id}"
            tz = sched.get("timeZone") or booking_config.default_timezone
            working_hours = sched.get("availability") or sched.get("working_hours_json")
            overrides = sched.get("overrides") or sched.get("dateOverrides")
            is_default = bool(sched.get("isDefault", False))

            if local_sched is None:
                local_sched = TenantSchedulingSchedule(
                    tenant_id=tenant_id,
                    provider="calcom",
                    name=name,
                    timezone=tz,
                    working_hours_json=working_hours if isinstance(working_hours, (dict, list)) else None,
                    overrides_json=overrides if isinstance(overrides, list) else None,
                    provider_schedule_id=sched_id,
                    is_default=is_default,
                    is_active=True,
                    last_synced_at=now,
                    sync_status="synced",
                )
                self.db.add(local_sched)
                self.db.flush()
            else:
                local_sched.name = name
                local_sched.timezone = tz
                if isinstance(working_hours, (dict, list)):
                    local_sched.working_hours_json = working_hours
                if isinstance(overrides, list):
                    local_sched.overrides_json = overrides
                local_sched.is_default = is_default
                local_sched.is_active = True
                local_sched.last_synced_at = now
                local_sched.sync_status = "synced"
                local_sched.last_error_message = None

            self._upsert_provider_object(
                tenant_id=tenant_id,
                provider="calcom",
                object_type="schedule",
                local_object_id=local_sched.id,
                external_id=sched_id,
                external_slug=None,
                metadata={"name": name, "is_default": is_default},
                synced_at=now,
            )

        # Mark missing remote schedules as remote_deleted (never delete historical data)
        missing_schedules = list(
            self.db.scalars(
                select(TenantSchedulingSchedule).where(
                    TenantSchedulingSchedule.tenant_id == tenant_id,
                    TenantSchedulingSchedule.provider == "calcom",
                    TenantSchedulingSchedule.sync_status != "remote_deleted",
                )
            )
        )
        for ms in missing_schedules:
            if ms.provider_schedule_id not in synced_schedule_ext_ids:
                ms.sync_status = "remote_deleted"
                ms.last_synced_at = now

        # 2. Sync Teams
        synced_team_ext_ids: set[str] = set()
        for team in remote_teams:
            team_id_raw = team.get("id")
            if team_id_raw is None:
                continue
            team_id = str(team_id_raw)
            synced_team_ext_ids.add(team_id)
            team_name = team.get("name") or f"Equipo Cal.com #{team_id}"

            local_team = self.db.scalar(
                select(TenantSchedulingTeam).where(
                    TenantSchedulingTeam.tenant_id == tenant_id,
                    TenantSchedulingTeam.name == team_name,
                )
            )
            if local_team is None:
                local_team = TenantSchedulingTeam(
                    tenant_id=tenant_id,
                    name=team_name,
                    description=f"Sincronizado desde Cal.com (ID {team_id})",
                    routing_strategy="round_robin",
                    is_active=True,
                )
                self.db.add(local_team)
                self.db.flush()

            self._upsert_provider_object(
                tenant_id=tenant_id,
                provider="calcom",
                object_type="team",
                local_object_id=local_team.id,
                external_id=team_id,
                external_slug=team.get("slug"),
                metadata=team,
                synced_at=now,
            )

        # 3. Sync Event Types
        synced_et_ext_ids: set[str] = set()
        for et in remote_event_types:
            et_id_raw = et.get("id")
            if et_id_raw is None:
                continue
            et_id = str(et_id_raw)
            synced_et_ext_ids.add(et_id)

            et_name = et.get("title") or et.get("name") or f"Tipo de cita #{et_id}"
            et_slug = et.get("slug") or f"event-{et_id}"
            et_duration = int(et.get("length") or et.get("duration") or 30)
            et_desc = et.get("description")
            is_active = not bool(et.get("hidden", False))

            # Match local schedule if scheduleId present
            local_sched_id = None
            sched_ref = et.get("scheduleId") or et.get("schedule_id")
            if sched_ref:
                matched_sched = self.db.scalar(
                    select(TenantSchedulingSchedule.id).where(
                        TenantSchedulingSchedule.tenant_id == tenant_id,
                        TenantSchedulingSchedule.provider == "calcom",
                        TenantSchedulingSchedule.provider_schedule_id == str(sched_ref),
                    )
                )
                local_sched_id = matched_sched

            # Match local team if teamId present
            local_team_id = None
            team_ref = et.get("teamId") or et.get("team_id")
            if team_ref:
                matched_team_obj = self.db.scalar(
                    select(TenantSchedulingProviderObject.local_object_id).where(
                        TenantSchedulingProviderObject.tenant_id == tenant_id,
                        TenantSchedulingProviderObject.provider == "calcom",
                        TenantSchedulingProviderObject.object_type == "team",
                        TenantSchedulingProviderObject.external_id == str(team_ref),
                    )
                )
                local_team_id = matched_team_obj

            local_et = self.db.scalar(
                select(TenantSchedulingEventType).where(
                    TenantSchedulingEventType.tenant_id == tenant_id,
                    TenantSchedulingEventType.provider == "calcom",
                    TenantSchedulingEventType.provider_event_type_id == et_id,
                )
            )
            if local_et is None:
                local_et = TenantSchedulingEventType(
                    tenant_id=tenant_id,
                    provider="calcom",
                    name=et_name,
                    slug=et_slug,
                    description=et_desc,
                    duration_minutes=et_duration,
                    slot_interval_minutes=int(et.get("slotInterval") or et_duration),
                    buffer_before_minutes=int(et.get("beforeEventBuffer") or 0),
                    buffer_after_minutes=int(et.get("afterEventBuffer") or 0),
                    minimum_notice_minutes=int(et.get("minimumBookingNotice") or 60),
                    timezone=booking_config.default_timezone,
                    local_schedule_id=local_sched_id,
                    local_team_id=local_team_id,
                    provider_event_type_id=et_id,
                    provider_event_type_slug=et_slug,
                    provider_config_json=et,
                    is_active=is_active,
                    last_synced_at=now,
                    sync_status="synced",
                )
                self.db.add(local_et)
                self.db.flush()
            else:
                local_et.name = et_name
                local_et.slug = et_slug
                local_et.description = et_desc
                local_et.duration_minutes = et_duration
                local_et.slot_interval_minutes = int(et.get("slotInterval") or et_duration)
                local_et.buffer_before_minutes = int(et.get("beforeEventBuffer") or 0)
                local_et.buffer_after_minutes = int(et.get("afterEventBuffer") or 0)
                local_et.minimum_notice_minutes = int(et.get("minimumBookingNotice") or 60)
                if local_sched_id:
                    local_et.local_schedule_id = local_sched_id
                if local_team_id:
                    local_et.local_team_id = local_team_id
                local_et.provider_event_type_slug = et_slug
                local_et.provider_config_json = et
                local_et.is_active = is_active
                local_et.last_synced_at = now
                local_et.sync_status = "synced"
                local_et.last_error_message = None

            self._upsert_provider_object(
                tenant_id=tenant_id,
                provider="calcom",
                object_type="event_type",
                local_object_id=local_et.id,
                external_id=et_id,
                external_slug=et_slug,
                metadata=et,
                synced_at=now,
            )

        # Mark missing remote event types as remote_deleted
        missing_ets = list(
            self.db.scalars(
                select(TenantSchedulingEventType).where(
                    TenantSchedulingEventType.tenant_id == tenant_id,
                    TenantSchedulingEventType.provider == "calcom",
                    TenantSchedulingEventType.sync_status != "remote_deleted",
                )
            )
        )
        for met in missing_ets:
            if met.provider_event_type_id not in synced_et_ext_ids:
                met.sync_status = "remote_deleted"
                met.last_synced_at = now

        # 4. Update Booking Config health check and user details
        booking_config.last_health_check_at = now
        booking_config.status = "active"
        booking_config.last_error_message = None
        if user_info.get("username") and not booking_config.default_username:
            booking_config.default_username = user_info["username"]

        # 5. Record integration audit event
        self.db.add(
            TenantIntegrationEvent(
                tenant_id=tenant_id,
                provider="calcom",
                event_type="calcom_sync",
                status="success",
                message=f"Sync exitoso: {len(synced_schedule_ext_ids)} horarios, {len(synced_et_ext_ids)} tipos de cita, {len(synced_team_ext_ids)} equipos.",
                metadata_json={
                    "schedules_count": len(synced_schedule_ext_ids),
                    "event_types_count": len(synced_et_ext_ids),
                    "teams_count": len(synced_team_ext_ids),
                    "username": user_info.get("username"),
                    "email": user_info.get("email"),
                },
            )
        )
        self.db.commit()

        return {
            "status": "success",
            "counts": {
                "schedules": len(synced_schedule_ext_ids),
                "event_types": len(synced_et_ext_ids),
                "teams": len(synced_team_ext_ids),
            },
            "account": {
                "id": user_info.get("id"),
                "username": user_info.get("username"),
                "email": user_info.get("email"),
                "name": user_info.get("name"),
            },
            "last_synced_at": now.isoformat(),
        }

    def _upsert_provider_object(
        self,
        *,
        tenant_id: str,
        provider: str,
        object_type: str,
        local_object_id: str | None,
        external_id: str,
        external_slug: str | None,
        metadata: dict[str, Any],
        synced_at: datetime,
    ) -> TenantSchedulingProviderObject:
        obj = self.db.scalar(
            select(TenantSchedulingProviderObject).where(
                TenantSchedulingProviderObject.tenant_id == tenant_id,
                TenantSchedulingProviderObject.provider == provider,
                TenantSchedulingProviderObject.object_type == object_type,
                TenantSchedulingProviderObject.external_id == external_id,
            )
        )
        if obj is None:
            obj = TenantSchedulingProviderObject(
                tenant_id=tenant_id,
                provider=provider,
                object_type=object_type,
                local_object_id=local_object_id,
                external_id=external_id,
                external_slug=external_slug,
                provider_metadata_json=metadata,
                sync_status="active",
                last_synced_at=synced_at,
            )
            self.db.add(obj)
        else:
            obj.local_object_id = local_object_id
            obj.external_slug = external_slug
            obj.provider_metadata_json = metadata
            obj.sync_status = "active"
            obj.last_synced_at = synced_at
            obj.last_error_message = None
        return obj
